"""
mains_answer.py
Main handler for mains answer generation using Gemini 2.5 Pro.

Uses MCP current affairs server for latest news (not web_searcher).

Usage:
  from app.prompts.mains_prompt import assemble_mains_prompt
  from mains_answer import generate_answer

Config:
  export GEMINI_API_KEY=...
"""

import os
import sys
import logging
import re
import json
import redis.asyncio as redis
from uuid import uuid4
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

logger = logging.getLogger("mains_answer")
logging.basicConfig(level=logging.INFO)

def clean_gemini_error(error_msg: str) -> str:
    """
    Clean Gemini API error messages for user-friendly display.
    Provides actionable guidance to help users resolve the issue.
    """
    # For quota errors (429)
    if '429' in error_msg and 'quota' in error_msg.lower():
        return "Failed to generate answer: You have exceeded your Gemini API quota. Please check your usage at https://aistudio.google.com/app/apikey and upgrade your plan if needed, or try again after some time."
    
    if '429' in error_msg and 'rate limit' in error_msg.lower():
        return "Failed to generate answer: Too many requests to Gemini API. Please wait a few minutes and try again."
    
    # For auth errors
    lower_msg = error_msg.lower()
    if 'api_key_invalid' in error_msg or 'api key not valid' in lower_msg or 'invalid api key' in lower_msg:
        return "Failed to generate answer: Invalid Gemini API key. Please update your API key in Settings. You can get a new key from https://aistudio.google.com/app/apikey"
    
    # For timeout errors
    if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
        return "Failed to generate answer: Request timed out. The AI service is taking longer than expected. Please try again, or try with a shorter question."
    
    # For network/connection errors
    if 'connection' in error_msg.lower() or 'network' in error_msg.lower():
        return "Failed to generate answer: Network connection error. Please check your internet connection and try again."
    
    # For empty response
    if 'empty response' in error_msg.lower():
        return "Failed to generate answer: Received empty response from AI service. This is usually temporary - please try again in a moment."
    
    # For service unavailable
    if 'service unavailable' in error_msg.lower() or '503' in error_msg:
        return "Failed to generate answer: AI service is temporarily unavailable. Please try again in a few minutes."
    
    # For server errors
    if '500' in error_msg or 'internal server error' in error_msg.lower():
        return "Failed to generate answer: Server error occurred. We're working to fix this. Please try again or contact support if the issue persists."
    
    # Generic fallback with first sentence
    first_line = error_msg.split('\n')[0]
    first_sentence = first_line.split('.')[0]
    
    # Limit to reasonable length
    if len(first_sentence) > 120:
        first_sentence = first_sentence[:117] + '...'
    
    # Always prefix with "Failed to generate answer:"
    if first_sentence and not first_sentence.startswith('Failed to generate answer'):
        return f"Failed to generate answer: {first_sentence}. Please try again or contact support if the issue persists."
    
    return "Failed to generate answer: An unexpected error occurred. Please try again or contact support if the issue persists."

from ..prompts.mains_prompt import assemble_mains_prompt
from ..utils.context_retriever import retrieve_context_for_question
from ..utils.question_parser import parse_question_for_search
from ..utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
from ..utils.map_proxy import parse_and_generate_maps, check_map_service_health
from ..utils.cache_manager import get_cache_manager
from ..utils.answer_compressor import compress_answer
from ..utils.user_api_key import get_gemini_api_key_for_request
from ..core.config import settings
from ..core.deps import get_current_user
from ..models.user import User
from slowapi import Limiter
from slowapi.util import get_remote_address

# Import Gemini client
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

# OpenAI API key for question parser
OPENAI_API_KEY = settings.OPENAI_API_KEY

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# -- Utility small guards and postprocessors --
def enforce_diagrams(answer: str, required: int = 1) -> str:
    """
    Ensure at least `required` Mermaid diagrams exist in the answer.
    If not, insert a safe, minimal Mermaid diagram (flowchart)
    in a stable location (after first sub-heading and before bullets).
    """
    # quick check: count existing mermaid fenced blocks
    mermaid_count = answer.count("```mermaid")
    if mermaid_count >= required:
        return answer
    
    return answer

def count_words_excluding_visuals(text: str) -> int:
    """
    Count words in text, EXCLUDING all visual content:
    - Mermaid diagram blocks (```mermaid ... ```)
    - Map JSON blocks (```map-json ... ```)
    - Any code blocks (``` ... ```)
    - Base64 images (![...](data:image/...))
    - Inline base64 data
    
    This gives accurate word count for the actual prose content only.
    """
    cleaned_text = text
    
    # Remove ```mermaid ... ``` blocks
    cleaned_text = re.sub(r'```mermaid[\s\S]*?```', '', cleaned_text)
    
    # Remove ```map-json ... ``` blocks
    cleaned_text = re.sub(r'```map-json[\s\S]*?```', '', cleaned_text)
    
    # Remove any other code blocks
    cleaned_text = re.sub(r'```[\s\S]*?```', '', cleaned_text)
    
    # Remove base64 images: ![alt](data:image/...) 
    cleaned_text = re.sub(r'!\[[^\]]*\]\(data:image[^\)]+\)', '', cleaned_text)
    
    # Remove any remaining base64 data strings
    cleaned_text = re.sub(r'data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+', '', cleaned_text)
    
    # Count words in remaining prose
    return len(cleaned_text.split())

from ..utils.langsmith_tracer import trace_gemini

@trace_gemini("mains_answer_generation")
async def generate_answer(
    question: str,
    static_context: Optional[str] = None,
    dynamic_context: Optional[str] = None,
    word_count: int = 350,
    gemini_client: Optional[Any] = None,
    map_service_healthy: bool = True
) -> dict:
    """
    Top-level function to generate a mains answer using Gemini 2.5 Pro.
    
    Args:
        question: The mains question to answer
        static_context: Retrieved context 
        dynamic_context: Current affairs context
        word_count: Target word count for the answer
        gemini_client: GeminiClient instance (required)
        map_service_healthy: Whether map service is available (default: True)
    
    Returns:
        { "answer": str, "sources": list }
    """
    if not gemini_client:
        raise RuntimeError("GeminiClient is required for answer generation")

    # 1) Assemble prompt
    prompt_pair = assemble_mains_prompt(
        question=question,
        context=static_context,
        current_bullets=dynamic_context or "",  # Pass current affairs separately
        word_count=word_count
    )

    # 2) Call Gemini 2.5 Pro with timeout protection
    answer_text = ""
    sources = []

    try:
        # Compose final messages (system + user)
        system_msg = prompt_pair["system"]
        user_msg = prompt_pair["user"]

        logger.info(f"🤖 Calling Gemini 2.5 Pro for answer generation...")
        
        # Call Gemini with timeout protection (60 seconds)
        import asyncio
        try:
            response = await asyncio.wait_for(
                gemini_client.generate_response(
                    user_prompt=user_msg,
                    system_prompt=system_msg,
                    temperature=0.15,  # Low temperature for consistency
                    max_retries=2  # Retry only Gemini call, not the whole pipeline
                ),
                timeout=60.0  # 60 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("❌ Gemini call timed out after 60 seconds")
            raise RuntimeError("Answer generation timed out after 60 seconds. The AI service is taking longer than expected. Please try again with a simpler question or try again later.")
        
        answer_text = response.strip()
        logger.info(f"✅ Gemini response received: {len(answer_text)} chars")
        
    except RuntimeError:
        # Re-raise RuntimeError (timeout or other runtime issues)
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Gemini call failed: {error_msg}")
        # Clean error message for user display
        clean_msg = clean_gemini_error(error_msg)
        # Re-raise with cleaned message
        raise RuntimeError(clean_msg)

    # 3) Post-processing: ensure diagrams and word-count
    answer_text = enforce_diagrams(answer_text, required=1)
    
    # 4) Process map-json blocks (only if map service is healthy)
    if map_service_healthy:
        logger.info("🗺️  Checking for map-json blocks in answer...")
        try:
            answer_text = await parse_and_generate_maps(answer_text)
            logger.info("✅ Map processing completed")
        except Exception as e:
            logger.error(f"❌ Map processing failed: {str(e)}", exc_info=True)
            # Continue with answer even if map generation fails
    else:
        # Map service unavailable - skip map generation
        logger.warning("⚠️ Map service unavailable - skipping map generation")
        # Replace map-json blocks with error message
        import re
        map_json_pattern = r'```map-json[\s\S]*?```'
        if re.search(map_json_pattern, answer_text):
            answer_text = re.sub(
                map_json_pattern,
                '\n\n*[Map generation unavailable - map service is currently down]*\n\n',
                answer_text
            )
            logger.info("📝 Replaced map-json blocks with unavailability message")

    # 5) Pack result
    result = {
        "answer": answer_text,
        "sources": sources  # placeholder: can integrate actual source extraction later
    }
    return result

# FastAPI Router
router = APIRouter()

class MainsAnswerRequest(BaseModel):
    question: str
    word_count: int = 500

class MainsAnswerResponse(BaseModel):
    question: str
    answer: str
    compressed_answer: Optional[str] = None  # Compressed version (if applied)
    sources: List[Dict[str, Any]]
    word_count_actual: int
    word_count_compressed: Optional[int] = None  # Compressed word count

# Helper for connection check
async def check_connection(request: Request):
    """
    Check if client is still connected.
    If disconnected, raise exception to stop processing.
    """
    if await request.is_disconnected():
        logger.warning("⚠️ [CANCEL] Client disconnected, stopping generation")
        raise HTTPException(
            status_code=499, # Client Closed Request
            detail="Client closed request"
        )

@router.post("/generate")
@limiter.limit("20/hour")
async def generate_mains_answer(
    request: Request,
    mains_request: MainsAnswerRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue Mains Answer generation.
    Returns job_id for polling.
    """
    try:
        user_id = str(current_user.id) if current_user.id else current_user.email
        
        # 1. Check if we already have a specialized cached answer (fast return)
        # However, for polling consistency, we might just let the worker handle cache too,
        # OR we check cache here and return immediately if found?
        # If we return immediate result, the frontend needs to handle {job_id: ...} OR {result: ...}
        # To keep it simple, let's enqueue everything OR check cache and if hit, return a synthetic "completed" job?
        # Let's check cache here for speed.
        
        cache = get_cache_manager()
        model_version = "gemini-2.5-pro-v1"
        cached_answer_data = cache.get_cached_answer(mains_request.question, mains_request.word_count, model_version)
        
        if cached_answer_data:
             logger.info(f"⚡ [CACHE HIT] Immediate return for '{mains_request.question[:20]}...'")
             # We need to return a structure that the frontend polling logic can digest.
             # Or we return a "completed" status immediately?
             # Let's say we return { "job_id": "cached", "status": "completed", "result": ... }
             # But standard pattern is POST returns job_id, then GET status returns result.
             # Let's simulate a job. 
             job_id = f"cached-{uuid4()}"
             
             # We can write the result to Redis as if the job finished
             # We can write the result to Redis as if the job finished
             client = redis.Redis(host="localhost", port=6379, decode_responses=True)
             
             # Reconstruct result object
             result_obj = {
                "question": cached_answer_data["question"],
                "answer": cached_answer_data["answer"],
                "compressed_answer": cached_answer_data.get("compressed_answer"),
                "sources": cached_answer_data.get("sources", []),
                "word_count_actual": cached_answer_data.get("word_count_actual", 0),
                "word_count_compressed": cached_answer_data.get("word_count_compressed")
             }
             
             await client.set(f"job_status:{job_id}", "completed", ex=3600)
             await client.set(f"job_result:{job_id}", json.dumps(result_obj), ex=3600)
             await client.close()
             
             return {
                 "job_id": job_id,
                 "status": "completed",
                 "message": "Answer found in cache."
             }

        # 2. Get API Key
        try:
            gemini_api_key = get_gemini_api_key_for_request(current_user)
        except ValueError as e:
            raise HTTPException(400, str(e))
        
        if not gemini_api_key:
             raise HTTPException(400, "No Gemini API key available.")
             
        # 3. Enqueue Job
        job_id = str(uuid4())
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            raise HTTPException(500, "Job queue not initialized")
            
        await arq_pool.enqueue_job(
            "generate_mains_answer_task",
            _job_id=job_id,
            job_id=job_id,
            query=mains_request.question,
            user_id=user_id,
            word_count=mains_request.word_count,
            gemini_api_key=gemini_api_key
        )
        
        # 4. Set initial status
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        await client.set(f"job_status:{job_id}", "queued", ex=3600)
        await client.close()
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Answer generation started."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to enqueue mains answer: {e}")
        raise HTTPException(500, str(e))

@router.get("/status/{job_id}")
async def get_generation_status(job_id: str):
    """
    Poll status of answer generation.
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
            
        # Semantic logging for polling
        logger.info(f"MAINS_GENERATION - {job_id[:8]}... : {status.upper()}")
            
        await client.close()
        
        return {
            "job_id": job_id,
            "status": status,
            "result": result,
            "error": error
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/cancel/{job_id}")
async def cancel_generation(job_id: str):
    """
    Cancel running generation.
    """
    try:
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        return {"message": "Cancellation requested"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/history")
async def get_mains_answer_history(
    limit: int = 20,
    offset: int = 0,
    search: str = "",
    current_user: User = Depends(get_current_user)
):
    """
    Get user's history of mains answers from Redis.
    Returns list of {question, timestamp, word_count, id}.
    """
    try:
        cache = get_cache_manager()
        user_id = str(current_user.id) if current_user.id else current_user.email
        
        history, total, has_more = cache.get_user_history(user_id, limit=limit, offset=offset, search=search or None)
        return {
            "history": history,
            "limit": limit,
            "offset": offset,
            "search": search or "",
            "total": total,
            "has_more": has_more
        }
    except Exception as e:
        logger.error(f"❌ Failed to fetch history: {e}")
        return {
            "history": [],
            "limit": limit,
            "offset": offset,
            "search": search or "",
            "total": 0,
            "has_more": False
        }


@router.get("/history/answer", response_model=MainsAnswerResponse)
async def get_cached_mains_answer(
    question: str,
    word_count: int = 500,
    current_user: User = Depends(get_current_user)
):
    """
    Return a cached mains answer (no regeneration).
    Shows compressed answer if available to reduce payload size.
    """
    try:
        cache = get_cache_manager()
        model_version = "gemini-2.5-pro-v1"
        cached = cache.get_cached_answer(question, word_count, model_version)

        if not cached:
            raise HTTPException(
                status_code=404,
                detail="No cached answer found for this question and word count. Please generate again."
            )

        answer = cached.get("answer", "")
        compressed_answer = cached.get("compressed_answer")
        word_count_actual = cached.get("word_count_actual") or count_words_excluding_visuals(answer)
        word_count_compressed = cached.get("word_count_compressed")

        return MainsAnswerResponse(
            question=cached.get("question", question),
            answer=answer,
            compressed_answer=compressed_answer,
            sources=cached.get("sources", []),
            word_count_actual=word_count_actual,
            word_count_compressed=word_count_compressed
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to fetch cached answer: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cached answer")

# Quick test function
if __name__ == "__main__":
    q = "Discuss the causes and impacts of increasing forest fires in India and suggest mitigation measures."
    res = generate_answer(q, static_context="Use NCERT and Vision IAS notes on forests", word_count=300)
    print(res["answer"][:2000])
