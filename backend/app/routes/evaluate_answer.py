"""
evaluate_answer.py

Evaluation pipeline using Arq Queue + Gemini.

Flow:
  1) Upload answer (PDF/image) -> Save to disk -> Enqueue Job -> Return job_id
  2) Worker processes job (OCR -> Retrieval -> Gemini)
  3) User polls /status/{job_id}

Usage:
  POST /evaluate-answer/ -> {job_id: ...}
  GET /evaluate-answer/status/{job_id} -> {status: ..., result: ...}
"""

import os
import logging
import shutil
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException, Depends
from pathlib import Path
from uuid import uuid4
import redis.asyncio as redis

from ..core.config import settings
from ..core.deps import get_current_user
from ..models.user import User
from ..utils.user_api_key import get_gemini_api_key_for_request
from ..gemini_core import settings_gemini_key

logger = logging.getLogger(__name__)

router = APIRouter()

# Global default (fallback)
GEMINI_API_KEY_SYSTEM = settings_gemini_key.GEMINI_API_KEY

@router.post("/")
async def evaluate_answer_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    question: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue answer evaluation task.
    Saves files to backend/data/temp/{job_id}/ and enqueues job.
    """
    try:
        # 1. Get Gemini Key
        try:
            gemini_api_key = get_gemini_api_key_for_request(current_user)
            if not gemini_api_key:
                gemini_api_key = GEMINI_API_KEY_SYSTEM
        except Exception:
            gemini_api_key = GEMINI_API_KEY_SYSTEM

        if not gemini_api_key:
             raise HTTPException(400, "No Gemini API key available.")
            
        # 2. Preparation
        job_id = str(uuid4())
        job_dir = settings.BASE_DIR / "data" / "temp" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        saved_file_paths = []
        
        # 3. Save Files
        for file in files:
            file_ext = Path(file.filename).suffix.lower() if file.filename else '.pdf'
            safe_filename = f"{uuid4()}{file_ext}"
            file_path = job_dir / safe_filename
            
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            saved_file_paths.append(str(file_path))
            
        # 4. Enqueue Job
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            # Cleanup if queue fails
            shutil.rmtree(job_dir)
            raise HTTPException(500, "Job queue not initialized")
            
        await arq_pool.enqueue_job(
            "evaluate_answer_task",
            job_id=job_id,
            file_paths=saved_file_paths,
            question=question or "",
            user_id=str(current_user.id) if current_user else "anonymous",
            gemini_api_key=gemini_api_key
        )
        
        # 5. Set initial status in Redis
        # We use a separate redis client connection for status (simple string)
        # or we rely on the client knowing it's "queued".
        # Let's set it explicitly so status endpoint works immediately.
        # But we don't have a redis client handy in route unless we create one.
        # Arq pool doesn't expose SET.
        # We can spin up a quick client.
        
        try:
            client = redis.Redis(host="localhost", port=6379, decode_responses=True)
            await client.set(f"job_status:{job_id}", "queued", ex=3600)
            await client.close()
        except:
            pass # Non-critical
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Evaluation started. Poll /evaluate-answer/status/{job_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to enqueue evaluation: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/status/{job_id}")
async def get_evaluation_status(request: Request, job_id: str):
    """
    Poll status of evaluation job.
    """
    try:
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        
        status = await client.get(f"job_status:{job_id}")
        if not status:
             # Fallback: check if Arq knows about it?
             # If completely missing, maybe it expired or never existed.
             status = "unknown"
             
        result = None
        if status == "completed":
            result_json = await client.get(f"job_result:{job_id}")
            if result_json:
                result = json.loads(result_json)
        
        error = None
        if status == "failed":
            error = await client.get(f"job_error:{job_id}")

        # Semantic logging for polling
        logger.info(f"EVALUATION_STATUS - {job_id[:8]}... : {status.upper()}")

        await client.close()
            
        return {
            "job_id": job_id,
            "status": status,
            "result": result,
            "error": error
        }

    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/cancel/{job_id}")
async def cancel_evaluation(job_id: str):
    """
    Cancel a running evaluation job.
    """
    try:
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        return {"message": "Cancellation requested"}
    except Exception as e:
        raise HTTPException(500, str(e))
