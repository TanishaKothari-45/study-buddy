"""
query.py

Mains Answer Generation using Arq Queue + Streaming Chat.

Usage:
  POST /query/ -> {job_id: ...}  (Mains answer via queue)
  GET /query/status/{job_id} -> {status: ..., result: ...}
  POST /query/stream -> SSE stream (Real-time chat with RAG)
"""

import logging
import json
import redis.asyncio as redis
from uuid import uuid4
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from ..models.mains import QueryRequest
from ..utils.user_api_key import get_gemini_api_key_for_request
from ..gemini_core import settings_gemini_key
from ..gemini_core.gemini_client import GeminiClient
import os
import asyncio

# Global default (fallback)
GEMINI_API_KEY_SYSTEM = settings_gemini_key.GEMINI_API_KEY

# TODO: REVERT FOR PROD — change get_current_user_optional → get_current_user on all 3 usages below
# (lines ~51, ~157 in this file). Also restore: Optional[UserProfile] → UserProfile in the param type.
from ..core.deps import get_current_user_optional, get_redis_client

from ..core.user_profile import UserProfile
from ..utils.user_api_key import get_gemini_api_key_for_request, get_direct_api_key_from_request

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Request for streaming chat with RAG."""
    question: str = Field(..., description="User's question")
    subject: Optional[str] = Field(default=None, description="Subject filter (Geography, History)")
    session_id: Optional[str] = Field(default=None, description="Chat session ID")
    k: int = Field(default=5, description="Number of documents to retrieve")

# Routes
router = APIRouter()

@router.post("/")
async def generate_answer(
    request: Request,
    query_request: QueryRequest,
    current_user: Optional[UserProfile] = Depends(get_current_user_optional)
):
    """
    Enqueue Mains Answer generation.
    Returns job_id for polling.
    """
    try:
        user_id = str(current_user.id) if current_user else "anonymous"

        # 1. Get Gemini Key
        try:
            direct_key = get_direct_api_key_from_request(request)
            gemini_api_key = get_gemini_api_key_for_request(current_user, direct_key)
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


@router.post("/stream")
async def stream_chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: Optional[UserProfile] = Depends(get_current_user_optional)
):
    """
    Streaming chat endpoint with RAG (Chat Pipeline v2).

    Pipeline stages:
      0. Query Analysis — LLM extracts subject/domain + generates multi-query variants
      1. Enhanced Retrieval — multi-query Pinecone fetch + cross-encoder rerank
      2. Response Generation — UPSC-aware structured prompt, streamed
      3. Recommendations — metadata-driven related topics (no LLM)

    SSE events: sources → content (streamed) → recommendations → done
    """
    from ..services.chat_pipeline import run_chat_pipeline

    question = chat_request.question
    subject = chat_request.subject
    k = chat_request.k

    # Get Gemini API key upfront
    try:
        direct_key = get_direct_api_key_from_request(request)
        gemini_api_key = get_gemini_api_key_for_request(current_user, direct_key)
        if not gemini_api_key or not gemini_api_key.strip():
            gemini_api_key = GEMINI_API_KEY_SYSTEM
    except Exception:
        gemini_api_key = GEMINI_API_KEY_SYSTEM

    if not gemini_api_key:
        raise HTTPException(400, "No Gemini API key configured")

    pinecone_handler = request.app.state.vector_handler
    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model_name="gemini-2.5-flash",
        timeout=120.0,
    )

    return StreamingResponse(
        run_chat_pipeline(
            question=question,
            subject=subject,
            pinecone_handler=pinecone_handler,
            gemini_client=gemini_client,
            k=k,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )