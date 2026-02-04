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

from ..core.deps import get_current_user, get_redis_client
from ..core.user_profile import UserProfile

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


@router.post("/stream")
async def stream_chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Streaming chat endpoint with RAG (Retrieval Augmented Generation).
    
    1. Retrieves relevant documents from Pinecone (filtered by subject if provided)
    2. Streams LLM response in real-time via SSE
    """
    # Extract values from request to avoid closure issues
    question = chat_request.question
    subject = chat_request.subject
    k = chat_request.k
    
    # Get Gemini API key upfront
    try:
        gemini_api_key = get_gemini_api_key_for_request(current_user)
        if not gemini_api_key or not gemini_api_key.strip():
            gemini_api_key = GEMINI_API_KEY_SYSTEM
    except Exception:
        gemini_api_key = GEMINI_API_KEY_SYSTEM
    
    if not gemini_api_key:
        raise HTTPException(400, "No Gemini API key configured")
    
    # Get pinecone handler
    pinecone_handler = request.app.state.vector_handler
    
    async def generate_stream():
        try:
            # Build Pinecone filter for subject
            filter_metadata = None
            if subject:
                # Pinecone stores subject as "Geography", "History" etc
                filter_metadata = {"subject": subject}
                logger.info(f"🔍 Chat filter: subject={subject}")
            
            # Retrieve relevant documents
            logger.info(f"📚 Retrieving {k} documents for: '{question[:50]}...'")
            
            results = pinecone_handler.query_documents(
                query_text=question,
                k=k,
                filter_metadata=filter_metadata,
                use_content_store=True,
                re_rank=True,
                fetch_k=20
            )
            
            # Format sources for frontend
            sources = []
            context_chunks = []
            for doc in results:
                meta = doc.get("metadata", {})
                sources.append({
                    "filename": meta.get("filename", "Unknown"),
                    "page_number": meta.get("page_number"),
                    "chapter": meta.get("chapter", "Unknown"),
                    "subject": meta.get("subject", "Unknown")
                })
                content = doc.get("content") or doc.get("page_content", "")
                if content:
                    context_chunks.append(content[:2000])  # Limit each chunk
            
            # Send sources first
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            
            # Build context for LLM
            context_text = "\n\n---\n\n".join(context_chunks[:5]) if context_chunks else "No relevant context found."
            
            # Build prompt
            subject_label = f" about {subject}" if subject else ""
            prompt_text = f"""You are a knowledgeable study assistant{subject_label} for UPSC preparation.

Use the following context from study materials to answer the question. 
If the context doesn't contain relevant information, say so and provide what general knowledge you have.

CONTEXT:
{context_text}

Be concise, accurate, and cite specific details from the context when available.

Question: {question}"""

            # Initialize Gemini client
            gemini_client = GeminiClient(
                api_key=gemini_api_key,
                model_name="gemini-2.5-flash",
                timeout=120.0
            )
            
            # Stream response
            async for chunk in gemini_client.generate_response_streaming(
                text_input=prompt_text,
                temperature=0.3
            ):
                if chunk:
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"❌ Chat stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )