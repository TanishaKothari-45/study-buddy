"""
worker.py

Arq Worker for background job processing.
Handles: Mock Test Generation, Answer Evaluation, Mains Answer Generation.

All jobs use Redis for status tracking for consistency.
User locks prevent concurrent API calls per user (budget/rate limit protection).

Usage:
    arq app.worker.WorkerSettings
"""

import asyncio
import json
import logging
import os
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from arq.connections import RedisSettings
from redis.asyncio import Redis
from redis.asyncio.lock import Lock as RedisLock
from uuid import uuid4
import re
import time

from .core.config import settings
from .utils.pinecone_handler import PineconeHandler
from .gemini_core.gemini_client import GeminiClient
from .utils.cache_manager import get_cache_manager
from .utils.langsmith_tracer import trace_chain
from .core.langsmith_config import configure_langsmith

# Initialize LangSmith
configure_langsmith()

logger = logging.getLogger(__name__)

# Redis Settings
REDIS_SETTINGS = RedisSettings(host="localhost", port=6379)

# Job status TTL (1 hour)
JOB_STATUS_TTL = 3600


# ============================================================
# WORKER LIFECYCLE
# ============================================================

async def startup(ctx):
    """Initialize resources for the worker"""
    logger.info("🚀 Worker starting up...")
    
    # Initialize Redis client for locking/cancellation/status
    ctx["redis"] = Redis(host="localhost", port=6379, decode_responses=True)
    
    # Initialize Pinecone handler (shared for all tasks)
    if settings.USE_PINECONE:
        ctx["pinecone_handler"] = PineconeHandler()
        logger.info("✅ Pinecone handler initialized")

    # Cleanup any dangling locks from previous runs
    try:
        keys = await ctx["redis"].keys("lock:user:*")
        if keys:
            await ctx["redis"].delete(*keys)
            logger.info(f"🧹 Cleared {len(keys)} dangling user locks")
    except Exception as e:
        logger.warning(f"⚠️ Failed to cleanup dangling locks: {e}")
    
    logger.info("✅ Worker initialized")


async def shutdown(ctx):
    """Clean up resources"""
    logger.info("🛑 Worker shutting down...")
    await ctx["redis"].close()
    logger.info("✅ Worker shutdown complete")


async def check_cancellation(ctx, job_id: str):
    """Check if job should be cancelled"""
    if await ctx["redis"].exists(f"cancel:{job_id}"):
        logger.info(f"🚫 Job {job_id} cancelled by user")
        raise asyncio.CancelledError("Job cancelled by user")


# ============================================================
# REDIS JOB STATUS HELPERS
# ============================================================

async def set_job_status(redis: Redis, job_id: str, status: str, **extra_data):
    """Set job status in Redis with optional extra data"""
    await redis.set(f"job_status:{job_id}", status, ex=JOB_STATUS_TTL)
    
    # Store extra data if provided
    for key, value in extra_data.items():
        if value is not None:
            if isinstance(value, (dict, list)):
                await redis.set(f"job_{key}:{job_id}", json.dumps(value), ex=JOB_STATUS_TTL)
            else:
                await redis.set(f"job_{key}:{job_id}", str(value), ex=JOB_STATUS_TTL)


async def set_job_result(redis: Redis, job_id: str, result: dict):
    """Set job result in Redis"""
    await redis.set(f"job_result:{job_id}", json.dumps(result), ex=JOB_STATUS_TTL)
    await redis.set(f"job_status:{job_id}", "completed", ex=JOB_STATUS_TTL)


async def set_job_error(redis: Redis, job_id: str, error: str):
    """Set job error in Redis"""
    await redis.set(f"job_error:{job_id}", error, ex=JOB_STATUS_TTL)
    await redis.set(f"job_status:{job_id}", "failed", ex=JOB_STATUS_TTL)


# ============================================================
# SHARED PIPELINE HELPER
# ============================================================

