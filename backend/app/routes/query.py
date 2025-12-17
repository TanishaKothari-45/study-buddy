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
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..core.deps import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    mode: str = "concise" # concise or detailed

@router.post("/")
async def generate_answer(
    request: Request,
    query_request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue Mains Answer generation.
    Returns job_id for polling.
    """
    try:
        user_id = str(current_user.id) if current_user else "anonymous"
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
            client = redis.Redis(host="localhost", port=6379, decode_responses=True)
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
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        
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
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        return {"message": "Cancellation requested"}
    except Exception as e:
        raise HTTPException(500, str(e))