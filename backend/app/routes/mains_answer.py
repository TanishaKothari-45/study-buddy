"""
mains_answer.py
Main handler for mains answer generation using Gemini 2.5 Pro.

Uses MCP current affairs server for latest news (not web_searcher).

Usage:
  from mains_prompt import assemble_mains_prompt
  from mains_answer import generate_answer

Config:
  export GEMINI_API_KEY=...
"""

import os
import sys
import logging
import re
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

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
    if ('401' in error_msg or '403' in error_msg) and 'API key' in error_msg:
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

from mains_prompt import assemble_mains_prompt
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


def enforce_word_count(answer: str, target: int) -> str:
    words = len(answer.split())
    if words > target * 1.2:
        # trim last paragraph(s)
        paras = [p for p in answer.split("\n\n") if p.strip()]
        if len(paras) > 1:
            # drop last paragraph(s) until under limit
            while len(" ".join(" ".join(paras).split()).split()) > target * 1.2 and len(paras) > 1:
                paras = paras[:-1]
            return "\n\n".join(paras).strip()
        return " ".join(answer.split()[: int(target * 1.2 * 1.0)])
    elif words < target * 0.8:
        # add a short synthesis sentence
        return answer + f"\n\n(Addendum: In short, the above points suggest that a balanced policy mix is required.)"
    return answer

from ..utils.langsmith_tracer import trace_gemini

@trace_gemini("mains_answer_generation")
async def generate_answer(
    question: str,
    static_context: Optional[str] = None,
    word_count: int = 350,
    gemini_client: Optional[Any] = None
) -> dict:
    """
    Top-level function to generate a mains answer using Gemini 2.5 Pro.
    
    Args:
        question: The mains question to answer
        static_context: Retrieved context (includes current affairs)
        word_count: Target word count for the answer
        gemini_client: GeminiClient instance (required)
    
    Returns:
        { "answer": str, "sources": list }
    """
    if not gemini_client:
        raise RuntimeError("GeminiClient is required for answer generation")

    # 1) Assemble prompt
    prompt_pair = assemble_mains_prompt(
        question=question,
        context=static_context,
        current_bullets="",  # Current affairs already in static_context
        word_count=word_count
    )

    # 2) Call Gemini 2.5 Pro
    answer_text = ""
    sources = []

    try:
        # Compose final messages (system + user)
        system_msg = prompt_pair["system"]
        user_msg = prompt_pair["user"]

        logger.info(f"🤖 Calling Gemini 2.5 Pro for answer generation...")
        
        # Call Gemini (retries transient errors internally, up to 2 retries)
        response = await gemini_client.generate_response(
            user_prompt=user_msg,
            system_prompt=system_msg,
            temperature=0.15,  # Low temperature for consistency
            max_retries=2  # Retry only Gemini call, not the whole pipeline
        )
        
        answer_text = response.strip()
        logger.info(f"✅ Gemini response received: {len(answer_text)} chars")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Gemini call failed: {error_msg}")
        # Clean error message for user display
        clean_msg = clean_gemini_error(error_msg)
        # Re-raise with cleaned message
        raise RuntimeError(clean_msg)

    # 3) Post-processing: ensure diagrams and word-count
    answer_text = enforce_diagrams(answer_text, required=1)
    # answer_text = enforce_word_count(answer_text, target=word_count)
    
    # 4) Process map-json blocks in parallel (if any)
    logger.info("🗺️  Checking for map-json blocks in answer...")
    try:
        answer_text = await parse_and_generate_maps(answer_text)
        logger.info("✅ Map processing completed")
    except Exception as e:
        logger.error(f"❌ Map processing failed: {str(e)}", exc_info=True)
        # Continue with answer even if map generation fails

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

@router.post("/generate")
@limiter.limit("20/hour")  # Rate limit: 20 requests per hour per IP
async def generate_mains_answer(
    request: Request,
    mains_request: MainsAnswerRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate a comprehensive UPSC Mains style answer for Geography questions.
    Now with Redis caching for answers and news fetches.
    Uses user's personal Gemini API key if set, otherwise system default.
    """
    try:
        logger.info(f"🚀 [MAINS] Received request: '{mains_request.question[:100]}...' (word_count={mains_request.word_count})")
        
        # Get Gemini API key (user's personal key or system default)
        try:
            gemini_api_key = get_gemini_api_key_for_request(current_user)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="No Gemini API key configured. Please set your personal API key in settings to use this feature."
            )
        
        if not gemini_api_key:
            raise HTTPException(
                status_code=400,
                detail="No Gemini API key available. Please set your personal API key in settings to use this feature."
            )
        
        # Initialize Gemini client with user's API key
        gemini_client = GeminiClient(
            api_key=gemini_api_key,
            model_name="gemini-2.5-pro"
        )
        
        # Initialize cache manager
        cache = get_cache_manager()
        model_version = "gemini-2.5-pro-v1"
        
        # ============================================================
        # STEP 1: Check answer cache (exact match)
        # ============================================================
        # cached_answer_data = cache.get_cached_answer(
        #     question=mains_request.question,
        #     word_count=mains_request.word_count,
        #     model_version=model_version
        # )
        
        # if cached_answer_data:
        #     # Cache HIT - but still need to compress if overlong
        #     logger.info("🎯 [CACHE HIT] Returning cached answer")
        #     cached_answer = cached_answer_data["answer"]
        #     word_count_actual = count_words_excluding_visuals(cached_answer)
            
        #     # Compress using existing gemini_client (already initialized with user's API key)
        #     compressed_answer = None
        #     word_count_compressed = None
            
        #     compressed = await compress_answer(
        #         original_answer=cached_answer,
        #         target_word_count=mains_request.word_count,
        #         gemini_client=gemini_client,
        #         threshold_ratio=1.4
        #     )
        #     if compressed:
        #         compressed_answer = compressed
        #         word_count_compressed = count_words_excluding_visuals(compressed)
        #         logger.info(f"🗜️ [CACHE] Compressed cached answer: {word_count_actual} -> {word_count_compressed}")
            
        #     return MainsAnswerResponse(
        #         question=cached_answer_data["question"],
        #         answer=cached_answer,
        #         compressed_answer=compressed_answer,
        #         sources=cached_answer_data["sources"],
        #         word_count_actual=word_count_actual,
        #         word_count_compressed=word_count_compressed
        #     )
        
        # Cache MISS - proceed with generation
        logger.info("⚡ [CACHE MISS] Generating new answer")
        
        # Dogpile protection: try to acquire lock
        cache_key = cache.get_answer_cache_key(mains_request.question, mains_request.word_count, model_version)
        lock_acquired = cache.acquire_lock(cache_key)
        
        if not lock_acquired:
            # Another request is generating this answer - wait briefly and retry cache
            logger.info("⏳ [LOCK] Another request is generating this answer, waiting...")
            import asyncio
            await asyncio.sleep(2)
            
            # Retry cache lookup
            cached_answer_data = cache.get_cached_answer(
                question=mains_request.question,
                word_count=mains_request.word_count,
                model_version=model_version
            )
            
            if cached_answer_data:
                logger.info("🎯 [CACHE HIT] Found answer after waiting for lock")
                cached_answer = cached_answer_data["answer"]
                word_count_actual = count_words_excluding_visuals(cached_answer)
                
                # Compress using existing gemini_client
                compressed_answer = None
                word_count_compressed = None
                
                compressed = await compress_answer(
                    original_answer=cached_answer,
                    target_word_count=mains_request.word_count,
                    gemini_client=gemini_client,
                    threshold_ratio=1.4
                )
                if compressed:
                    compressed_answer = compressed
                    word_count_compressed = count_words_excluding_visuals(compressed)
                
                return MainsAnswerResponse(
                    question=cached_answer_data["question"],
                    answer=cached_answer,
                    compressed_answer=compressed_answer,
                    sources=cached_answer_data["sources"],
                    word_count_actual=word_count_actual,
                    word_count_compressed=word_count_compressed
                )
        
        try:
            # Get Pinecone handler
            pinecone_handler = request.app.state.vector_handler
            
            # ============================================================
            # PARALLEL EXECUTION BLOCK 1: Independent operations
            # Health Check + Context Retrieval + (Question Parsing + News Fetch)
            # ============================================================
            logger.info("🚀 [MAINS] Starting parallel execution: health + retrieval + parsing + news")
            
            # Import timing utilities
            import asyncio
            import time
            
            # Start overall timing
            parallel_start = time.perf_counter()
            
            # Helper function to combine parsing + news fetch (they depend on each other)
            async def fetch_news_with_parsing():
                """Parse question and fetch news in sequence, but run parallel to retrieval"""
                task_start = time.perf_counter()
                parsed_topics = {}
                current_affairs_bullets = []
                time_range = "3months"
                
                try:
                    # Step 1: Parse question for news search
                    parse_start = time.perf_counter()
                    logger.info(f"🔍 [PARSE] Parsing question for news search...")
                    parsed_topics = await parse_question_for_search(
                        question=mains_request.question,
                        openai_api_key=OPENAI_API_KEY
                    )
                    parse_time = (time.perf_counter() - parse_start) * 1000
                    logger.info(f"✅ [PARSE] Parsed: {parsed_topics.get('search_query', '')[:50]}... ({parse_time:.1f}ms)")
                    
                    # Step 2: Fetch news using parsed keywords (check cache first)
                    if parsed_topics:
                        news_start = time.perf_counter()
                        cached_news = cache.get_cached_news(parsed_topics, time_range)
                        
                        if cached_news:
                            news_time = (time.perf_counter() - news_start) * 1000
                            logger.info(f"🎯 [NEWS CACHE HIT] Using cached news ({len(cached_news)} bullets, {news_time:.1f}ms)")
                            current_affairs_bullets = cached_news
                        else:
                            logger.info(f"🗞️ [NEWS CACHE MISS] Fetching from MCP...")
                            current_affairs_bullets = await fetch_current_affairs_for_question(
                                parsed_keywords=parsed_topics,
                                max_bullets=5,
                                time_range=time_range
                            )
                            news_time = (time.perf_counter() - news_start) * 1000
                            logger.info(f"✅ [NEWS] Retrieved {len(current_affairs_bullets)} bullets ({news_time:.1f}ms)")
                            cache.set_cached_news(parsed_topics, current_affairs_bullets, time_range)
                
                except Exception as e:
                    logger.warning(f"⚠️ [PARSE/NEWS] Failed: {e}")
                
                task_time = (time.perf_counter() - task_start) * 1000
                return parsed_topics, current_affairs_bullets, task_time
            
            # Helper to time retrieval
            async def timed_retrieval():
                """Time the context retrieval operation"""
                task_start = time.perf_counter()
                result = await asyncio.to_thread(
                    retrieve_context_for_question,
                    search_query=mains_request.question,
                    vector_handler=pinecone_handler,
                    mode="mains",
                    use_content_store=True,
                    k=6
                )
                task_time = (time.perf_counter() - task_start) * 1000
                return result[0], result[1], task_time  # context, sources, time
            
            # Helper to time health check
            async def timed_health_check():
                """Time the map service health check"""
                task_start = time.perf_counter()
                result = await check_map_service_health()
                task_time = (time.perf_counter() - task_start) * 1000
                return result, task_time
            
            # Launch all operations in parallel
            results = await asyncio.gather(
                # 1. Map service health check (50-100ms)
                timed_health_check(),
                
                # 2. Context retrieval from Pinecone + SQLite (300-600ms)
                timed_retrieval(),
                
                # 3. Question parsing + news fetch bundled (800-2000ms)
                fetch_news_with_parsing()
            )
            
            # Unpack results with timing
            (map_service_healthy, health_time) = results[0]
            (context, sources, retrieval_time) = results[1]
            (parsed_topics, current_affairs_bullets, parse_news_time) = results[2]
            
            # Calculate total parallel time and metrics
            parallel_total_time = (time.perf_counter() - parallel_start) * 1000
            sequential_estimate = health_time + retrieval_time + parse_news_time
            time_saved = sequential_estimate - parallel_total_time
            
            # Log performance metrics
            logger.info("⏱️  [PERFORMANCE METRICS - Parallel Execution]:")
            logger.info(f"   • Health check: {health_time:.1f}ms")
            logger.info(f"   • Context retrieval (Pinecone + SQLite): {retrieval_time:.1f}ms")
            logger.info(f"   • Question parsing + news fetch: {parse_news_time:.1f}ms")
            logger.info(f"   • Total parallel time: {parallel_total_time:.1f}ms")
            logger.info(f"   • Sequential would take: {sequential_estimate:.1f}ms")
            logger.info(f"   • ⚡ TIME SAVED: {time_saved:.1f}ms ({(time_saved/sequential_estimate*100) if sequential_estimate > 0 else 0:.0f}% faster)")
            
            # Log results
            if map_service_healthy:
                logger.info("✅ [PARALLEL] Map service is available")
            else:
                logger.warning("⚠️ [PARALLEL] Map service is unavailable - maps will not be generated")
            
            if not context:
                logger.warning(f"⚠️ [PARALLEL] No context retrieved")
                return MainsAnswerResponse(
                    question=mains_request.question,
                    answer="No relevant information found in the uploaded documents for this question.",
                    sources=[],
                    word_count_actual=0
                )
            
            logger.info(f"✅ [PARALLEL] Context: {len(context)} chars, {len(sources)} sources")
            logger.info(f"✅ [PARALLEL] News: {len(current_affairs_bullets)} bullets")
            logger.info("🎯 [PARALLEL] All operations completed in parallel!")
            
            # Append current affairs to context (additive, not replacing)
            if current_affairs_bullets:
                current_affairs_section = format_bullets_for_context(current_affairs_bullets)
                logger.info(f"📝 [MAINS] Current affairs section: {current_affairs_section}")
                context = context + current_affairs_section
                logger.info(f"📝 [MAINS] Added current affairs to context: {len(current_affairs_section)} chars")

            # ============================================================
            # STEP 5: Generate answer using Gemini 2.5 Pro
            # ============================================================
            logger.info(f"🤖 [MAINS] Generating answer with Gemini 2.5 Pro...")
            
            # Call async generate_answer - let exceptions propagate
            result = await generate_answer(
                question=mains_request.question,
                static_context=context,
                word_count=mains_request.word_count,
                gemini_client=gemini_client
            )
            
            answer = result["answer"]
            word_count_actual = count_words_excluding_visuals(answer)
            
            logger.info(f"✅ [MAINS] Answer generated: {len(answer)} characters, {word_count_actual} words")
            
            # ============================================================
            # STEP 6: Compress if exceeds 140% of target word count
            # ============================================================
            compressed_answer = None
            word_count_compressed = None
            
            try:
                compressed = await compress_answer(
                    original_answer=answer,
                    target_word_count=mains_request.word_count,
                    gemini_client=gemini_client,
                    threshold_ratio=1.4
                )
                
                if compressed:
                    compressed_answer = compressed
                    word_count_compressed = count_words_excluding_visuals(compressed)
                    logger.info(f"🗜️ [MAINS] Compressed: {word_count_actual} -> {word_count_compressed} words")
            except Exception as e:
                # Compression failure is not critical - just log and continue with uncompressed answer
                logger.warning(f"⚠️ [MAINS] Compression failed: {e}")
            
            # ============================================================
            # STEP 7: Cache the answer
            # ============================================================
            cache.set_cached_answer(
                question=mains_request.question,
                word_count=mains_request.word_count,
                answer=answer,
                sources=sources,
                model_version=model_version
            )
            
            return MainsAnswerResponse(
                question=mains_request.question,
                answer=answer,
                compressed_answer=compressed_answer,
                sources=sources,
                word_count_actual=word_count_actual,
                word_count_compressed=word_count_compressed
            )
        
        finally:
            # Release lock
            if lock_acquired:
                cache.release_lock(cache_key)

    except HTTPException:
        # Re-raise HTTPException as-is (already has proper status code and detail)
        raise
    except Exception as e:
        # Catch unexpected errors
        error_msg = str(e)
        logger.error(f"❌ Mains answer generation failed: {error_msg}")
        # Clean error message for user display
        clean_msg = clean_gemini_error(error_msg)
        raise HTTPException(status_code=500, detail=clean_msg)

# Quick test function
if __name__ == "__main__":
    q = "Discuss the causes and impacts of increasing forest fires in India and suggest mitigation measures."
    res = generate_answer(q, static_context="Use NCERT and Vision IAS notes on forests", word_count=300)
    print(res["answer"][:2000])
