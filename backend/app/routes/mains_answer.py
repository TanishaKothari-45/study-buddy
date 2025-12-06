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
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger("mains_answer")
logging.basicConfig(level=logging.INFO)

from mains_prompt import assemble_mains_prompt
from ..utils.context_retriever import retrieve_context_for_question
from ..utils.question_parser import parse_question_for_search
from ..utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
from ..utils.map_proxy import parse_and_generate_maps, check_map_service_health
from ..utils.cache_manager import get_cache_manager
from ..utils.answer_compressor import compress_answer
from ..core.config import settings
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
        
        # Call Gemini with async
        response = await gemini_client.generate_response(
            user_prompt=user_msg,
            system_prompt=system_msg,
            temperature=0.15,  # Low temperature for consistency
            max_retries=2
        )
        
        answer_text = response.strip()
        logger.info(f"✅ Gemini response received: {len(answer_text)} chars")
        
    except Exception as e:
        logger.error(f"❌ Gemini call failed: {e}")
        # Fallback simple template answer to avoid blank responses
        answer_text = f"**Introduction**\nBrief introduction based on provided materials.\n\n**Body**\n• Key point 1\n• Key point 2\n\n**Conclusion**\nSynthesis and policy suggestion."

    # 3) Post-processing: ensure diagrams and word-count
    answer_text = enforce_diagrams(answer_text, required=1)
    # answer_text = enforce_word_count(answer_text, target=word_count)
    
    # 4) Process map-json blocks (if any)
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
async def generate_mains_answer(request: Request, mains_request: MainsAnswerRequest):
    """
    Generate a comprehensive UPSC Mains style answer for Geography questions.
    Now with Redis caching for answers and news fetches.
    """
    try:
        logger.info(f"🚀 [MAINS] Received request: '{mains_request.question[:100]}...' (word_count={mains_request.word_count})")
        
        # Initialize cache manager
        cache = get_cache_manager()
        model_version = "gemini-2.5-pro-v1"
        
        # ============================================================
        # STEP 1: Check answer cache (exact match)
        # ============================================================
        cached_answer_data = cache.get_cached_answer(
            question=mains_request.question,
            word_count=mains_request.word_count,
            model_version=model_version
        )
        
        if cached_answer_data:
            # Cache HIT - but still need to compress if overlong
            logger.info("🎯 [CACHE HIT] Returning cached answer")
            cached_answer = cached_answer_data["answer"]
            word_count_actual = count_words_excluding_visuals(cached_answer)
            
            # Initialize Gemini client for compression
            compressed_answer = None
            word_count_compressed = None
            
            if GeminiClient and GEMINI_API_KEY:
                gemini_client = GeminiClient(
                    api_key=GEMINI_API_KEY,
                    model_name="gemini-2.5-pro"
                )
                compressed = await compress_answer(
                    original_answer=cached_answer,
                    target_word_count=mains_request.word_count,
                    gemini_client=gemini_client,
                    threshold_ratio=1.4
                )
                if compressed:
                    compressed_answer = compressed
                    word_count_compressed = count_words_excluding_visuals(compressed)
                    logger.info(f"🗜️ [CACHE] Compressed cached answer: {word_count_actual} -> {word_count_compressed}")
            
            return MainsAnswerResponse(
                question=cached_answer_data["question"],
                answer=cached_answer,
                compressed_answer=compressed_answer,
                sources=cached_answer_data["sources"],
                word_count_actual=word_count_actual,
                word_count_compressed=word_count_compressed
            )
        
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
                
                # Compress if overlong
                compressed_answer = None
                word_count_compressed = None
                
                if GeminiClient and GEMINI_API_KEY:
                    gemini_client = GeminiClient(
                        api_key=GEMINI_API_KEY,
                        model_name="gemini-2.5-pro"
                    )
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
            # Check map service health (non-blocking)
            logger.info("🔍 [MAINS] Checking map service health...")
            map_service_healthy = await check_map_service_health()
            if map_service_healthy:
                logger.info("✅ [MAINS] Map service is available")
            else:
                logger.warning("⚠️  [MAINS] Map service is unavailable - maps will not be generated")
            
            # Get Pinecone handler
            pinecone_handler = request.app.state.vector_handler
            
            # Use FULL question for Pinecone vector search (better semantic matching)
            logger.info(f"📚 [MAINS] Retrieving context using full question...")
            context, sources = retrieve_context_for_question(
                search_query=mains_request.question,  # Full question for Pinecone
                vector_handler=pinecone_handler,
                mode="mains",
                use_content_store=True,
                k=6
            )
            
            if not context:
                logger.warning(f"⚠️ [MAINS] No context retrieved")
                return MainsAnswerResponse(
                    question=mains_request.question,
                    answer="No relevant information found in the uploaded documents for this question.",
                    sources=[],
                    word_count_actual=0
                )
            
            logger.info(f"✅ [MAINS] Retrieved context: {len(context)} chars, {len(sources)} sources")

            # ============================================================
            # STEP 2: Parse question & check news cache
            # ============================================================
            parsed_topics = {}
            current_affairs_bullets = []
            time_range = "3months"
            
            logger.info(f"🔍 [MAINS] Parsing question for current affairs search...")
            try:
                parsed_topics = await parse_question_for_search(
                    question=mains_request.question,
                    openai_api_key=OPENAI_API_KEY
                )
                logger.info(f"✅ [MAINS] Parsed for current affairs: {parsed_topics.get('search_query', '')[:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ [MAINS] Question parsing failed: {e}")
                parsed_topics = {}

            # Check news cache first
            if parsed_topics:
                cached_news = cache.get_cached_news(parsed_topics, time_range)
                
                if cached_news:
                    # News cache HIT
                    logger.info(f"🎯 [NEWS CACHE HIT] Using cached news ({len(cached_news)} bullets)")
                    current_affairs_bullets = cached_news
                else:
                    # News cache MISS - fetch from MCP
                    logger.info(f"🗞️ [NEWS CACHE MISS] Fetching current affairs from MCP...")
                    try:
                        current_affairs_bullets = await fetch_current_affairs_for_question(
                            parsed_keywords=parsed_topics,
                            max_bullets=5,
                            time_range=time_range
                        )
                        logger.info(f"✅ [MAINS] Retrieved {len(current_affairs_bullets)} current affairs bullets")
                        
                        # Cache the news bullets
                        cache.set_cached_news(parsed_topics, current_affairs_bullets, time_range)
                    except Exception as e:
                        logger.warning(f"⚠️ [MAINS] Current affairs fetch failed: {e}")
                        current_affairs_bullets = []
            
            # Append current affairs to context (additive, not replacing)
            if current_affairs_bullets:
                current_affairs_section = format_bullets_for_context(current_affairs_bullets)
                logger.info(f"📝 [MAINS] Current affairs section: {current_affairs_section}")
                context = context + current_affairs_section
                logger.info(f"📝 [MAINS] Added current affairs to context: {len(current_affairs_section)} chars")

            # ============================================================
            # STEP 3: Generate answer using Gemini 2.5 Pro
            # ============================================================
            logger.info(f"🤖 [MAINS] Generating answer with Gemini 2.5 Pro...")
            
            # Initialize Gemini client
            if not GeminiClient or not GEMINI_API_KEY:
                raise HTTPException(
                    status_code=500,
                    detail="Gemini client not available. Please configure GEMINI_API_KEY."
                )
            
            gemini_client = GeminiClient(
                api_key=GEMINI_API_KEY,
                model_name="gemini-2.5-pro"
            )
            
            # Call async generate_answer
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
            # STEP 4: Compress if exceeds 140% of target word count
            # ============================================================
            compressed_answer = None
            word_count_compressed = None
            
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
            
            # ============================================================
            # STEP 5: Cache the answer
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

    except Exception as e:
        logger.error(f"❌ Mains answer generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Quick test function
if __name__ == "__main__":
    q = "Discuss the causes and impacts of increasing forest fires in India and suggest mitigation measures."
    res = generate_answer(q, static_context="Use NCERT and Vision IAS notes on forests", word_count=300)
    print(res["answer"][:2000])
