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
            if not gemini_api_key or not gemini_api_key.strip():
                gemini_api_key = GEMINI_API_KEY_SYSTEM
        except Exception:
            gemini_api_key = GEMINI_API_KEY_SYSTEM

        if not gemini_api_key or not gemini_api_key.strip():
             raise HTTPException(400, "No Gemini API key available. Please configure an API key in Settings.")
            
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
            _job_id=job_id,
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


@router.post("/batch")
async def evaluate_batch_answers_endpoint(
    request: Request,
    file: UploadFile = File(...),
    use_standard_format: bool = Form(default=False),  # Use UPSC standard format (2+3 pages)
    question_file: Optional[UploadFile] = File(default=None),  # Optional question PDF/image
    questions: Optional[str] = Form(default=None),  # Optional JSON array of question texts
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue batch answer evaluation task.
    Accepts a PDF with multiple answers (up to 20), splits by regex patterns (Q1, Q2, etc.),
    and evaluates each answer sequentially.
    
    Returns batch_job_id for polling progress.
    """
    try:
        # 1. Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(400, "Only PDF files are supported for batch evaluation")
        
        # 2. Get Gemini Key
        try:
            gemini_api_key = get_gemini_api_key_for_request(current_user)
            if not gemini_api_key:
                gemini_api_key = GEMINI_API_KEY_SYSTEM
        except Exception:
            gemini_api_key = GEMINI_API_KEY_SYSTEM

        if not gemini_api_key:
            raise HTTPException(400, "No Gemini API key available.")
        
        # 3. Save PDF and question file if provided
        job_id = str(uuid4())
        job_dir = settings.BASE_DIR / "data" / "temp" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = job_dir / f"{uuid4()}.pdf"
        content = await file.read()
        with open(pdf_path, "wb") as f:
            f.write(content)
        
        # Save question file if provided
        question_file_path = None
        if question_file:
            # Validate question file type
            if not question_file.filename:
                raise HTTPException(400, "Question file must have a filename")
            
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.webp']
            file_ext = Path(question_file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                raise HTTPException(400, f"Question file must be PDF or image ({', '.join(allowed_extensions)})")
            
            question_file_path = job_dir / f"question_{uuid4()}{file_ext}"
            question_content = await question_file.read()
            with open(question_file_path, "wb") as f:
                f.write(question_content)
        
        # Parse manual questions if provided
        question_texts = None
        if questions:
            try:
                question_texts = json.loads(questions)
                if not isinstance(question_texts, list):
                    raise ValueError("Questions must be a JSON array")
                # Filter out empty questions
                question_texts = [q.strip() for q in question_texts if q.strip()]
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(400, f"Invalid questions JSON format: {str(e)}")
        
        # 4. Enqueue Batch Job
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            shutil.rmtree(job_dir)
            raise HTTPException(500, "Job queue not initialized")
        
        await arq_pool.enqueue_job(
            "evaluate_batch_answers_task",
            _job_id=job_id,
            job_id=job_id,
            pdf_path=str(pdf_path),
            user_id=str(current_user.id) if current_user else "anonymous",
            gemini_api_key=gemini_api_key,
            use_standard_format=use_standard_format,
            question_file_path=str(question_file_path) if question_file_path else None,
            question_texts=question_texts
        )
        
        # 5. Set initial status
        try:
            client = redis.Redis(host="localhost", port=6379, decode_responses=True)
            await client.set(f"job_status:{job_id}", "queued", ex=7200)  # 2 hour TTL for batch jobs
            await client.close()
        except:
            pass  # Non-critical
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Batch evaluation started. Poll /evaluate-answer/status/{job_id} for progress"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to enqueue batch evaluation: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/status/{job_id}")
async def get_evaluation_status(request: Request, job_id: str):
    """
    Poll status of evaluation job (single or batch).
    
    For batch jobs, returns:
    {
        "job_id": "...",
        "status": "processing" | "completed" | "partial_failed" | "cancelled" | "failed",
        "batch_data": {
            "total_answers": 20,
            "completed_answers": 15,
            "failed_answers": 2,
            "answers": [
                {
                    "answer_id": "a1",
                    "question_number": 1,
                    "status": "completed" | "failed" | "processing",
                    "evaluation": {...} | null,
                    "error": "..." | null
                },
                ...
            ]
        },
        "result": {...},  # Only for single answer jobs
        "error": "..."  # Only if status is "failed" or "cancelled"
    }
    """
    try:
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        
        status = await client.get(f"job_status:{job_id}")
        if not status:
            status = "unknown"
        
        # Check if this is a batch job (has batch_data)
        batch_data_json = await client.get(f"job_batch_data:{job_id}")
        is_batch = batch_data_json is not None
        
        result = None
        batch_data = None
        
        if is_batch:
            # Batch job - return batch progress
            batch_data = json.loads(batch_data_json) if batch_data_json else None
            
            # Also check for final result
            if status in ["completed", "partial_failed"]:
                result_json = await client.get(f"job_result:{job_id}")
                if result_json:
                    result = json.loads(result_json)
                    # Use result batch_data if available (more up-to-date)
                    if result and "answers" in result:
                        batch_data = result
        else:
            # Single answer job
            if status == "completed":
                result_json = await client.get(f"job_result:{job_id}")
                if result_json:
                    result = json.loads(result_json)
        
        error = None
        if status in ["failed", "cancelled"]:
            error = await client.get(f"job_error:{job_id}")

        # Semantic logging for polling
        logger.info(f"EVALUATION_STATUS - {job_id[:8]}... : {status.upper()}")

        await client.close()
        
        response = {
            "job_id": job_id,
            "status": status,
        }
        
        if is_batch:
            response["batch_data"] = batch_data
        else:
            response["result"] = result
        
        if error:
            response["error"] = error
            
        return response

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


@router.post("/generate-improved")
async def generate_improved_answer_endpoint(
    request: Request,
    question: str = Form(...),
    feedback: str = Form(...),  # JSON string
    student_answer: Optional[str] = Form(default=None),
    word_count: Optional[int] = Form(default=250),
    files: Optional[List[UploadFile]] = File(default=None),
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue improved answer generation task.
    Takes question, feedback (from evaluation), and optionally student answer files/text.
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
        
        # 2. Parse feedback JSON
        try:
            feedback_dict = json.loads(feedback)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid feedback JSON format")
        
        # 3. Preparation
        job_id = str(uuid4())
        saved_file_paths = None
        
        # 4. Save Files if provided
        if files and len(files) > 0:
            job_dir = settings.BASE_DIR / "data" / "temp" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            saved_file_paths = []
            
            for file in files:
                file_ext = Path(file.filename).suffix.lower() if file.filename else '.pdf'
                safe_filename = f"{uuid4()}{file_ext}"
                file_path = job_dir / safe_filename
                
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                
                saved_file_paths.append(str(file_path))
        
        # 5. Enqueue Job
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            # Cleanup if queue fails
            if saved_file_paths:
                import shutil
                shutil.rmtree(Path(saved_file_paths[0]).parent)
            raise HTTPException(500, "Job queue not initialized")
        
        await arq_pool.enqueue_job(
            "generate_improved_answer_task",
            _job_id=job_id,
            job_id=job_id,
            question=question,
            student_answer=student_answer,
            file_paths=saved_file_paths,
            feedback=feedback_dict,
            user_id=str(current_user.id) if current_user else "anonymous",
            gemini_api_key=gemini_api_key,
            word_count=word_count
        )
        
        # 6. Set initial status in Redis
        try:
            client = redis.Redis(host="localhost", port=6379, decode_responses=True)
            await client.set(f"job_status:{job_id}", "queued", ex=3600)
            await client.close()
        except:
            pass  # Non-critical
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Improved answer generation started. Poll /evaluate-answer/status/{job_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to enqueue improved answer generation: {e}", exc_info=True)
        raise HTTPException(500, str(e))
