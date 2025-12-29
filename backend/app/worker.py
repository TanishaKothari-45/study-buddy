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

# Batch processing concurrency limit (for parallel Gemini calls)
BATCH_CONCURRENT_LIMIT = 10


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
# GEMINI CLIENT FACTORY (Cached by api_key + model)
# ============================================================

def get_gemini_client(ctx: dict, api_key: str, model_name: str) -> GeminiClient:
    """
    Get or create a GeminiClient instance with caching.
    Caches clients by (api_key_prefix, model_name) to avoid redundant initialization.
    
    Args:
        ctx: Worker context dict
        api_key: Gemini API key
        model_name: Model name (e.g., gemini-2.5-pro)
        
    Returns:
        GeminiClient instance (cached or new)
    """
    # Initialize cache dict if not exists
    if "gemini_clients" not in ctx:
        ctx["gemini_clients"] = {}
    
    # Cache key: first 8 chars of api_key + model_name (for privacy)
    cache_key = f"{api_key[:8]}:{model_name}"
    
    if cache_key not in ctx["gemini_clients"]:
        ctx["gemini_clients"][cache_key] = GeminiClient(api_key=api_key, model_name=model_name)
        logger.debug(f"✅ Created new GeminiClient for {cache_key}")
    
    return ctx["gemini_clients"][cache_key]


# ============================================================
# TRAINING EXAMPLES LOADER (Consolidated)
# ============================================================

