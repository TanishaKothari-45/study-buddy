"""
query.py

Mains Answer Generation using Arq Queue.
Replaces legacy streaming with Unified Queue polling.

Usage:
  POST /query/ -> {job_id: ...}
  GET /query/status/{job_id} -> {status: ..., result: ...}
"""

import logging
import json
import redis.asyncio as redis
from uuid import uuid4
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional, List, Dict
from ..models.mains import QueryRequest
from ..utils.user_api_key import get_gemini_api_key_for_request
from ..gemini_core import settings_gemini_key

# Global default (fallback)
GEMINI_API_KEY_SYSTEM = settings_gemini_key.GEMINI_API_KEY

from ..core.deps import get_current_user, get_redis_client
from ..core.user_profile import UserProfile

logger = logging.getLogger(__name__)

# Routes
router = APIRouter()

@router.post("/")
async def generate_answer(
    request: Request,
    query_request: QueryRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Enqueue Mains Answer generation.
    Returns job_id for polling.
    """
    try:
        user_id = str(current_user.id) if current_user else "anonymous"

        # 1. Get Gemini Key
        try:
            gemini_api_key = get_gemini_api_key_for_request(current_user)
            if not gemini_api_key or not gemini_api_key.strip():
                gemini_api_key = GEMINI_API_KEY_SYSTEM
        except Exception:
            gemini_api_key = GEMINI_API_KEY_SYSTEM

        if not gemini_api_key or not gemini_api_key.strip():
             raise HTTPException(400, "No Gemini API key available. Please configure an API key in Settings.")

        job_id = str(uuid4())
        
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            raise HTTPException(500, "Job queue not initialized")

        # Enqueue job
        await arq_pool.enqueue_job(
            "generate_mains_answer_task",
            job_id=job_id,
            query=query_request.query,
            user_id=user_id
        )
        
        # Set initial status
        try:
            client = get_redis_client()
            await client.set(f"job_status:{job_id}", "queued", ex=3600)
            await client.close()
        except:
            pass

        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Answer generation started. Poll /query/status/{job_id}"
        }

    except Exception as e:
        logger.error(f"❌ Failed to enqueue query: {e}")
        raise HTTPException(500, str(e))

@router.get("/status/{job_id}")
async def get_query_status(job_id: str):
    """
    Poll status of answer generation job.
    """
    try:
        client = get_redis_client()
        
        status = await client.get(f"job_status:{job_id}")
        if not status:
             status = "unknown"

        result = None
        if status == "completed":
            result_json = await client.get(f"job_result:{job_id}")
            if result_json:
                result = json.loads(result_json)
        
        error = None
        if status == "failed":
            error = await client.get(f"job_error:{job_id}")

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
async def cancel_query(job_id: str):
    """
    Cancel a running query job.
    """
    try:
        client = get_redis_client()
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        return {"message": "Cancellation requested"}
    except Exception as e:
        raise HTTPException(500, str(e))