@trace_chain("shared_enriched_pipeline")
async def run_enriched_pipeline(
    ctx: dict,
    job_id: str,
    query: str,
    gemini_api_key: Optional[str] = None,
    k: int = 6,
    fetch_k: int = 20,
    max_total_tokens: int = 32000
) -> Dict[str, Any]:
    """
    Shared retrieval & news pipeline for Mains and Evaluation.
    Parallel execution: Health + Retrieval (Top 20->6) + News (Parsing+Fetching).
    Includes smart truncation.
    """
    from .utils.context_retriever import retrieve_context_for_question
    from .utils.question_parser import parse_question_for_search
    from .utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
    from .utils.map_proxy import check_map_service_health
    from .utils.cache_manager import get_cache_manager
    from .utils.smart_truncator import truncate_with_token_budget
    
    redis = ctx["redis"]
    pinecone_handler = ctx.get("pinecone_handler")
    cache = get_cache_manager()
    
    # 1. Health check
    async def timed_health_check():
         try:
             return await check_map_service_health()
         except Exception as e:
             logger.warning(f"Health check failed: {e}")
             return False
             
    # 2. Retrieval (Top 20 -> 6 with re-ranking)
    async def timed_retrieval():
        try:
            return await asyncio.to_thread(
                retrieve_context_for_question,
                search_query=query,
                vector_handler=pinecone_handler,
                mode="mains",
                use_content_store=True,
                k=k,
                re_rank=True,
                fetch_k=fetch_k
            )
        except Exception as e:
            logger.warning(f"Retrieval failed: {e}")
            return "", []

    # 3. News (Parsing + Fetching)
    async def fetch_news_with_parsing():
        try:
            # Step A: Parse question (Fix keyword: use gemini_api_key)
            parsed = await parse_question_for_search(query, gemini_api_key=gemini_api_key)
            bullets = []
            if parsed:
                # Step B: Check news cache
                time_range = "3months"
                cached_news = None
                if cache:
                    cached_news = cache.get_cached_news(parsed, time_range)
                
                if cached_news:
                    bullets = cached_news
                    logger.info(f"🎯 [JOB {job_id}] News cache hit")
                else:
                    # Step C: Fetch from MCP
                    bullets = await fetch_current_affairs_for_question(
                        parsed, max_bullets=5, time_range=time_range, gemini_api_key=gemini_api_key
                    )
                    if cache and bullets:
                        cache.set_cached_news(parsed, bullets, time_range)
            return parsed, bullets
        except Exception as e:
            logger.warning(f"News pipeline failed: {e}")
            return {}, []

    # Run in parallel
    logger.info(f"🚀 [JOB {job_id}] Running shared enriched pipeline in parallel...")
    results = await asyncio.gather(
        timed_health_check(),
        timed_retrieval(),
        fetch_news_with_parsing()
    )
    
    map_service_healthy = results[0]
    raw_context, sources = results[1]
    parsed_topics, current_affairs_bullets = results[2]
    
    # Format news bullets
    current_affairs_text = ""
    if current_affairs_bullets:
        current_affairs_text = format_bullets_for_context(current_affairs_bullets)
        
    # Apply Smart Truncation
    logger.info(f"📊 [JOB {job_id}] Applying smart truncation...")
    context_trim, current_trim = truncate_with_token_budget(
        static_context=raw_context,
        current_affairs=current_affairs_text,
        question=query,
        system_prompt_tokens=1500,
        max_total_tokens=max_total_tokens
    )

    return {
        "context": context_trim or "[No specific context retrieved - use general knowledge]",
        "current_affairs": current_trim,
        "sources": sources,
        "parsed_topics": parsed_topics,
        "current_affairs_bullets": current_affairs_bullets,
        "map_service_healthy": map_service_healthy
    }


# ============================================================
# TASK 1: MOCK TEST GENERATION
# ============================================================

@trace_chain("mock_test_pipeline")
async def generate_mock_test_task(
    ctx,
    job_id: str,
    num_questions: int,
    topics: List[str],
    difficulty: str,
    api_key: str
):
    """
    Generate mock test questions using FULL pipeline.
    This implements the complete generate_async_pipeline logic in the worker.
    """
    logger.info(f"🔨 [JOB {job_id}] Starting mock test generation")
    redis = ctx["redis"]

    await set_job_status(redis, job_id, "processing",
                         num_questions=num_questions,
                         topics=topics,
                         difficulty=difficulty)

    try:
        await check_cancellation(ctx, job_id)

        # Import required functions from mock_test route
        from .routes.mock_test import (
            hybrid_retrieve_for_mock_test,
            generate_micro_batches,
            semantic_deduplicate,
            fill_gaps_targeted
        )
        from .core.config import settings

        pinecone_handler = ctx["pinecone_handler"]

        # Step 1: Retrieve chunks (scaled)
        logger.info(f"📚 [JOB {job_id}] Step 1: Retrieving content chunks")
        try:
            pyq_chunks, content_chunks = hybrid_retrieve_for_mock_test(
                pinecone_handler=pinecone_handler,
                topics=topics,
                num_questions=num_questions,
                difficulty=difficulty
            )
            logger.info(f"✅ [JOB {job_id}] Retrieved {len(content_chunks)} content chunks, {len(pyq_chunks)} PYQ chunks")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id}] Retrieval failed: {e}", exc_info=True)
            raise

        all_chunks = content_chunks  # Use content chunks for generation

        if len(all_chunks) < 10:
            raise Exception(f"Insufficient content: only {len(all_chunks)} chunks retrieved")

        await check_cancellation(ctx, job_id)

        from .utils.job_tracker import get_job_store
        job_store = get_job_store()

        # Step 2: Generate micro-batches
        logger.info(f"🔨 [JOB {job_id}] Step 2: Generating micro-batches")
        try:
            all_questions = await generate_micro_batches(
                all_chunks=all_chunks,
                num_questions=num_questions,
                difficulty=difficulty,
                topics=topics,
                api_key=api_key,
                job_id=job_id,
                job_store=job_store
            )
            logger.info(f"✅ [JOB {job_id}] Generated {len(all_questions)} total questions")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id}] Batch generation failed: {e}", exc_info=True)
            raise

        await check_cancellation(ctx, job_id)

        # Step 3: Semantic deduplication
        logger.info(f"🔍 [JOB {job_id}] Step 3: Semantic deduplication")
        try:
            # Get embedder from pinecone handler
            embedder = pinecone_handler.embedder if hasattr(pinecone_handler, 'embedder') else None
            if not embedder:
                logger.warning(f"⚠️ [JOB {job_id}] No embedder available, skipping deduplication")
                unique_questions = all_questions
            else:
                unique_questions = await semantic_deduplicate(
                    questions=all_questions,
                    embedder=embedder,
                    threshold=0.88
                )
            logger.info(f"✅ [JOB {job_id}] After deduplication: {len(unique_questions)} unique questions")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id}] Deduplication failed: {e}", exc_info=True)
            unique_questions = all_questions  # Continue with original questions

        await check_cancellation(ctx, job_id)

        # Step 4: Gap-fill if needed
        if len(unique_questions) < num_questions:
            logger.info(f"🔧 [JOB {job_id}] Step 4: Gap-filling ({len(unique_questions)}/{num_questions})")
            try:
                gap_fill = await fill_gaps_targeted(
                    current_questions=unique_questions,
                    target=num_questions,
                    difficulty=difficulty,
                    topics=topics,
                    api_key=api_key,
                    job_id=job_id,
                    pinecone_handler=pinecone_handler
                )
                unique_questions.extend(gap_fill)
                logger.info(f"✅ [JOB {job_id}] After gap-fill: {len(unique_questions)} questions")
            except Exception as e:
                logger.error(f"💥 [JOB {job_id}] Gap-fill failed: {e}", exc_info=True)
                # Continue with what we have

        # Step 5: Final selection and shuffle
        logger.info(f"🎲 [JOB {job_id}] Step 5: Final selection and shuffle")
        if len(unique_questions) > num_questions:
            # Simple random selection
            import random
            unique_questions = random.sample(unique_questions, num_questions)

        import random
        random.shuffle(unique_questions)

        # Convert to final format
        final_questions = []
        for i, q in enumerate(unique_questions):
            final_questions.append({
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "correct_answer": q.get("correct_answer", "A"),
                "explanation": q.get("explanation", ""),
                "source": {
                    "filename": "Generated",
                    "chapter": "Mock Test",
                    "section": f"Question {i+1}",
                    "question_id": f"{job_id}_q{i+1}",
                    "topics": topics,
                    "difficulty": difficulty
                }
            })

        # Build result
        result = {
            "questions": final_questions,
            "total_marks": len(final_questions) * 2,
            "time_allowed": f"{len(final_questions) * 1.2:.0f} minutes",
            "instructions": [
                "Attempt all questions.",
                f"Each question carries 2 marks.",
                f"Total marks: {len(final_questions) * 2}.",
                "Negative marking: -0.67 marks (1/3 of 2 marks) for each wrong answer.",
                "No marks deducted for unanswered questions.",
                "Choose the most appropriate option.",
                "Questions are based on your uploaded study materials."
            ]
        }

        await set_job_result(redis, job_id, result)
        logger.info(f"✅ [JOB {job_id}] Completed - {len(final_questions)} questions generated")

    except asyncio.CancelledError:
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] Failed: {e}", exc_info=True)
        await set_job_error(redis, job_id, str(e))
    finally:
        await redis.delete(f"cancel:{job_id}")


# ============================================================
# TASK 2: ANSWER EVALUATION (Full Implementation)
# ============================================================

@trace_chain("evaluation_pipeline")
async def evaluate_answer_task(
    ctx, 
    job_id: str, 
    file_paths: List[str], 
    question: str, 
    user_id: str, 
    gemini_api_key: str
):
    """
    Evaluate student answer using Gemini.
    Full 6-step pipeline from original evaluate_answer.py.
    """
    logger.info(f"📝 [JOB {job_id}] Starting evaluation for user {user_id}")
    redis = ctx["redis"]
    status_key = f"job_status:{job_id}"
    await redis.set(status_key, "processing")
    
    try:
        await check_cancellation(ctx, job_id)
        
        # Initialize Gemini Client
        gemini_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_PRO)
        
        # Import models
        from .models.evaluation import EvaluationResponse

        # Import utilities directly
        from .utils.context_retriever import retrieve_context_for_question
        from .utils.question_parser import parse_question_for_search
        from .utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
        from .utils.map_proxy import parse_and_generate_maps
        from .utils.cache_manager import get_cache_manager
        from .utils.answer_compressor import compress_answer
        
        # Import shared prompt
        try:
             from .prompts.shared_mains_prompts import get_evaluation_system_prompt
             system_prompt = get_evaluation_system_prompt()
        except ImportError:
             logger.warning("⚠️ Using fallback generic system prompt")
             system_prompt = "You are an expert evaluator. Improve the answer using the context provided."

        # File type check
        all_is_pdf = all(f.lower().endswith('.pdf') for f in file_paths)
        all_is_image = all(f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) for f in file_paths)

        # ============================================================
        # STEP 1: Extract question from files if not provided (OCR)
        # ============================================================
        # Retrieve logic - running Phase 1 (No User Lock needed for this Gemini call? 
        # Actually this Gemini call uses user key, so technically it SHOULD be locked if strict.
        # But retrieval is heavy. Let's do OCR first. OCR is Gemini Flash usually or can use Pro.
        # For safety/simplicity, we can lock. BUT if we lock here, we block retrieval.
        # Decision: OCR using Gemini Flash or Pro fast. Let's run it without lock OR assume partial concurrency allowed.
        # User requested PRE-LOCK retrieval. So OCR must happen before retrieval.
        # If we use user key, we face rate limit. 
        # To strictly follow "retrieve before lock", we need identifying query first.
        # Compromise: We lock for OCR briefly, then unlock for retrieval, then lock for generation.
        # OR: We just run OCR. Rate limits will handle it (Arq retries).
        
        identified_question = question
        
        if not identified_question:
            logger.info(f"📝 [JOB {job_id}] STEP 1: Extracting question from files...")
            try:
                question_prompt = "Read the handwritten answer and identify the QUESTION. Return ONLY the question text."
                
                # ACQUIRE LOCK (Briefly for OCR)
                # We reuse the client but need to ensure we don't block heavily.
                # Since we already initialized client, we can use it.
                # However, OCR is a generation call.
                lock_key = f"lock:user:{user_id}"
                
                # Acquiring lock for OCR (60s timeout to handle overlaps)
                lock = RedisLock(redis, lock_key, timeout=60)
                if await lock.acquire(blocking=True, blocking_timeout=60):
                    try:
                        if all_is_pdf:
                            question_response = await gemini_client.generate_response(question_prompt, pdf_path=file_paths[0], temperature=0.0)
                        else:
                            question_response = await gemini_client.generate_response(question_prompt, image_path=file_paths[0], temperature=0.0)
                        
                        identified_question = question_response.strip()
                        logger.info(f"✅ [JOB {job_id}] Identified question: {identified_question[:100]}...")
                    finally:
                        await lock.release()
                else:
                    # Non-negotiable step: if we can't get the question, we can't proceed.
                    # Raise error to allow worker to retry the job.
                    raise Exception("Could not acquire user lock for OCR after 60s")
            except Exception as e:
                logger.warning(f"⚠️ [JOB {job_id}] Failed to identify question: {e}")
                identified_question = "Question not identified"
        else:
            logger.info(f"📝 [JOB {job_id}] STEP 1: Using provided question")
        
        await check_cancellation(ctx, job_id)
        
        # ============================================================
        # PHASE 2: ALIGNED RETRIEVAL & NEWS PIPELINE
        # ============================================================
        # We reuse the shared pipeline for consistency with Mains Answer
        pipeline_result = await run_enriched_pipeline(
            ctx=ctx,
            job_id=job_id,
            query=identified_question,
            gemini_api_key=gemini_api_key
        )
        
        context = pipeline_result["context"]
        sources = pipeline_result["sources"]
        map_service_healthy = pipeline_result["map_service_healthy"]
        current_affairs_bullets = pipeline_result["current_affairs_bullets"]
        
        # Merge current affairs into context if present (for evaluation prompt)
        if pipeline_result["current_affairs"]:
            context = context + "\n\n**RECENT NEWS/CURRENT AFFAIRS**:\n" + pipeline_result["current_affairs"]
        
        await check_cancellation(ctx, job_id)
        
        # ============================================================
        # STEP 5: Load training examples (few-shot learning)
        # ============================================================
        training_examples = []
        try:
            training_data_file = Path(__file__).parent.parent.parent / "data" / "training_examples.json"
            if training_data_file.exists():
                with open(training_data_file, 'r', encoding='utf-8') as f:
                    training_data = json.load(f)
                    all_examples = training_data.get("training_examples", [])
                    training_examples = all_examples[-3:] if len(all_examples) > 3 else all_examples
                    logger.info(f"✅ [JOB {job_id}] Loaded {len(training_examples)} training examples")
        except Exception as e:
            logger.debug(f"No training examples loaded: {e}")

        # ============================================================
        # STEP 6: Build enhanced prompt
        # ============================================================
        logger.info(f"📝 [JOB {job_id}] STEP 6: Building enhanced prompt...")
        word_count_int = 350
        user_prompt = _build_evaluation_prompt(
            identified_question=identified_question,
            context=context,
            training_examples=training_examples,
            word_count=word_count_int
        )
        
        # ============================================================
        # STEP 7: Call Gemini WITH USER LOCK
        # ============================================================
        logger.info(f"🤖 [JOB {job_id}] STEP 7: Calling Gemini with user lock...")
        
        lock_key = f"lock:user:{user_id}"
        lock = RedisLock(redis, lock_key, timeout=120)  # 2 min timeout for evaluation
        acquired = await lock.acquire(blocking=True, blocking_timeout=70)
        
        if not acquired:
            raise Exception(f"Could not acquire lock for user {user_id} - another job may be running")
        
        try:
            await check_cancellation(ctx, job_id)
            logger.info(f"🔐 [JOB {job_id}] Lock acquired, calling Gemini...")
            
            # Call Gemini with files
            if all_is_pdf:
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    pdf_path=file_paths,
                    temperature=0.2,
                    max_retries=3
                )
            elif all_is_image:
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    image_path=file_paths,
                    temperature=0.2,
                    max_retries=3
                )
            else:
                # Mixed types - use first file
                if file_paths[0].lower().endswith('.pdf'):
                    response_text = await gemini_client.generate_response(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        pdf_path=file_paths[0],
                        temperature=0.2,
                        max_retries=3
                    )
                else:
                    response_text = await gemini_client.generate_response(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        image_path=file_paths[0],
                        temperature=0.2,
                        max_retries=3
                    )
            
            logger.info(f"✅ [JOB {job_id}] Received response: {len(response_text)} chars")
        finally:
            await lock.release()
            logger.info(f"🔓 [JOB {job_id}] Lock released")
        
        # ============================================================
        # STEP 8: Parse response
        # ============================================================
        logger.info(f"🔍 [JOB {job_id}] STEP 8: Parsing response...")
        improved_answer, feedback = _parse_evaluation_response(response_text)
        
        # ============================================================
        # STEP 9: Process maps (optional)
        # ============================================================
        logger.info(f"🗺️ [JOB {job_id}] STEP 9: Processing maps...")
        try:
            improved_answer = await parse_and_generate_maps(improved_answer)
        except Exception as e:
            logger.debug(f"Map processing skipped: {e}")
        
        # ============================================================
        # STEP 10: Compression & Save Result
        # ============================================================
        logger.info(f"🗜️ [JOB {job_id}] STEP 10: Applying compression & saving result...")
        
        # Calculate word count for original improved answer
        word_count_actual = count_words_excluding_visuals(improved_answer)
        
        # Use Flash for compression
        flash_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_FLASH)
        
        compressed_answer = None
        word_count_compressed = None
        
        try:
            compressed = await compress_answer(
                original_answer=improved_answer,
                target_word_count=word_count_int,
                gemini_client=flash_client,
                threshold_ratio=1.4
            )
            if compressed:
                compressed_answer = compressed
                word_count_compressed = count_words_excluding_visuals(compressed)
                logger.info(f"✅ [JOB {job_id}] Compression successful: {word_count_actual} -> {word_count_compressed} words")
        except Exception as e:
            logger.warning(f"⚠️ [JOB {job_id}] Compression failed: {e}")

        result = {
            "question": identified_question,
            "student_answer": "Answer extracted by Gemini",
            "improved_answer": improved_answer,
            "compressed_answer": compressed_answer,
            "feedback": feedback,
            "sources": sources,
            "parsed_topics": parsed_topics,
            "current_affairs_count": len(current_affairs_bullets),
            "word_count_actual": word_count_actual,
            "word_count_compressed": word_count_compressed,
            "success": True
        }
        
        await set_job_result(redis, job_id, result)
        logger.info(f"✅ [JOB {job_id}] Evaluation complete")
        
    except asyncio.CancelledError:
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] Failed: {e}", exc_info=True)
        await set_job_error(redis, job_id, str(e))
    finally:
        # Cleanup files
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        # Cleanup directory
        if file_paths:
            try:
                os.rmdir(Path(file_paths[0]).parent)
            except:
                pass
        
        await redis.delete(f"cancel:{job_id}")


