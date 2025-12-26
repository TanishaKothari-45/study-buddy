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
    
    1. OCR (Question Extraction + Word Count Detection):
       - If question not provided, use Gemini to extract question from uploaded files
       - Extract word count from question (10 marks -> 150 words, 15 marks -> 250 words)
       - Uses Gemini Pro with OCR capabilities (PDF/image reading)
       - Locked briefly to prevent concurrent API calls
    
    2. TRAINING EXAMPLES:
       - Loads few-shot examples from training_examples.json
       - Provides examples of good feedback patterns
    
    3. PROMPT BUILDING:
       - Builds evaluation prompt with:
         * Question
         * Training examples (few-shot learning)
         * Instructions for feedback ONLY (no improved answer)
    
    4. GEMINI EVALUATION (Locked):
       - Sends prompt + student's handwritten answer (PDF/image) to Gemini 2.5 Pro
       - Gemini performs OCR on handwritten answer
       - Gemini evaluates and returns JSON with detailed feedback ONLY
    
    5. RESPONSE PARSING:
       - Parses JSON response
       - Extracts feedback structure only
       - Handles parsing errors gracefully
    
    6. RESULT SAVING:
       - Saves feedback result to Redis
       - Includes: question, student_answer, feedback, word_count
    
    KEY FEATURES:
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
        
        # Initialize Gemini Client
        gemini_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_PRO)
        
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

        # ============================================================
        # STEP 1: Extract question from files if not provided (OCR + Word Count)
        # ============================================================
        identified_question = question
        word_count_int = 250  # Default
        
        if not identified_question:
            logger.info(f"📝 [JOB {job_id}] STEP 1: Extracting question from files...")
            try:
                question_prompt = """Read the handwritten answer and identify:
1. The QUESTION text
2. The marks/word count (e.g., "10 marks" or "15 marks" or "150 words" or "250 words")

Return in format:
QUESTION: [question text]
MARKS: [10 or 15 or detected word count]
If marks are 10, word count is 150. If marks are 15, word count is 250."""
                
                lock_key = f"lock:user:{user_id}"
                lock = RedisLock(redis, lock_key, timeout=60)
                if await lock.acquire(blocking=True, blocking_timeout=60):
                    try:
                        if all_is_pdf:
                            question_response = await gemini_client.generate_response(question_prompt, pdf_path=file_paths[0], temperature=0.0)
                        else:
                            question_response = await gemini_client.generate_response(question_prompt, image_path=file_paths[0], temperature=0.0)
                        
                        # Parse response to extract question and word count
                        response_text = question_response.strip()
                        lines = response_text.split('\n')
                        for line in lines:
                            if line.startswith('QUESTION:'):
                                identified_question = line.replace('QUESTION:', '').strip()
                            elif line.startswith('MARKS:'):
                                marks_text = line.replace('MARKS:', '').strip()
                                # Extract number
                                import re
                                marks_match = re.search(r'\d+', marks_text)
                                if marks_match:
                                    marks = int(marks_match.group())
                                    if marks == 10:
                                        word_count_int = 150
                                    elif marks == 15:
                                        word_count_int = 250
                                    else:
                                        # Check if it's already a word count
                                        if '150' in marks_text or marks == 150:
                                            word_count_int = 150
                                        elif '250' in marks_text or marks == 250:
                                            word_count_int = 250
                        
                        if not identified_question:
                            identified_question = response_text.split('\n')[0].replace('QUESTION:', '').strip()
                        
                        logger.info(f"✅ [JOB {job_id}] Identified question: {identified_question[:100]}...")
                        logger.info(f"✅ [JOB {job_id}] Detected word count: {word_count_int}")
                    finally:
                        await lock.release()
                else:
                    raise Exception("Could not acquire user lock for OCR after 60s")
            except Exception as e:
                logger.warning(f"⚠️ [JOB {job_id}] Failed to identify question: {e}")
                identified_question = question or "Question not identified"
        else:
            logger.info(f"📝 [JOB {job_id}] STEP 1: Using provided question")
            # Try to extract word count from question text
            import re
            marks_match = re.search(r'(\d+)\s*marks?', identified_question, re.IGNORECASE)
            if marks_match:
                marks = int(marks_match.group(1))
                if marks == 10:
                    word_count_int = 150
                elif marks == 15:
                    word_count_int = 250
        
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
        # STEP 2: Build evaluation prompt (feedback only, no context)
        # ============================================================
        logger.info(f"📝 [JOB {job_id}] STEP 2: Building evaluation prompt...")
        user_prompt = _build_evaluation_prompt(
            identified_question=identified_question,
            training_examples=training_examples,
            word_count=word_count_int
        )
        
        # ============================================================
        # STEP 3: Call Gemini WITH USER LOCK
        # ============================================================
        logger.info(f"🤖 [JOB {job_id}] STEP 3: Calling Gemini with user lock...")
        
        async with redis.lock(f"lock:user:{user_id}", timeout=120, blocking_timeout=70):
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
        # STEP 4: Parse response (feedback only)
        # ============================================================
        logger.info(f"🔍 [JOB {job_id}] STEP 4: Parsing response...")
        feedback = _parse_evaluation_response(response_text)
        
        # ============================================================
        # STEP 5: Save Result (feedback only)
        # ============================================================
        logger.info(f"💾 [JOB {job_id}] STEP 5: Saving result...")
        
        result = {
            "question": identified_question,
            "student_answer": "Answer extracted by Gemini",
            "feedback": feedback,
            "word_count": word_count_int,
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
    identified_question: str,
    training_examples: List[dict],
    word_count: int
) -> str:
    """Build the evaluation user prompt (feedback only, no context)"""
    parts = [f"**QUESTION**: {identified_question}\n\n"]
    parts.append(f"**EXPECTED WORD COUNT**: {word_count} words (based on question marks/requirements)\n\n")
    
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
    
    parts.append(f"""\n**TASK**: Read the student's handwritten answer from the uploaded file and provide detailed feedback.

**Requirements for Feedback**:
1. Identify specific strengths in the student's answer
2. Point out missing elements (facts, examples, structure, visuals)
3. Provide actionable improvement suggestions
4. Comment on IBC format adherence and evidence usage
5. Assess directive alignment (if directive word is present in question)
6. Comment on whether visuals (maps/diagrams/tables) were needed but missing
7. Give an overall encouraging assessment
{f'8. Learn from the {len(training_examples)} few-shot examples above to provide similar quality feedback' if training_examples else ''}

**Note**: This is FEEDBACK ONLY. Do NOT generate an improved answer. Focus solely on evaluating the student's work.

Return ONLY a valid JSON object as specified in the system prompt. No markdown code blocks, no commentary.""")
    
    return "".join(parts)


def _parse_evaluation_response(response_text: str) -> dict:
    """Parse Gemini's evaluation response (feedback only)"""
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
            "missing_elements": feedback_data.get("missing_elements", []),
            "improvements_needed": feedback_data.get("improvements_needed", []),
            "section_wise_assessment": feedback_data.get("section_wise_assessment", {
                "introduction": "",
                "body": "",
                "conclusion": ""
            }),
            "directive_alignment": feedback_data.get("directive_alignment"),
            "evidence_feedback": feedback_data.get("evidence_feedback", ""),
            "visual_feedback": feedback_data.get("visual_feedback"),
            "examiner_expectation_gap": feedback_data.get("examiner_expectation_gap"),
            "strategy_tip": feedback_data.get("strategy_tip"),
            "overall_assessment": feedback_data.get("overall_assessment", ""),
            "margin_comments": feedback_data.get("margin_comments", [])
        }
        
        return feedback
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse evaluation response as JSON: {e}")
        # Fallback: return minimal feedback structure
        return {
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
            "missing_elements": [],
            "improvements_needed": [],
            "section_wise_assessment": {
                "introduction": "",
                "body": "",
                "conclusion": ""
            },
            "directive_alignment": None,
            "evidence_feedback": "Unable to parse structured feedback from response",
            "visual_feedback": None,
            "examiner_expectation_gap": None,
            "strategy_tip": None,
            "overall_assessment": "Evaluation completed but response format was unexpected.",
            "margin_comments": []
        }


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
    
    FLOW:
    1. Split PDF into answer chunks using regex (Q1, Q2, etc.)
    2. For each answer chunk:
       - OCR and extract question
       - Run evaluation pipeline
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
        
        # Import answer splitter
        from .utils.answer_splitter import split_pdf_by_answers
        
        # Step 1: Split PDF into answer chunks
        logger.info(f"📄 [BATCH JOB {job_id}] Step 1: Splitting PDF into answer chunks...")
        output_dir = Path(pdf_path).parent / f"batch_{job_id}"
        answer_chunks = split_pdf_by_answers(
            pdf_path, 
            str(output_dir), 
            use_standard_format=use_standard_format,
            question_file_path=question_file_path,
            question_texts=question_texts
        )
        
        if not answer_chunks:
            raise Exception("No answer chunks detected in PDF")
        
        # Enforce max 20 answers
        if len(answer_chunks) > 20:
            logger.warning(f"⚠️ [BATCH JOB {job_id}] Limiting to 20 answers (found {len(answer_chunks)})")
            answer_chunks = answer_chunks[:20]
        
        batch_data["total_answers"] = len(answer_chunks)
        logger.info(f"✅ [BATCH JOB {job_id}] Split into {len(answer_chunks)} answer chunks")
        
        # Log detected question numbers
        q_nums = [chunk.get("question_number", idx + 1) for idx, chunk in enumerate(answer_chunks)]
        logger.info(f"📋 [BATCH JOB {job_id}] Detected question numbers: {q_nums}")
        
        # Initialize Gemini Client
        gemini_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_PRO)
        
        # Import shared prompt
        try:
            from .prompts.shared_mains_prompts import get_evaluation_system_prompt
            system_prompt = get_evaluation_system_prompt()
        except ImportError:
            logger.warning("⚠️ Using fallback generic system prompt")
            system_prompt = "You are an expert evaluator. Provide detailed feedback on the student's answer."
        
        # Load training examples
        training_examples = []
        try:
            training_data_file = Path(__file__).parent.parent.parent / "data" / "training_examples.json"
            if training_data_file.exists():
                with open(training_data_file, 'r', encoding='utf-8') as f:
                    training_data = json.load(f)
                    all_examples = training_data.get("training_examples", [])
                    training_examples = all_examples[-3:] if len(all_examples) > 3 else all_examples
        except Exception as e:
            logger.debug(f"No training examples loaded: {e}")
        
        # Step 2: Process each answer sequentially
        logger.info(f"🔄 [BATCH JOB {job_id}] Step 2: Processing {len(answer_chunks)} answers sequentially...")
        
        batch_cancelled = False
        
        for idx, chunk in enumerate(answer_chunks):
            answer_id = chunk["answer_id"]
            answer_file_path = chunk["file_path"]
            question_number = chunk["question_number"]  # Actual question number (preserved)
            marks = chunk.get("marks")  # Optional marks indicator
            
            logger.info(f"📝 [BATCH JOB {job_id}] Processing answer {idx + 1}/{len(answer_chunks)}: {answer_id} (Q{question_number}" + 
                       (f", {marks} marks" if marks else "") + ")")
            
            # Check cancellation
            try:
                await check_cancellation(ctx, job_id)
            except asyncio.CancelledError:
                logger.info(f"🚫 [BATCH JOB {job_id}] Batch cancelled by user")
                batch_cancelled = True
                break
            
            # Initialize answer status
            answer_data = {
                "answer_id": answer_id,
                "question_number": question_number,  # Actual question number
                "status": "processing",
                "evaluation": None,
                "error": None
            }
            
            # Add marks if available
            if marks:
                answer_data["marks"] = marks
            batch_data["answers"].append(answer_data)
            await set_job_status(redis, job_id, "processing", batch_data=json.dumps(batch_data))
            
            try:
                # Extract question from answer PDF
                question_prompt = """Read the handwritten answer and identify:
1. The QUESTION text
2. The marks/word count (e.g., "10 marks" or "15 marks" or "150 words" or "250 words")

Return in format:
QUESTION: [question text]
MARKS: [10 or 15 or detected word count]
If marks are 10, word count is 150. If marks are 15, word count is 250."""
                
                identified_question = None
                word_count_int = 250  # Default
                
                # Acquire lock for question extraction
                lock_key = f"lock:user:{user_id}"
                async with redis.lock(lock_key, timeout=60, blocking_timeout=60):
                    try:
                        question_response = await gemini_client.generate_response(
                            question_prompt,
                            pdf_path=answer_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                        
                        # Parse response
                        response_text = question_response.strip()
                        lines = response_text.split('\n')
                        for line in lines:
                            if line.startswith('QUESTION:'):
                                identified_question = line.replace('QUESTION:', '').strip()
                            elif line.startswith('MARKS:'):
                                marks_text = line.replace('MARKS:', '').strip()
                                import re
                                marks_match = re.search(r'\d+', marks_text)
                                if marks_match:
                                    marks = int(marks_match.group())
                                    if marks == 10:
                                        word_count_int = 150
                                    elif marks == 15:
                                        word_count_int = 250
                        
                        if not identified_question:
                            identified_question = response_text.split('\n')[0].replace('QUESTION:', '').strip() or f"Question {question_number}"
                        
                    except Exception as e:
                        error_str = str(e).lower()
                        # Check for fatal errors (429/401)
                        if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str or 'api key' in error_str:
                            logger.error(f"❌ [BATCH JOB {job_id}] Fatal error (429/401) at answer {answer_id}: {e}")
                            batch_cancelled = True
                            raise  # Re-raise to cancel batch
                        # Transient error - mark as failed and continue
                        logger.warning(f"⚠️ [BATCH JOB {job_id}] Failed to extract question for {answer_id}: {e}")
                        identified_question = f"Question {question_number}"
                
                if batch_cancelled:
                    break
                
                # Build evaluation prompt
                user_prompt = _build_evaluation_prompt(
                    identified_question=identified_question,
                    training_examples=training_examples,
                    word_count=word_count_int
                )
                
                # Call Gemini for evaluation (with lock)
                async with redis.lock(lock_key, timeout=120, blocking_timeout=70):
                    await check_cancellation(ctx, job_id)
                    
                    try:
                        response_text = await gemini_client.generate_response(
                            user_prompt=user_prompt,
                            system_prompt=system_prompt,
                            pdf_path=answer_file_path,
                            temperature=0.2,
                            max_retries=2  # Max 2 retries per answer
                        )
                        
                        # Parse evaluation response
                        feedback = _parse_evaluation_response(response_text)
                        
                        # Mark answer as completed
                        answer_data["status"] = "completed"
                        answer_data["evaluation"] = {
                            "question": identified_question,
                            "feedback": feedback,
                            "word_count": word_count_int
                        }
                        batch_data["completed_answers"] += 1
                        
                        logger.info(f"✅ [BATCH JOB {job_id}] Completed answer {answer_id}")
                        
                    except Exception as e:
                        error_str = str(e).lower()
                        # Check for fatal errors (429/401)
                        if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str or 'api key' in error_str:
                            logger.error(f"❌ [BATCH JOB {job_id}] Fatal error (429/401) at answer {answer_id}: {e}")
                            batch_cancelled = True
                            raise  # Re-raise to cancel batch
                        
                        # Transient error - mark as failed and continue
                        logger.warning(f"⚠️ [BATCH JOB {job_id}] Failed to evaluate answer {answer_id}: {e}")
                        answer_data["status"] = "failed"
                        answer_data["error"] = clean_gemini_error(str(e))
                        batch_data["failed_answers"] += 1
                
                if batch_cancelled:
                    break
                
            except asyncio.CancelledError:
                batch_cancelled = True
                break
            except Exception as e:
                error_str = str(e).lower()
                # Check for fatal errors
                if '429' in error_str or 'quota' in error_str or '401' in error_str or '403' in error_str or 'api key' in error_str:
                    logger.error(f"❌ [BATCH JOB {job_id}] Fatal error (429/401): {e}")
                    batch_cancelled = True
                    answer_data["status"] = "failed"
                    answer_data["error"] = clean_gemini_error(str(e))
                    batch_data["failed_answers"] += 1
                    break
                else:
                    # Transient error
                    logger.warning(f"⚠️ [BATCH JOB {job_id}] Error processing answer {answer_id}: {e}")
                    answer_data["status"] = "failed"
                    answer_data["error"] = clean_gemini_error(str(e))
                    batch_data["failed_answers"] += 1
            
            # Update progress
            await set_job_status(redis, job_id, "processing", batch_data=json.dumps(batch_data))
            # Also store separately for easy retrieval
            await redis.set(f"job_batch_data:{job_id}", json.dumps(batch_data), ex=7200)
        
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
        # Cleanup: Remove split PDFs and temp directory
        try:
            if 'output_dir' in locals():
                import shutil
                if Path(output_dir).exists():
                    shutil.rmtree(output_dir)
                    logger.info(f"🧹 [BATCH JOB {job_id}] Cleaned up temp directory")
        except Exception as e:
            logger.warning(f"⚠️ [BATCH JOB {job_id}] Failed to cleanup: {e}")
        
        # Cleanup original PDF if it was in temp directory
        try:
            if Path(pdf_path).parent.name == "temp":
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
        except:
            pass
        
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
        
        # Initialize Gemini Client
        gemini_client = GeminiClient(api_key=gemini_api_key, model_name=settings.GEMINI_MODEL_PRO)
        
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
        
        try:
            async with redis.lock(lock_key, timeout=120, blocking_timeout=70):
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
    job_timeout = 300  # 5 minutes max per job
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