def load_training_examples(max_examples: int = 3) -> List[dict]:
    """
    Load few-shot training examples from data file (consolidated helper).
    
    Args:
        max_examples: Maximum number of examples to return (default: 3)
        
    Returns:
        List of training example dicts
    """
    try:
        training_data_file = Path(__file__).parent.parent.parent / "data" / "training_examples.json"
        if training_data_file.exists():
            with open(training_data_file, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
                all_examples = training_data.get("training_examples", [])
                # Return last N examples (most recent)
                return all_examples[-max_examples:] if len(all_examples) > max_examples else all_examples
    except Exception as e:
        logger.debug(f"No training examples loaded: {e}")
    return []


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
    k: int = 12,
    fetch_k: int = 30,
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
            error_msg = str(e).lower()
            if '401' in error_msg or '403' in error_msg or 'api key' in error_msg or 'invalid' in error_msg:
                logger.error(f"❌ Critical API Key error in news pipeline: {e}")
                # Re-raise for fail-fast
                raise
            logger.warning(f"News pipeline failed (fallback allowed): {e}")
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
        await set_job_error(redis, job_id, clean_gemini_error(str(e)))
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
    Evaluate student answer using Gemini 2.5 Pro (FEEDBACK ONLY - No Retrieval).
    
    EVALUATION FLOW (Simplified):
    =============================
    
    1. TRAINING EXAMPLES:
       - Loads few-shot examples from training_examples.json
       - Provides examples of good feedback patterns
    
    2. PROMPT BUILDING:
       - Builds evaluation prompt with:
         * Training examples (few-shot learning)
         * Instructions to extract question, marks, word_count from files
         * Instructions for feedback ONLY (no improved answer)
    
    3. GEMINI EVALUATION (Locked):
       - Sends prompt + student's handwritten answer (PDF/image) to Gemini 2.5 Pro
       - Gemini performs OCR on handwritten answer
       - Gemini extracts question, marks, word_count AND evaluates answer
       - Returns JSON with question, marks, word_count, and detailed feedback
    
    4. RESPONSE PARSING:
       - Parses JSON response
       - Extracts question, marks, word_count, and feedback structure
       - Handles parsing errors gracefully
    
    5. RESULT SAVING:
       - Saves feedback result to Redis
       - Includes: question, student_answer, feedback, word_count, marks
    
    KEY FEATURES:
    - Single API call for question extraction + evaluation (more efficient)
    - Pure prompt-based evaluation (no retrieval to save tokens)
    - User lock prevents concurrent evaluations per user
    - Cancellation support via Redis flags
    - File cleanup after processing
    - Error handling with user-friendly messages
    """
    logger.info(f"📝 [JOB {job_id}] Starting evaluation for user {user_id}")
    redis = ctx["redis"]
    status_key = f"job_status:{job_id}"
    await redis.set(status_key, "processing")
    
    try:
        await check_cancellation(ctx, job_id)
        
        # Validate API key before proceeding
        if not gemini_api_key or not gemini_api_key.strip():
            raise Exception("Invalid API key: API key is empty or not provided. Please check your API key in Settings.")
        
        # Initialize Gemini Client (using cached factory)
        gemini_client = get_gemini_client(ctx, gemini_api_key, settings.GEMINI_MODEL_PRO)
        
        # Import shared prompt
        try:
             from .prompts.shared_mains_prompts import get_evaluation_system_prompt
             system_prompt = get_evaluation_system_prompt()
        except ImportError:
             logger.warning("⚠️ Using fallback generic system prompt")
             system_prompt = "You are an expert evaluator. Provide detailed feedback on the student's answer."

        # File type check
        all_is_pdf = all(f.lower().endswith('.pdf') for f in file_paths)
        all_is_image = all(f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) for f in file_paths)

        # Default values (will be extracted from response)
        identified_question = question or ""  # Use provided question if available, otherwise will be extracted
        word_count_int = 250  # Default
        marks_int = 15  # Default (15 marks = 250 words)
        
        await check_cancellation(ctx, job_id)
        
        # ============================================================
        # STEP 1: Load training examples (using consolidated helper)
        # ============================================================
        training_examples = load_training_examples(max_examples=3)
        if training_examples:
            logger.info(f"✅ [JOB {job_id}] Loaded {len(training_examples)} training examples")

        # ============================================================
        # STEP 2: Build evaluation prompt (feedback only, no context)
        # ============================================================
        logger.info(f"📝 [JOB {job_id}] STEP 2: Building evaluation prompt...")
        user_prompt = _build_evaluation_prompt(
            provided_question=identified_question,  # May be empty, will be extracted if not provided
            training_examples=training_examples,
            use_extracted_text=False  # Single mode: read from files
        )
        
        # ============================================================
        # STEP 3: Call Gemini WITH USER LOCK
        # ============================================================
        logger.info(f"🤖 [JOB {job_id}] STEP 3: Calling Gemini with user lock...")
        
        # Re-applied increased timeout for evaluation (Gemini 2.5 Pro can be slow)
        async with redis.lock(f"lock:user:{user_id}", timeout=600, blocking_timeout=70):
            logger.info(f"🔐 [JOB {job_id}] Lock acquired, calling Gemini...")
            await check_cancellation(ctx, job_id)
            
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
        
        # ============================================================
        # STEP 4: Parse response (extract question, marks, word_count, and feedback)
        # ============================================================
        logger.info(f"🔍 [JOB {job_id}] STEP 4: Parsing response...")
        parsed_result = _parse_evaluation_response(response_text)
        feedback = parsed_result.get("feedback", {})
        
        # Extract question, marks, and word_count from response
        extracted_question = parsed_result.get("question", "")
        extracted_marks = parsed_result.get("marks", 15)
        extracted_word_count = parsed_result.get("word_count", 250)
        
        # Use extracted values if question was not provided, otherwise use provided question
        if not identified_question and extracted_question:
            identified_question = extracted_question
            logger.info(f"✅ [JOB {job_id}] Extracted question: {identified_question[:100]}...")
        
        # Always use extracted marks and word_count (they're more accurate)
        marks_int = extracted_marks
        word_count_int = extracted_word_count
        logger.info(f"✅ [JOB {job_id}] Extracted marks: {marks_int}, word_count: {word_count_int}")
        
        # ============================================================
        # STEP 5: Save Result (feedback only)
        # ============================================================
        logger.info(f"💾 [JOB {job_id}] STEP 5: Saving result...")
        
        result = {
            "question": identified_question,
            "student_answer": "Answer extracted by Gemini",
            "feedback": feedback,
            "word_count": word_count_int,
            "marks": marks_int,
            "success": True
        }
        
        await set_job_result(redis, job_id, result)
        logger.info(f"✅ [JOB {job_id}] Evaluation complete")
        
    except asyncio.CancelledError:
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] Failed: {e}", exc_info=True)
        await set_job_error(redis, job_id, clean_gemini_error(str(e)))
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
    provided_question: str = "",
    training_examples: List[dict] = None,
    answer_text: str = None,
    word_count: int = None,
    marks: int = None,
    use_extracted_text: bool = False
) -> str:
    """
    Build the evaluation user prompt (unified for both single and batch modes).
    
    Args:
        provided_question: Question text (optional for single mode, required for batch mode)
        training_examples: Few-shot examples for learning feedback patterns
        answer_text: Extracted answer text (only for batch mode when use_extracted_text=True)
        word_count: Word count (only for batch mode when use_extracted_text=True)
        marks: Marks (only for batch mode when use_extracted_text=True)
        use_extracted_text: If True, use provided answer_text instead of reading from files
    
    Returns:
        Formatted evaluation prompt string
    """
    import json
    
    if training_examples is None:
        training_examples = []
    
    parts = []
    
    if use_extracted_text:
        # Batch mode: Use extracted text (question, marks, word_count, answer_text already provided)
        if not provided_question or not answer_text:
            raise ValueError("For batch mode, question and answer_text must be provided")
        if word_count is None or marks is None:
            raise ValueError("For batch mode, word_count and marks must be provided")
        
        # Include marks and word_limit in JSON format as specified
        input_json = {
            "question_text": provided_question,
            "answer_text": answer_text,
            "marks": marks,
            "word_limit": word_count
        }
        parts.append(f"""**INPUT FORMAT**:
```json
{json.dumps(input_json, indent=2, ensure_ascii=False)}
```

**QUESTION**: {provided_question}

**MARKS**: {marks} marks
**WORD LIMIT**: {word_count} words

**STUDENT ANSWER TEXT**:
{answer_text}

""")
        
        task_description = "Evaluate the student's answer text provided above and provide detailed feedback."
    else:
        # Single mode: Read from uploaded files (OCR + evaluation)
        if provided_question:
            parts.append(f"""**QUESTION PROVIDED**: {provided_question}

**TASK**: Extract marks and word count from the question or uploaded file, then evaluate the student's handwritten answer.

""")
        else:
            parts.append("""**TASK**: 
1. First, extract the QUESTION text from the uploaded file(s)
2. Extract the MARKS (10 or 15) and WORD COUNT (150 or 250 words) from the question or file
   - 10 marks = 150 words
   - 15 marks = 250 words
3. Then evaluate the student's handwritten answer

""")
        
        task_description = "Read the student's handwritten answer from the uploaded file and provide detailed feedback."
    
    # Add few-shot examples (same for both modes)
    if training_examples:
        parts.append("\n**FEW-SHOT EXAMPLES** (learn from these feedback examples):\n")
        parts.append("---\n")
        for idx, example in enumerate(training_examples, 1):
            parts.append(f"\n**Example {idx}:**\n")
            parts.append(f"Question: {example.get('question', 'N/A')[:150]}...\n\n")
            parts.append(f"Student Answer Preview: {example.get('student_answer', 'N/A')[:200]}...\n\n")
            parts.append(f"Ideal Feedback Given:\n{example.get('ideal_feedback', 'N/A')}\n")
            parts.append("\n---\n")
    
    # Evaluation requirements (same for both modes)
    parts.append(f"""**REQUIREMENTS FOR EVALUATION**:
1. {"Extract question, marks, and word_count from the uploaded file(s) if not provided" if not use_extracted_text else "Use the provided question, marks, and word_count"}
2. Identify specific strengths in the student's answer
3. Point out missing elements (facts, examples, structure, visuals)
4. Provide actionable improvement suggestions
5. Comment on IBC format adherence and evidence usage
6. Assess directive alignment (if directive word is present in question)
7. Comment on whether visuals (maps/diagrams/tables) were needed but missing
8. Give an overall encouraging assessment
""")
    
    if training_examples:
        parts.append(f"9. Learn from the {len(training_examples)} few-shot examples above to provide similar quality feedback\n")
    
    parts.append(f"""
**TASK**: {task_description}

**Note**: This is FEEDBACK ONLY. Do NOT generate an improved answer. Focus solely on evaluating the student's work.

Return ONLY a valid JSON object as specified in the system prompt. The JSON must include:
- "question": {"extracted question text" if not use_extracted_text else f"question text (use: {provided_question})"}
- "marks": {"10 or 15" if not use_extracted_text else str(marks)}
- "word_count": {"150 or 250" if not use_extracted_text else str(word_count)}
- "feedback": evaluation feedback object

No markdown code blocks, no commentary.""")
    
    return "".join(parts)


def _parse_evaluation_response(response_text: str) -> dict:
    """Parse Gemini's evaluation response (extract question, marks, word_count, and feedback)"""
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
        
        # Extract question, marks, and word_count from root level
        extracted_question = response_data.get("question", "")
        extracted_marks = response_data.get("marks", 15)
        extracted_word_count = response_data.get("word_count", 250)
        
        # Validate and normalize marks/word_count
        if extracted_marks not in [10, 15]:
            # Try to derive from word_count
            if extracted_word_count == 150:
                extracted_marks = 10
            elif extracted_word_count == 250:
                extracted_marks = 15
            else:
                extracted_marks = 15  # Default
                extracted_word_count = 250  # Default
        
        # Ensure consistency: 10 marks = 150 words, 15 marks = 250 words
        if extracted_marks == 10 and extracted_word_count != 150:
            extracted_word_count = 150
        elif extracted_marks == 15 and extracted_word_count != 250:
            extracted_word_count = 250
        
        # Extract feedback (may be nested under "feedback" key or at root)
        feedback_data = response_data.get("feedback", response_data)
        
        feedback = {
            "examiner_expectation_blueprint": feedback_data.get("examiner_expectation_blueprint", {
                "key_demands_of_the_question": [],
                "ideal_logical_structure": {
                    "introduction": "",
                    "body": "",
                    "conclusion": ""
                },
                "non_negotiables": []
            }),
            "strengths": feedback_data.get("strengths", []),
            "critical_gaps_and_remedies": feedback_data.get("critical_gaps_and_remedies", []),
            "section_wise_assessment": feedback_data.get("section_wise_assessment", {
                "introduction": "",
                "body": "",
                "conclusion": ""
            }),
            "directive_alignment": feedback_data.get("directive_alignment"),
            "evidence_feedback": feedback_data.get("evidence_feedback", ""),
            "visual_feedback": feedback_data.get("visual_feedback"),
            "strategy_tip": feedback_data.get("strategy_tip"),
            "overall_assessment": feedback_data.get("overall_assessment", ""),
            "margin_comments": feedback_data.get("margin_comments", [])
        }
        
        return {
            "question": extracted_question,
            "marks": extracted_marks,
            "word_count": extracted_word_count,
            "feedback": feedback
        }
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse evaluation response as JSON: {e}")
        # Fallback: return minimal structure
        return {
            "question": "",
            "marks": 15,
            "word_count": 250,
            "feedback": {
                "examiner_expectation_blueprint": {
                    "key_demands_of_the_question": [],
                    "ideal_logical_structure": {
                        "introduction": "",
                        "body": "",
                        "conclusion": ""
                    },
                    "non_negotiables": []
                },
                "strengths": [],
                "critical_gaps_and_remedies": [],
                "section_wise_assessment": {
                    "introduction": "",
                    "body": "",
                    "conclusion": ""
                },
                "directive_alignment": None,
                "evidence_feedback": "Unable to parse structured feedback from response",
                "visual_feedback": None,
                "strategy_tip": None,
                "overall_assessment": "Evaluation completed but response format was unexpected.",
                "margin_comments": []
            }
        }


# ============================================================
# HELPER: Single Answer Evaluation (for parallel batch processing)
# ============================================================

async def _evaluate_single_answer_async(
    answer_data: dict,
    gemini_client: GeminiClient,
    evaluation_system_prompt: str,
    training_examples: List[dict],
    semaphore: asyncio.Semaphore,
    job_id: str,
    temp_dir: Path
) -> dict:
    """
    Evaluate a single answer with semaphore-controlled concurrency.
    Now supports PDF segments for improved reliability.
    """
    answer_id = answer_data.get("answer_id", "unknown")
    question_number = answer_data.get("question_number", 0)
    question_text = answer_data.get("question", f"Question {question_number}")
    answer_text = answer_data.get("text", "")
    word_count = answer_data.get("word_count", 250)
    marks = answer_data.get("marks", 15)
    
    result = {
        "answer_id": answer_id,
        "question_number": question_number,
        "status": "processing",
        "evaluation": None,
        "error": None,
        "marks": marks,
        "word_count": word_count
    }
    
    try:
        # Use semaphore for rate limiting
        async with semaphore:
            logger.info(f"📝 [BATCH JOB {job_id}] Evaluating answer {answer_id} (Q{question_number})")
            
            # Check if we have a segment PDF or just text
            segment_pdf_path = answer_data.get("segment_pdf_path")
            
            if segment_pdf_path and os.path.exists(segment_pdf_path):
                # USE PDF SEGMENT (Most Reliable)
                # Build evaluation prompt (single-answer style)
                user_prompt = _build_evaluation_prompt(
                    provided_question=question_text,
                    training_examples=training_examples,
                    word_count=word_count,
                    marks=marks,
                    use_extracted_text=False  # Tell Gemini to read from file
                )
                
                # Call Gemini for evaluation
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=evaluation_system_prompt,
                    pdf_path=segment_pdf_path,
                    temperature=0.2,
                    max_retries=2
                )
            else:
                # FALLBACK: Use Extracted Text if split failed
                user_prompt = _build_evaluation_prompt(
                    provided_question=question_text,
                    training_examples=training_examples,
                    answer_text=answer_text,
                    word_count=word_count,
                    marks=marks,
                    use_extracted_text=True
                )
                
                # Call Gemini for evaluation
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=evaluation_system_prompt,
                    temperature=0.2,
                    max_retries=2
                )
            
            # Parse evaluation response
            parsed_result = _parse_evaluation_response(response_text)
            feedback = parsed_result.get("feedback", {})
            
            # Mark answer as completed
            result["status"] = "completed"
            result["evaluation"] = {
                "question": question_text,
                "feedback": feedback,
                "word_count": word_count,
                "marks": marks
            }
            
            logger.info(f"✅ [BATCH JOB {job_id}] Completed answer {answer_id}")
            
    except Exception as e:
        error_str = str(e).lower()
        
        # Check for fatal errors (429/401) - these should stop the entire batch
        if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str or 'api key' in error_str:
            logger.error(f"❌ [BATCH JOB {job_id}] Fatal error at answer {answer_id}: {e}")
            result["status"] = "fatal_error"
            result["error"] = clean_gemini_error(str(e))
        else:
            # Transient error - mark as failed
            logger.warning(f"⚠️ [BATCH JOB {job_id}] Failed to evaluate answer {answer_id}: {e}")
            result["status"] = "failed"
            result["error"] = clean_gemini_error(str(e))
    
    return result


# ============================================================
# TASK 2B: BATCH ANSWER EVALUATION (Multiple Answers from Single PDF)
# ============================================================

@trace_chain("batch_evaluation_pipeline")
async def evaluate_batch_answers_task(
    ctx,
    job_id: str,
    pdf_path: str,
    user_id: str,
    gemini_api_key: str,
    use_standard_format: bool = False,
    question_file_path: Optional[str] = None,
    question_texts: Optional[List[str]] = None
):
    """
    Evaluate multiple answers from a single PDF using batch processing.
    
    NEW FLOW:
    1. Single Gemini call: Detection + OCR mode
       - Detect all answers in PDF
       - Extract question, marks, word_count, and OCR text for each answer
       - Returns JSON with all answers
    2. Sequential evaluation calls:
       - For each detected answer, make evaluation API call
       - Use extracted question and text (no need to send files again)
       - Track status per answer
    3. Handle errors gracefully:
       - 429/401: Cancel entire batch
       - Transient errors: Retry then mark failed, continue
    4. Update progress in Redis for polling
    
    Redis Structure:
    - job_status:{job_id} = "processing" | "completed" | "partial_failed" | "cancelled"
    - job_batch_data:{job_id} = JSON with {total_answers, completed_answers, failed_answers, answers: [...]}
    """
    logger.info(f"📦 [BATCH JOB {job_id}] Starting batch evaluation for user {user_id}")
    redis = ctx["redis"]
    
    # Initialize batch status
    batch_data = {
        "total_answers": 0,
        "completed_answers": 0,
        "failed_answers": 0,
        "answers": []
    }
    
    await set_job_status(redis, job_id, "processing", batch_data=json.dumps(batch_data))
    
    try:
        await check_cancellation(ctx, job_id)
        
        # Initialize Gemini Client (using cached factory)
        gemini_client = get_gemini_client(ctx, gemini_api_key, settings.GEMINI_MODEL_PRO)
        
        # Import detection system prompt
        try:
            from .prompts.shared_mains_prompts import get_batch_detection_system_prompt, get_evaluation_system_prompt
            detection_system_prompt = get_batch_detection_system_prompt()
            evaluation_system_prompt = get_evaluation_system_prompt()
        except ImportError:
            logger.warning("⚠️ Using fallback generic system prompts")
            detection_system_prompt = "You are an expert document analyzer. Detect all answers in the PDF and extract questions, marks, word counts, and OCR text."
            evaluation_system_prompt = "You are an expert evaluator. Provide detailed feedback on the student's answer."
        
        # ============================================================
        # STEP 1: Detection + OCR (Single Gemini Call)
        # ============================================================
        logger.info(f"🔍 [BATCH JOB {job_id}] Step 1: Detecting answers and extracting OCR text...")
        
        detection_prompt = """Analyze the PDF document and detect all answers. For each answer:
1. Identify the answer boundaries (where each answer starts and ends)
2. Extract the question text
3. Extract marks (10 or 15) and word count (150 or 250)
4. Perform OCR to extract the complete answer text

Return the result in the exact JSON format specified in the system prompt."""
        
        lock_key = f"lock:user:{user_id}"
        detected_answers = []
        
        # Re-applied increased timeout for batch OCR/Detection (Segmentation pass)
        async with redis.lock(lock_key, timeout=900, blocking_timeout=90):
            await check_cancellation(ctx, job_id)
            
            try:
                detection_response = await gemini_client.generate_response(
                    user_prompt=detection_prompt,
                    system_prompt=detection_system_prompt,
                    pdf_path=pdf_path,
                    temperature=0.0,
                    max_retries=3
                )
                
                # Parse detection response
                cleaned_response = detection_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                detection_data = json.loads(cleaned_response)
                detected_answers = detection_data.get("answers", [])
                
                if not detected_answers:
                    raise Exception("No answers detected in PDF")
                
                # Enforce max 20 answers
                if len(detected_answers) > 20:
                    logger.warning(f"⚠️ [BATCH JOB {job_id}] Limiting to 20 answers (found {len(detected_answers)})")
                    detected_answers = detected_answers[:20]
                
                # ============================================================
                # STEP 1.5: SPLIT PDF (New Segmentation Logic)
                # ============================================================
                from PyPDF2 import PdfReader, PdfWriter
                
                logger.info(f"✂️ [BATCH JOB {job_id}] Splitting PDF into {len(detected_answers)} segments...")
                temp_dir = Path(pdf_path).parent / "segments"
                temp_dir.mkdir(exist_ok=True)
                
                reader = PdfReader(pdf_path)
                total_pages = len(reader.pages)
                
                valid_segments = []
                for idx, ans in enumerate(detected_answers):
                    try:
                        start_page = int(ans.get("start_page", 1)) - 1 # 0-indexed
                        end_page = int(ans.get("end_page", start_page + 1)) - 1
                        
                        # Safety checks
                        start_page = max(0, min(start_page, total_pages - 1))
                        end_page = max(start_page, min(end_page, total_pages - 1))
                        
                        writer = PdfWriter()
                        for p in range(start_page, end_page + 1):
                            writer.add_page(reader.pages[p])
                        
                        segment_filename = f"segment_{job_id}_{idx+1}.pdf"
                        segment_path = temp_dir / segment_filename
                        
                        with open(segment_path, "wb") as f:
                            writer.write(f)
                        
                        ans["segment_pdf_path"] = str(segment_path)
                        valid_segments.append(ans)
                        logger.debug(f"  • Created segment {idx+1}: Pages {start_page+1}-{end_page+1}")
                    except Exception as split_err:
                        logger.warning(f"  ⚠️ Failed to split segment {idx+1}: {split_err}")
                        # Keep it anyway, will fallback to text or fail later
                        valid_segments.append(ans)
                
                detected_answers = valid_segments
                batch_data["total_answers"] = len(detected_answers)
                logger.info(f"✅ [BATCH JOB {job_id}] Segmentation complete. {len(detected_answers)} answers ready.")
                
            except Exception as e:
                error_str = str(e).lower()
                if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str or 'api key' in error_str:
                    logger.error(f"❌ [BATCH JOB {job_id}] Fatal error during detection: {e}")
                    raise
                logger.error(f"❌ [BATCH JOB {job_id}] Detection failed: {e}", exc_info=True)
                raise Exception(f"Failed to detect answers: {str(e)}")
        
        # ============================================================
        # STEP 2: Parallel Evaluation Calls (with Semaphore)
        # ============================================================
        logger.info(f"🚀 [BATCH JOB {job_id}] Step 2: Evaluating {len(detected_answers)} answers in PARALLEL (max {BATCH_CONCURRENT_LIMIT} concurrent)...")
        
        # Load training examples once (using consolidated helper)
        training_examples = load_training_examples(max_examples=3)
        if training_examples:
            logger.info(f"✅ [BATCH JOB {job_id}] Loaded {len(training_examples)} training examples")
        
        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(BATCH_CONCURRENT_LIMIT)
        
        # Check for cancellation before starting parallel evaluation
        await check_cancellation(ctx, job_id)
        
        # Prepare answer data for parallel processing
        for idx, detected_answer in enumerate(detected_answers):
            detected_answer["answer_id"] = detected_answer.get("answer_id", f"a{idx + 1}")
            detected_answer["question_number"] = detected_answer.get("question_number", idx + 1)
        
        # Create tasks for parallel evaluation
        evaluation_tasks = [
            _evaluate_single_answer_async(
                answer_data=answer,
                gemini_client=gemini_client,
                evaluation_system_prompt=evaluation_system_prompt,
                training_examples=training_examples,
                semaphore=semaphore,
                job_id=job_id,
                temp_dir=temp_dir if 'temp_dir' in locals() else Path(pdf_path).parent
            )
            for answer in detected_answers
        ]
        
        # Run all evaluations in parallel with return_exceptions=True
        # This ensures we get results for all answers even if some fail
        logger.info(f"⏳ [BATCH JOB {job_id}] Starting parallel evaluation of {len(evaluation_tasks)} answers...")
        evaluation_results = await asyncio.gather(*evaluation_tasks, return_exceptions=True)
        
        # Process results and check for fatal errors
        batch_cancelled = False
        for result in evaluation_results:
            if isinstance(result, Exception):
                # Handle exceptions from gather
                error_str = str(result).lower()
                if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str:
                    batch_cancelled = True
                batch_data["answers"].append({
                    "answer_id": "unknown",
                    "question_number": 0,
                    "status": "failed",
                    "evaluation": None,
                    "error": clean_gemini_error(str(result)),
                    "marks": 15,
                    "word_count": 250
                })
                batch_data["failed_answers"] += 1
            else:
                # Normal result dict from _evaluate_single_answer_async
                batch_data["answers"].append(result)
                if result["status"] == "completed":
                    batch_data["completed_answers"] += 1
                elif result["status"] == "fatal_error":
                    batch_cancelled = True
                    batch_data["failed_answers"] += 1
                else:  # failed
                    batch_data["failed_answers"] += 1
        
        # Update progress after parallel completion
        await set_job_status(redis, job_id, "processing", batch_data=json.dumps(batch_data))
        await redis.set(f"job_batch_data:{job_id}", json.dumps(batch_data), ex=7200)
        
        logger.info(f"📊 [BATCH JOB {job_id}] Parallel evaluation complete: {batch_data['completed_answers']} completed, {batch_data['failed_answers']} failed")
        
        # Step 3: Finalize batch status
        # Store final batch_data
        await redis.set(f"job_batch_data:{job_id}", json.dumps(batch_data), ex=7200)
        
        if batch_cancelled:
            await set_job_status(redis, job_id, "cancelled", batch_data=json.dumps(batch_data))
            await set_job_error(redis, job_id, "Batch cancelled due to API error (429/401) or user request")
        elif batch_data["failed_answers"] > 0:
            await set_job_status(redis, job_id, "partial_failed", batch_data=json.dumps(batch_data))
            await set_job_result(redis, job_id, batch_data)
        else:
            await set_job_status(redis, job_id, "completed", batch_data=json.dumps(batch_data))
            await set_job_result(redis, job_id, batch_data)
        
        logger.info(f"✅ [BATCH JOB {job_id}] Batch complete: {batch_data['completed_answers']} completed, {batch_data['failed_answers']} failed")
        
    except asyncio.CancelledError:
        if 'batch_data' in locals():
            await redis.set(f"job_batch_data:{job_id}", json.dumps(batch_data), ex=7200)
            await set_job_status(redis, job_id, "cancelled", batch_data=json.dumps(batch_data))
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [BATCH JOB {job_id}] Batch failed: {e}", exc_info=True)
        if 'batch_data' in locals():
            await redis.set(f"job_batch_data:{job_id}", json.dumps(batch_data), ex=7200)
            await set_job_status(redis, job_id, "failed", batch_data=json.dumps(batch_data))
        await set_job_error(redis, job_id, clean_gemini_error(str(e)))
    finally:
        # Cleanup: Remove segments and PDF if they were in temp directory
        try:
            # Cleanup segments
            if 'temp_dir' in locals() and temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info(f"🧹 [BATCH JOB {job_id}] Cleaned up temporary segments")
                
            if Path(pdf_path).parent.name == "temp":
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logger.info(f"🧹 [BATCH JOB {job_id}] Cleaned up temp PDF")
        except Exception as e:
            logger.warning(f"⚠️ [BATCH JOB {job_id}] Failed to cleanup PDF: {e}")
        
        await redis.delete(f"cancel:{job_id}")


# ============================================================
# TASK 2C: GENERATE IMPROVED ANSWER (Separate from Evaluation)
# ============================================================

@trace_chain("improved_answer_generation_pipeline")
async def generate_improved_answer_task(
    ctx,
    job_id: str,
    question: str,
    student_answer: Optional[str],  # Text or None if using file_paths
    file_paths: Optional[List[str]],  # File paths if student answer is in files
    feedback: dict,  # Feedback JSON from evaluation
    user_id: str,
    gemini_api_key: str,
    word_count: int = 250
):
    """
    Generate improved answer based on evaluation feedback.
    
    FLOW:
    1. Run retrieval pipeline (context + current affairs)
    2. Build prompt with question, student answer, feedback, context
    3. Call Gemini with get_improved_answer_system_prompt()
    4. Process maps if present
    5. Optional compression
    6. Return improved answer in markdown
    """
    logger.info(f"✍️ [JOB {job_id}] Starting improved answer generation for user {user_id}")
    redis = ctx["redis"]
    status_key = f"job_status:{job_id}"
    await redis.set(status_key, "processing")
    
    try:
        await check_cancellation(ctx, job_id)
        
        # Initialize Gemini Client (using cached factory)
        gemini_client = get_gemini_client(ctx, gemini_api_key, settings.GEMINI_MODEL_PRO)
        
        # Import utilities
        from .utils.map_proxy import parse_and_generate_maps, check_map_service_health
        from .utils.answer_compressor import compress_answer
        
        # Import shared prompt
        try:
            from .prompts.shared_mains_prompts import get_improved_answer_system_prompt
            system_prompt = get_improved_answer_system_prompt()
        except ImportError:
            logger.warning("⚠️ Using fallback generic system prompt")
            system_prompt = "You are an expert UPSC answer writer. Generate an improved answer based on the feedback provided."
        
        # File type check
        all_is_pdf = False
        all_is_image = False
        if file_paths:
            all_is_pdf = all(f.lower().endswith('.pdf') for f in file_paths)
            all_is_image = all(f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) for f in file_paths)
        
        # Extract student answer text if using files
        student_answer_text = student_answer
        if not student_answer_text and file_paths:
            logger.info(f"📝 [JOB {job_id}] Extracting student answer from files...")
            try:
                extract_prompt = "Read the handwritten answer and extract the complete answer text. Return ONLY the answer text."
                lock_key = f"lock:user:{user_id}"
                lock = RedisLock(redis, lock_key, timeout=60)
                if await lock.acquire(blocking=True, blocking_timeout=60):
                    try:
                        if all_is_pdf:
                            student_answer_text = await gemini_client.generate_response(extract_prompt, pdf_path=file_paths[0], temperature=0.0)
                        elif all_is_image:
                            student_answer_text = await gemini_client.generate_response(extract_prompt, image_path=file_paths[0], temperature=0.0)
                        else:
                            student_answer_text = "Answer extracted from file"
                        logger.info(f"✅ [JOB {job_id}] Extracted student answer: {len(student_answer_text)} chars")
                    finally:
                        await lock.release()
            except Exception as e:
                logger.warning(f"⚠️ [JOB {job_id}] Failed to extract student answer: {e}")
                student_answer_text = "Student answer from uploaded file"
        
        await check_cancellation(ctx, job_id)
        
        # ============================================================
        # STEP 1: Run retrieval pipeline
        # ============================================================
        logger.info(f"📚 [JOB {job_id}] STEP 1: Running retrieval pipeline...")
        pipeline_result = await run_enriched_pipeline(
            ctx=ctx,
            job_id=job_id,
            query=question,
            gemini_api_key=gemini_api_key
        )
        
        context = pipeline_result["context"]
        sources = pipeline_result["sources"]
        map_service_healthy = pipeline_result["map_service_healthy"]
        current_affairs_section = pipeline_result["current_affairs"]
        
        # Merge current affairs into context
        if current_affairs_section:
            context = context + "\n\n**RECENT NEWS/CURRENT AFFAIRS**:\n" + current_affairs_section
        
        await check_cancellation(ctx, job_id)
        
        # ============================================================
        # STEP 2: Build prompt for improved answer
        # ============================================================
        logger.info(f"📝 [JOB {job_id}] STEP 2: Building improved answer prompt...")
        user_prompt = _build_improved_answer_prompt(
            question=question,
            student_answer=student_answer_text or "Student answer from uploaded file",
            feedback=feedback,
            context=context,
            word_count=word_count
        )
        
        # ============================================================
        # STEP 3: Call Gemini WITH USER LOCK
        # ============================================================
        logger.info(f"🤖 [JOB {job_id}] STEP 3: Calling Gemini with user lock...")
        
        async with redis.lock(f"lock:user:{user_id}", timeout=120, blocking_timeout=70):
            logger.info(f"🔐 [JOB {job_id}] Lock acquired, calling Gemini...")
            await check_cancellation(ctx, job_id)
            
            # Call Gemini (with files if provided, otherwise text-only)
            if file_paths and (all_is_pdf or all_is_image):
                if all_is_pdf:
                    response_text = await gemini_client.generate_response(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        pdf_path=file_paths,
                        temperature=0.15,
                        max_retries=3
                    )
                else:
                    response_text = await gemini_client.generate_response(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        image_path=file_paths,
                        temperature=0.15,
                        max_retries=3
                    )
            else:
                # Text-only generation
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.15,
                    max_retries=3
                )
            
            logger.info(f"✅ [JOB {job_id}] Received response: {len(response_text)} chars")
        
        improved_answer = response_text.strip()
        word_count_actual = count_words_excluding_visuals(improved_answer)
        
        # ============================================================
        # STEP 4: Process maps
        # ============================================================
        logger.info(f"🗺️ [JOB {job_id}] STEP 4: Processing maps...")
        if map_service_healthy:
            try:
                improved_answer = await parse_and_generate_maps(improved_answer)
                logger.info("✅ Map processing completed")
            except Exception as e:
                logger.warning(f"Map generation failed: {e}")
        else:
            logger.warning("⚠️ Map service unavailable - skipping map generation")
        
        # ============================================================
        # STEP 5: Compression
        # ============================================================
        logger.info(f"🗜️ [JOB {job_id}] STEP 5: Applying compression...")
        compressed_answer = None
        word_count_compressed = None
        try:
            compressed = await compress_answer(
                original_answer=improved_answer,
                target_word_count=word_count,
                gemini_client=gemini_client,
                threshold_ratio=1.4,
                compression_target_ratio=1.2
            )
            if compressed:
                compressed_answer = compressed
                word_count_compressed = count_words_excluding_visuals(compressed)
                logger.info(f"✅ [JOB {job_id}] Compression successful: {word_count_actual} -> {word_count_compressed} words")
        except Exception as e:
            logger.warning(f"⚠️ [JOB {job_id}] Compression failed: {e}")
        
        # ============================================================
        # STEP 6: Save Result
        # ============================================================
        logger.info(f"💾 [JOB {job_id}] STEP 6: Saving result...")
        
        result = {
            "improved_answer": improved_answer,
            "compressed_answer": compressed_answer,
            "sources": sources,
            "word_count_actual": word_count_actual,
            "word_count_compressed": word_count_compressed,
            "success": True
        }
        
        await set_job_result(redis, job_id, result)
        logger.info(f"✅ [JOB {job_id}] Improved answer generation complete")
        
    except asyncio.CancelledError:
        await set_job_error(redis, job_id, "Cancelled by user")
    except Exception as e:
        logger.error(f"❌ [JOB {job_id}] Failed: {e}", exc_info=True)
        await set_job_error(redis, job_id, clean_gemini_error(str(e)))
    finally:
        # Cleanup files if provided
        if file_paths:
            for path in file_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
            # Cleanup directory
            try:
                os.rmdir(Path(file_paths[0]).parent)
            except:
                pass
        
        await redis.delete(f"cancel:{job_id}")


def _build_improved_answer_prompt(
    question: str,
    student_answer: str,
    feedback: dict,
    context: str,
    word_count: int
) -> str:
    """Build the improved answer generation prompt"""
    parts = [f"**QUESTION**: {question}\n\n"]
    
    parts.append(f"**STUDENT'S ORIGINAL ANSWER**:\n{student_answer}\n\n")
    
    # Format feedback - Only include: Examiner Expectation Blueprint, Missing Elements, Improvements Needed
    feedback_parts = []
    
    # 1. Examiner Expectation Blueprint
    if feedback.get("examiner_expectation_blueprint"):
        blueprint = feedback["examiner_expectation_blueprint"]
        blueprint_sections = []
        
        if blueprint.get("key_demands_of_the_question") and len(blueprint["key_demands_of_the_question"]) > 0:
            blueprint_sections.append(f"**Key Demands**: {', '.join(blueprint['key_demands_of_the_question'])}")
        
        if blueprint.get("ideal_logical_structure"):
            ideal = blueprint["ideal_logical_structure"]
            structure_parts = []
            if ideal.get("introduction"):
                structure_parts.append(f"Intro: {ideal['introduction']}")
            if ideal.get("body"):
                structure_parts.append(f"Body: {ideal['body']}")
            if ideal.get("conclusion"):
                structure_parts.append(f"Conclusion: {ideal['conclusion']}")
            if structure_parts:
                blueprint_sections.append(f"**Ideal Logical Structure**: {' | '.join(structure_parts)}")
        
        if blueprint.get("non_negotiables") and len(blueprint["non_negotiables"]) > 0:
            blueprint_sections.append(f"**Non-Negotiables**: {', '.join(blueprint['non_negotiables'])}")
        
        if blueprint_sections:
            feedback_parts.append("**EXAMINER EXPECTATION BLUEPRINT**:\n" + "\n".join(blueprint_sections))
    
    # 2. Missing Elements
    if feedback.get("missing_elements") and len(feedback["missing_elements"]) > 0:
        feedback_parts.append(f"\n**MISSING ELEMENTS**:\n" + "\n".join([f"- {item}" for item in feedback["missing_elements"]]))
    
    # 3. Improvements Needed
    if feedback.get("improvements_needed") and len(feedback["improvements_needed"]) > 0:
        feedback_parts.append(f"\n**IMPROVEMENTS NEEDED**:\n" + "\n".join([f"- {item}" for item in feedback["improvements_needed"]]))
    
    if feedback_parts:
        parts.append("**EVALUATION FEEDBACK**:\n")
        parts.append("\n".join(feedback_parts))
        parts.append("\n\n")
    
    # Add context
    if context:
        max_context_chars = 8000
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n\n[CONTEXT TRUNCATED]"
        
        parts.append(f"""**REFERENCE CONTEXT** (use to add facts, data, examples):
---
{context}
---

""")
    
    parts.append(f"""**TASK**: Generate an improved version of the student's answer based on the feedback above.

**Requirements**:
1. Preserve the student's voice and original points where possible
2. Address ALL feedback points (missing elements, improvements needed, structure issues)
3. Use REFERENCE CONTEXT to add facts, data, reports, and examples
4. Follow strict IBC format (Introduction-Body-Conclusion)
5. Target word count: approximately {word_count} words
6. Include visuals (maps/diagrams/tables) if feedback indicated they were missing
7. Every bullet must have: evidence (report/data) + example (India/World)
8. Ensure directive alignment if directive word was identified in feedback

Return ONLY the improved answer in markdown format. No JSON, no explanation, just the answer.""")
    
    return "".join(parts)


# ============================================================
# TASK 3: MAINS ANSWER GENERATION
# ============================================================


# ============================================================
# HELPER FUNCTIONS FOR MAINS ANSWER
# ============================================================

def clean_gemini_error(error_msg: str) -> str:
    """Clean Gemini API error messages for user-friendly display"""
    # For quota errors (429)
    if '429' in error_msg or 'ResourceExhausted' in error_msg:
        return "You exceeded your current quota. Check usage at https://ai.dev/usage?tab=rate-limit."
    
    # For auth errors
    lower_msg = error_msg.lower()
    if 'api_key_invalid' in error_msg or 'api key not valid' in lower_msg or 'invalid api key' in lower_msg:
        return "Invalid Gemini API key. Please update your API key in Settings."
        
    return f"AI Error: {error_msg[:150]}..."


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
        
        # Initialize resources (using cached factory for consistency)
        gemini_client = get_gemini_client(ctx, gemini_api_key, "gemini-2.5-pro")
        flash_client = get_gemini_client(ctx, gemini_api_key, settings.GEMINI_MODEL_FLASH)
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
        
        try:
            # Re-applied increased timeout for mock test generation
            async with redis.lock(lock_key, timeout=600, blocking_timeout=70):
                 await check_cancellation(ctx, job_id)
                 logger.info(f"🤖 [JOB {job_id}] Calling Gemini (Locked)...")
                 
                 # Create API call task
                 gemini_task = asyncio.create_task(gemini_client.generate_response(
                     user_prompt=prompt_pair["user"],
                     system_prompt=prompt_pair["system"],
                     temperature=0.15,
                     max_retries=2
                 ))
                 
                 # Create cancellation watcher task
                 async def watch_for_cancel():
                     while True:
                         await check_cancellation(ctx, job_id)  # Raises CancelledError if flag set
                         await asyncio.sleep(1)
                         
                 cancel_task = asyncio.create_task(watch_for_cancel())
                 
                 try:
                     done, pending = await asyncio.wait(
                         [gemini_task, cancel_task],
                         return_when=asyncio.FIRST_COMPLETED
                     )
                     
                     # Cancel pending tasks
                     for task in pending:
                         task.cancel()
                         
                     if gemini_task in done:
                         # API call finished naturally (success or error)
                         response_text = gemini_task.result()
                     else:
                         # Cancellation task finished (meaning flag was found -> error raised)
                         await cancel_task # Re-raise the cancellation error
                         
                 except Exception:
                     # Ensure we don't leave zombie API tasks
                     if not gemini_task.done():
                         gemini_task.cancel()
                     raise
        except Exception as e:
            error_msg = clean_gemini_error(str(e))
            logger.error(f"❌ [JOB {job_id}] Generation failed: {error_msg}")
            
            # Update Redis status so frontend polling sees the error
            await set_job_error(redis, job_id, error_msg)
            
            return {
                "status": "failed",
                "error": error_msg,
                "job_id": job_id
            }
             
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
                 gemini_client=gemini_client,
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
    functions = [generate_mock_test_task, evaluate_answer_task, evaluate_batch_answers_task, generate_improved_answer_task, generate_mains_answer_task]
    redis_settings = REDIS_SETTINGS
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20      # Handling I/O bound tasks (Gemini API), manageable for single worker
    # Job timeout (Re-applied to allow long-running batch evaluation/OCR)
    job_timeout = 900  # 15 minutes max per job
    max_tries = 1      # Do not retry jobs on failure/cancellation

if __name__ == "__main__":
    import sys
    from arq import run_worker
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        sys.exit(0)