def _build_evaluation_prompt(
    identified_question: str,
    context: str,
    training_examples: List[dict],
    word_count: int
) -> str:
    """Build the evaluation user prompt"""
    parts = [f"**QUESTION**: {identified_question}\n\n"]
    
    if context:
        # Truncate context if too long
        max_context_chars = 8000
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n\n[CONTEXT TRUNCATED]"
        
        parts.append(f"""**REFERENCE CONTEXT** (use to substantiate points):
---
{context}
---

""")
    
    # Add few-shot examples
    if training_examples:
        parts.append("\n**FEW-SHOT EXAMPLES** (learn from these feedback examples):\n")
        parts.append("---\n")
        for idx, example in enumerate(training_examples, 1):
            parts.append(f"\n**Example {idx}:**\n")
            parts.append(f"Question: {example.get('question', 'N/A')[:150]}...\n\n")
            parts.append(f"Student Answer Preview: {example.get('student_answer', 'N/A')[:200]}...\n\n")
            parts.append(f"Ideal Feedback Given:\n{example.get('ideal_feedback', 'N/A')}\n")
            parts.append("\n---\n")
    
    parts.append(f"""\n**TASK**: Read the student's handwritten answer from the uploaded file and provide:
1. An improved version in strict IBC format
2. Detailed feedback comparing the student's answer to the ideal answer

**Requirements for Improved Answer**:
1. Preserve the student's voice and original points
2. Use the REFERENCE CONTEXT above to add facts, data, and examples
3. Follow strict IBC format (Introduction-Body-Conclusion)
4. Target word count: approximately {word_count} words
5. Include at least one inline diagram suggestion
6. Every bullet must have: evidence (report/data) + example (India/World)

**Requirements for Feedback**:
1. Identify specific strengths in the student's answer
2. Point out missing elements (facts, examples, structure)
3. Provide actionable improvement suggestions
4. Comment on IBC format adherence and evidence usage
5. Give an overall encouraging assessment
{f'6. Learn from the {len(training_examples)} few-shot examples above to provide similar quality feedback' if training_examples else ''}

Return ONLY a valid JSON object as specified in the system prompt. No markdown code blocks, no commentary.""")
    
    return "".join(parts)


def _parse_evaluation_response(response_text: str) -> tuple:
    """Parse Gemini's evaluation response"""
    try:
        # Clean response
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Parse JSON
        response_data = json.loads(cleaned)
        
        improved_answer = response_data.get("improved_answer", response_text)
        feedback_data = response_data.get("feedback", {})
        
        feedback = {
            "strengths": feedback_data.get("strengths", []),
            "missing_elements": feedback_data.get("missing_elements", []),
            "improvements_needed": feedback_data.get("improvements_needed", []),
            "structure_feedback": feedback_data.get("structure_feedback", ""),
            "evidence_feedback": feedback_data.get("evidence_feedback", ""),
            "overall_assessment": feedback_data.get("overall_assessment", "")
        }
        
        return improved_answer, feedback
        
    except json.JSONDecodeError:
        # Fallback: treat entire response as improved answer
        return response_text, {
            "strengths": [],
            "missing_elements": [],
            "improvements_needed": [],
            "structure_feedback": "Unable to parse structured feedback",
            "evidence_feedback": "",
            "overall_assessment": "Please review the improved answer above."
        }


def _get_fallback_evaluation_prompt() -> str:
    """Fallback evaluation system prompt"""
    return """You are an expert UPSC Geography evaluator.

Your task is to read a student's handwritten answer and provide:
1. An improved version using the provided reference context
2. Detailed feedback comparing the student's answer to the ideal

Return a JSON object with:
{
  "improved_answer": "The improved answer in markdown format...",
  "feedback": {
    "strengths": ["List specific strengths"],
    "missing_elements": ["Key points missing"],
    "improvements_needed": ["Actionable suggestions"],
    "structure_feedback": "Comment on structure",
    "evidence_feedback": "Comment on evidence usage",
    "overall_assessment": "Brief overall assessment"
  }
}

CRITICAL: Return ONLY valid JSON."""


# ============================================================
# TASK 3: MAINS ANSWER GENERATION
# ============================================================


# ============================================================
# HELPER FUNCTIONS FOR MAINS ANSWER
# ============================================================

def clean_gemini_error(error_msg: str) -> str:
    """Clean Gemini API error messages"""
    if '429' in error_msg:
        return "Quota exceeded. Please try again later."
    return f"AI Error: {error_msg[:100]}..."

def enforce_diagrams(answer: str, required: int = 1) -> str:
    """Ensure at least `required` Mermaid diagrams exist"""
    # Simple check - if missing, we relies on prompt instructions effectively
    # or we could inject a template. For now, just pass through.
    return answer

def count_words_excluding_visuals(text: str) -> int:
    """Count words excluding visuals"""
    cleaned_text = re.sub(r'```mermaid[\s\S]*?```', '', text)
    cleaned_text = re.sub(r'```map-json[\s\S]*?```', '', cleaned_text)
    cleaned_text = re.sub(r'```[\s\S]*?```', '', cleaned_text)
    cleaned_text = re.sub(r'!\[[^\]]*\]\(data:image[^\)]+\)', '', cleaned_text)
    return len(cleaned_text.split())

# ============================================================
# TASK 3: MAINS ANSWER GENERATION
# ============================================================

@trace_chain("mains_answer_pipeline")
async def generate_mains_answer_task(ctx, job_id: str, query: str, user_id: str, word_count: int = 350, gemini_api_key: str = None):
    """
    Generate Mains Answer using Gemini 2.5 Pro (Full Pipeline).
    Includes:
    1. Cache Check (if enabled here, but usually done in route. We do generation here)
    2. Parallel Fetch (Health, Retrieval, News)
    3. Prompt Assembly
    4. Generation
    5. Compression
    6. Cache & Save
    """
    logger.info(f"✍️ [JOB {job_id}] Starting mains answer generation for user {user_id}")
    redis = ctx["redis"]
    status_key = f"job_status:{job_id}"
    await redis.set(status_key, "processing")
    
    try:
        await check_cancellation(ctx, job_id)
        
        # Imports
        from .prompts.mains_prompt import assemble_mains_prompt
        from .utils.context_retriever import retrieve_context_for_question
        from .utils.question_parser import parse_question_for_search
        from .utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
        from .utils.map_proxy import parse_and_generate_maps, check_map_service_health
        from .utils.answer_compressor import compress_answer
        
        # Initialize resources
        gemini_client = GeminiClient(api_key=gemini_api_key, model_name="gemini-2.5-pro")
        flash_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_FLASH)
        cache = get_cache_manager()
        pinecone_handler = ctx.get("pinecone_handler")
        
        # ============================================================
        # PHASE 2: ALIGNED RETRIEVAL & NEWS PIPELINE
        # ============================================================
        pipeline_result = await run_enriched_pipeline(
            ctx=ctx,
            job_id=job_id,
            query=query,
            gemini_api_key=gemini_api_key
        )
        
        context = pipeline_result["context"]
        sources = pipeline_result["sources"]
        parsed_topics = pipeline_result["parsed_topics"]
        current_affairs_bullets = pipeline_result["current_affairs_bullets"]
        current_affairs_section = pipeline_result["current_affairs"]
        map_service_healthy = pipeline_result["map_service_healthy"]

        # ============================================================
        # GENERATE (User Locked)
        # ============================================================
        
        # Prompt
        prompt_pair = assemble_mains_prompt(
            question=query,
            context=context,
            current_bullets=current_affairs_section,
            word_count=word_count
        )
        
        lock_key = f"lock:user:{user_id}"
        logger.info(f"🔐 [JOB {job_id}] Acquiring lock {lock_key}...")
        
        async with redis.lock(lock_key, timeout=120, blocking_timeout=70):
             await check_cancellation(ctx, job_id)
             logger.info(f"🤖 [JOB {job_id}] Calling Gemini (Locked)...")
             
             response_text = await gemini_client.generate_response(
                 user_prompt=prompt_pair["user"],
                 system_prompt=prompt_pair["system"],
                 temperature=0.15,
                 max_retries=2
             )
             
        answer_text = response_text.strip()
        word_count_actual = count_words_excluding_visuals(answer_text)
        
        # ============================================================
        # POST-PROCESSING (Map + Compress)
        # ============================================================
        
        # Map Generation
        if map_service_healthy:
            try:
                answer_text = await parse_and_generate_maps(answer_text)
            except Exception as e:
                logger.warning(f"Map generation failed: {e}")
        
        # Compression
        compressed_answer = None
        word_count_compressed = None
        try:
             # Compression uses Gemini, might need lock? Usually fast/cheap.
             # Strict rate limit might require lock. Let's skip lock for compression to avoid holding it too long.
             # Or use system key? current compress_answer might use different client.
             # It accepts gemini_client.
             compressed = await compress_answer(
                 original_answer=answer_text,
                 target_word_count=word_count,
                 gemini_client=flash_client,
                 threshold_ratio=1.5
             )
             if compressed:
                 compressed_answer = compressed
                 word_count_compressed = count_words_excluding_visuals(compressed)
        except Exception as e:
             logger.warning(f"Compression failed: {e}")

        # ============================================================
        # SAVE RESULT & CACHE
        # ============================================================
        
        # Cache Result
        model_version = "gemini-2.5-pro-v1"
        answer_to_cache = compressed_answer or answer_text
        word_count_cache = count_words_excluding_visuals(answer_to_cache)
        compressed_for_cache = None if not compressed_answer or compressed_answer.strip() == answer_to_cache.strip() else compressed_answer
        
        if cache:
             cache.set_cached_answer(
                question=query,
                word_count=word_count,
                answer=answer_to_cache,
                sources=sources,
                model_version=model_version,
                compressed_answer=compressed_for_cache,
                word_count_actual=word_count_cache,
                word_count_compressed=word_count_compressed
            )
             # Add to history
             cache.add_user_history(
                user_id=user_id,
                question=query,
                word_count=word_count,
                answer_preview=answer_text
            )

        result = {
            "question": query,
            "answer": answer_text,
            "compressed_answer": compressed_answer,
            "sources": sources,
            "word_count_actual": word_count_actual,
            "word_count_compressed": word_count_compressed
        }
        
        await set_job_result(redis, job_id, result)
        logger.info(f"✅ [JOB {job_id}] Mains generation complete")

    except asyncio.CancelledError:
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] Failed: {e}", exc_info=True)
        await set_job_error(redis, job_id, str(e))
    finally:
        await redis.delete(f"cancel:{job_id}")


# ============================================================
# WORKER SETTINGS
# ============================================================

class WorkerSettings:
    """ARQ Worker configuration"""
    functions = [generate_mock_test_task, evaluate_answer_task, generate_mains_answer_task]
    redis_settings = REDIS_SETTINGS
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5

if __name__ == "__main__":
    import sys
    from arq import run_worker
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        sys.exit(0)
    job_timeout = 300  # 5 minutes max per job
