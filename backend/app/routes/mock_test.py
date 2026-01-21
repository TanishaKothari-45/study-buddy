"""
Mock test generation endpoint
"""
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import os
import random
import logging
import time
import asyncio
import math
from uuid import uuid4
from datetime import datetime
from collections import defaultdict
# from openai import OpenAI, RateLimitError  # No longer used for generation
import numpy as np

from ..core.config import settings
from ..core.deps import get_redis_client
from ..utils.metadata_enricher import GEOGRAPHY_TOPICS, GEOGRAPHY_DOMAINS
from ..utils.mm_utils import enforce_source_diversity
from ..utils.mock_test_prompting import assemble_upsc_prompt
from ..utils.query_builder import build_query_text, build_current_affairs_query
from ..utils.memory_manager import (
    init_memory_db,
    get_recent_questions,
    filter_recency,
    record_recent_question,
    record_feedback
)

from ..utils.semantic_dedup import semantic_deduplicate, hash_based_deduplicate
from ..gemini_core.gemini_client import GeminiClient
from ..gemini_core.settings_gemini_key import GEMINI_API_KEY
from ..utils.question_provenance import QuestionProvenance, get_question_bank
from ..utils.job_tracker import get_job_store, JobStatus
from ..utils.batch_validator import validate_batch, calculate_quality_score

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize memory database (only once at startup)
init_memory_db()

class MockTestRequest(BaseModel):
    num_questions: int = 5
    topics: List[str] = []  # Optional topics to focus on
    subject: str = "general"  # ncert, current_affairs, general

class QuestionSource(BaseModel):
    topic: str
    sub_domain: str

class MockTestQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    source: QuestionSource

class GeneratedQuestions(BaseModel):
    questions: List[MockTestQuestion]

class MockTestResponse(BaseModel):
    questions: List[MockTestQuestion]
    total_marks: int
    time_allowed: str
    instructions: List[str]


def sanitize_json_response(text: str) -> str:
    """Extract JSON from potential markdown code blocks."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return text

async def generate_question_paper(pyq_chunks: List[Dict], content_chunks: List[Dict], 
                            request: MockTestRequest, api_key: str, app_state=None) -> MockTestResponse:
    """
    Generate UPSC-style mock test questions using style learning + content knowledge.
    
    Style Learning (30% of prompt):
    - 40% PYQ chunks (from database)
    - 40% from patterns JSON
    - 30% from feedback (if available)
    
    Content Knowledge (70% of prompt):
    - Concept chunks (NCERT, Vision notes)
    - Current affairs chunks (if medium/hard)
    
    Cost Optimization Strategy:
    - Embeddings: Already using text-embedding-3-small (cheap)
    - Question Generation: Uses gpt-4o (large model) for quality
    - Other tasks (evaluation, query, etc.): Use gpt-4o-mini (small model)
    
    This balances cost (~90% tasks use mini) with quality (final questions use 4o).
    """
    # Prepare static text from content chunks
    content_text = "\n\n".join([chunk['content'] for chunk in content_chunks[:20]])
    logger.info(f"✅ Prepared content context from {len(content_chunks)} optimized chunks")
    
    # Extract topic from request (use first topic or "Geography" as default)
    topic = request.topics[0] if request.topics else "Geography"
    
    # Assemble prompt using direct pyq_chunks
    user_prompt = assemble_upsc_prompt(
        topic=topic,
        num_questions=request.num_questions,
        retrieved_static_text=content_text,
        retrieved_current_affairs="",
        pyq_chunks=pyq_chunks
    )
    
    logger.info(f"📊 Prompt composition: {len(content_chunks)} optimized chunks and {len(pyq_chunks) if pyq_chunks else 0} PYQ chunks")
    
    # Use GeminiClient for generation with structured output
    try:
        
        # Use GeminiClient for generation with structured output
        if not GEMINI_API_KEY:
            raise HTTPException(500, "Gemini API key not configured")
            
        gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
        
        # Use large model for final question generation
        # Passed Pydantic model is automatically cleaned by GeminiClient
        response_text = await gemini_client.generate_response(
            user_prompt=user_prompt,
            system_prompt="You are a UPSC Prelims question setter. Output valid JSON array for 'questions' key and nothing else.",
            response_schema=GeneratedQuestions,
            temperature=0.7
        )
        
        # Parse JSON response
        import json
        try:
            # Structured generation ensures valid JSON without markdown wrapping
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
        except json.JSONDecodeError:
            # Fallback: try to extract questions from text if something went fundamentally wrong
            logger.warning("Failed to parse Structured response, using fallback sanitization")
            sanitized_text = sanitize_json_response(response_text)
            try:
                response_data = json.loads(sanitized_text)
                questions_data = response_data.get("questions", [])
            except:
                questions_data = []
        
        # Convert to MockTestQuestion objects
        questions = []
        # Get embedder from app_state (passed from route) or from request if available
        embedder = None
        if app_state and hasattr(app_state, 'vector_handler'):
            embedder = app_state.vector_handler.embedder
        elif hasattr(request, 'app') and hasattr(request.app.state, 'vector_handler'):
            embedder = request.app.state.vector_handler.embedder
        
        for i, q_data in enumerate(questions_data):
            if isinstance(q_data, dict):
                # Handle options - convert dict to list if needed
                options_raw = q_data.get("options", [])
                if isinstance(options_raw, dict):
                    # Convert dict like {"A": "option1", "B": "option2"} to list ["option1", "option2", ...]
                    options_list = [options_raw.get(key, "") for key in ["A", "B", "C", "D"]]
                    # Filter out empty strings in case some keys are missing
                    options_list = [opt for opt in options_list if opt]
                elif isinstance(options_raw, list):
                    options_list = options_raw
                else:
                    options_list = ["A", "B", "C", "D"]  # Fallback
                
                question_text = q_data.get("question", f"Question {i+1}")
                
                question = MockTestQuestion(
                    question=question_text,
                    options=options_list,
                    correct_answer=q_data.get("correct_answer", "A"),
                    explanation=q_data.get("explanation", "No explanation provided"),
                    source={
                        "filename": "Generated", 
                        "chapter": "Mock Test", 
                        "section": f"Question {i+1}",
                        "question_id": f"mock_{int(time.time())}_{i}",  # Generate unique ID
                        "topics": q_data.get("source", {}).get("topics", request.topics)
                    }
                )
                questions.append(question)
                
                # 🆕 STEP 5: Memory Update - Store question in recency DB
                # 🆕 STEP 5: Memory Update - Store question in recency DB
                try:
                    # Extract topic and subtopic from request
                    topic = request.topics[0] if request.topics else "Geography"
                    subtopic = request.topics[1] if len(request.topics) > 1 else topic
                    
                    # Store in recency DB
                    record_recent_question(
                        question_text=question_text,
                        topic=topic,
                        subtopic=subtopic
                    )
                    logger.debug(f"✅ Stored question {i+1} in recency DB")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to store question in recency DB: {e}")
                    # Continue even if storage fails
        
        # If no questions were parsed, create a fallback
        if not questions:
            questions = [MockTestQuestion(
                question="What is the primary focus of Geography as a discipline?",
                options=[
                    "Study of physical features only",
                    "Study of human-environment interactions",
                    "Study of maps and cartography",
                    "Study of weather patterns"
                ],
                correct_answer="B",
                explanation="Geography is the study of human-environment interactions, encompassing both physical and human aspects.",
                source={"filename": "Generated", "chapter": "Mock Test", "section": "Fallback Question"}
            )]
        
        # Calculate time allowed: 2 hours for 100 questions = 1.2 minutes per question
        minutes_per_question = 1.2
        total_minutes = len(questions) * minutes_per_question
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        if hours > 0:
            time_allowed = f"{hours} hour{'s' if hours > 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            time_allowed = f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        # Create response with updated instructions based on scoring
        total_marks = len(questions) * 2
        instructions = [
            "Attempt all questions.",
            f"Each question carries 2 marks.",
            f"Total marks: {total_marks}.",
            "Negative marking: -0.67 marks (1/3 of 2 marks) for each wrong answer.",
            "No marks deducted for unanswered questions.",
            "Choose the most appropriate option.",
            "Questions are based on your uploaded study materials."
        ]
        
        return MockTestResponse(
            questions=questions,
            total_marks=total_marks,
            time_allowed=time_allowed,
            instructions=instructions
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to generate mock test: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate mock test. Please try again."
        )

def is_pyq_chunk(chunk: Dict[str, Any]) -> bool:
    """Check if a chunk is from a PYQ (Previous Year Question) file"""
    metadata = chunk.get("metadata", {})
    filename = metadata.get("filename", "").lower()
    
    # PYQ filename patterns
    pyq_patterns = [
        "geography-pyq topic wise",
        "geography_questions_in_upsc_prelims",
        "pyq",
        "prelims",
        "previous year"
    ]
    
    return any(pattern in filename for pattern in pyq_patterns)

def map_topics_to_domains(topics: List[str]) -> Dict[str, List[str]]:
    """
    Map user-selected topics to major_domain and sub_domain values.
    
    Returns:
        Dict with 'major_domains' and 'sub_domains' lists
    """
    major_domains = []
    sub_domains = []
    
    topics_lower = [t.lower() for t in topics]
    
    # Map topics to domains
    for domain, subtopics in GEOGRAPHY_TOPICS.items():
        for sub in subtopics:
            sub_lower = sub.lower()
            # Check if any user topic matches this sub_domain
            if any(topic in sub_lower or sub_lower in topic for topic in topics_lower):
                if domain not in major_domains:
                    major_domains.append(domain)
                if sub not in sub_domains:
                    sub_domains.append(sub)
    
    # Also check direct domain matches
    domain_names = [d.lower() for d in GEOGRAPHY_TOPICS.keys()]
    for topic in topics_lower:
        for domain in GEOGRAPHY_TOPICS.keys():
            if topic in domain.lower() or domain.lower() in topic:
                if domain not in major_domains:
                    major_domains.append(domain)
    
    return {
        "major_domains": major_domains,
        "sub_domains": sub_domains
    }

   

def is_actual_question_chunk(chunk: Dict[str, Any]) -> bool:
    """Check if a chunk contains an actual UPSC question (not index/contents page)"""
    content = chunk.get("content", "").lower()
    
    # Indicators of actual questions
    question_indicators = [
        "which of the following",
        "consider the following",
        "statement-i",
        "statement-ii",
        "select the correct",
        "choose the correct",
        "what is",
        "how many",
        "match the following"
    ]
    
    # Exclude index/contents pages
    exclude_indicators = [
        "contents",
        "index",
        "chapter",
        "page",
        "table of contents"
    ]
    
    # Check for question indicators
    has_question = any(indicator in content for indicator in question_indicators)
    
    # Check for exclude indicators (if too many, likely not a question)
    exclude_count = sum(1 for indicator in exclude_indicators if indicator in content)
    
    # Consider it a question if it has question indicators and few exclude indicators
    return has_question and exclude_count < 3

def extract_domains_from_topics(topics: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract major_domain and sub_domain from topics list.
    
    Since topics now come from dropdowns, they should match exactly with GEOGRAPHY_DOMAINS.
    Returns the first matching major_domain and sub_domain found.
    
    Args:
        topics: List of topic strings (can be sub-domains or major domains)
    
    Returns:
        Tuple of (major_domain, sub_domain) or (None, None) if not found
    """
    if not topics:
        return None, None
    
    major_domain = None
    sub_domain = None
    
    topics_lower = [t.lower() for t in topics]
    
    # First, check if any topic is a direct major domain match
    for domain in GEOGRAPHY_DOMAINS.keys():
        if domain.lower() in topics_lower or any(domain.lower() == t for t in topics_lower):
            major_domain = domain
            break
    
    # Then, check if any topic is a sub-domain
    for domain, subdomains in GEOGRAPHY_DOMAINS.items():
        for sub in subdomains:
            if sub.lower() in topics_lower or any(sub.lower() == t for t in topics_lower):
                sub_domain = sub
                # If we found a sub-domain, its parent is the major domain
                if not major_domain:
                    major_domain = domain
                break
        if sub_domain:
            break
    
    # If we found a sub-domain but no major domain, find the parent
    if sub_domain and not major_domain:
        for domain, subdomains in GEOGRAPHY_DOMAINS.items():
            if sub_domain in subdomains:
                major_domain = domain
                break
    
    logger.info(f"📌 Extracted domains from topics {topics}: major_domain={major_domain}, sub_domain={sub_domain}")
    return major_domain, sub_domain
def bucket_chunks_by_metadata(chunks: List[Dict], major_domain: Optional[str], sub_domain: Optional[str]) -> Dict[str, List[Dict]]:
    """
    Cluster chunks into buckets based on metadata hierarchy.
    - If no topic selection: Bucket by major_domain
    - If major_domain selected: Bucket by sub_domain
    - If sub_domain selected: Bucket by section / micro_topic
    """
    buckets = defaultdict(list)
    
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        
        if not major_domain:
            # Level 1: Bucket by Major Domain
            bucket_key = meta.get("major_domain") or meta.get("domain") or "General"
        elif not sub_domain:
            # Level 2: Bucket by Sub Domain
            bucket_key = meta.get("sub_domain") or meta.get("major_domain") or "General"
        else:
            # Level 3: Bucket by Section / Micro Topic
            bucket_key = meta.get("section") or meta.get("chapter") or meta.get("sub_domain") or "General"
            
        buckets[bucket_key].append(chunk)
        
    return buckets

def hybrid_retrieve_for_mock_test(
    pinecone_handler,
    topics: List[str],
    num_questions: int = 10,
    subject: str = "general"
) -> Tuple[List[Dict], List[Dict]]:
    """
    Advanced bucket-based retrieval for mock tests.
    1. Fetch n*10 context chunks (source_type != 'pyq')
    2. Bucket by metadata hierarchy (Domain -> Sub-domain -> Micro-topic)
    3. MMR (lambda=0.5) selection per bucket to get n*7 total chunks
    4. Fetch 10 PYQ chunks for style learning
    """
    # Extract domains from topics
    major_domain, sub_domain = extract_domains_from_topics(topics)
    
    # 🎯 Build direct semantic query
    from ..utils.query_builder import build_query_text
    query = build_query_text(major_domain, sub_domain, subject=subject)
    
    logger.info(f"🎯 [BUCKET_RETRIEVE] Starting retrieval: major_domain={major_domain}, sub_domain={sub_domain}, questions={num_questions}")
    
    # ================================
    # 1️⃣ Raw Content Fetch (n * 10)
    # ================================
    target_fetch = num_questions * 10
    logger.info(f"📘 Fetching {target_fetch} content chunks (excluding PYQs)...")
    
    try:
        # Fetch raw concept and current_affairs chunks
        # metadata filter: source_type IN ['concept', 'current_affairs']
        content_filter = {"source_type": {"$in": ["concept", "current_affairs"]}}
        
        # Use direct Pinecone metadata (use_content_store=False) for initial fetch
        # This avoids 50 SQL queries since we only need metadata for bucketing
        raw_chunks = pinecone_handler.query_documents(
            query_text=query,
            k=target_fetch,
            filter_metadata=content_filter,
            use_content_store=False
        )
        logger.info(f"   ✅ Retrieved {len(raw_chunks)} raw content chunks (using direct Pinecone metadata)")
        
        # ================================
        # 2️⃣ Metadata Bucketing
        # ================================
        buckets = bucket_chunks_by_metadata(raw_chunks, major_domain, sub_domain)
        bucket_stats = {k: len(v) for k, v in buckets.items()}
        logger.info(f"   📊 Formed {len(buckets)} buckets: {bucket_stats}")
        
        # Pre-embed query and all chunks once to minimize Embedding calls
        logger.info(f"   📝 Pre-embedding query and {len(raw_chunks)} chunks for efficient MMR...")
        query_embedding = np.array(pinecone_handler.langchain_embeddings.embed_query(query))
        
        all_chunk_texts = [c.get("content", "") for c in raw_chunks]
        all_chunk_embeddings = [np.array(emb) for emb in pinecone_handler.langchain_embeddings.embed_documents(all_chunk_texts)]
        
        # Create a mapping from chunk content to embedding for quick lookup
        # (Using content as key is safe here because chunks are distinct or from same list)
        # Better: use index mapping
        chunk_to_emb = {i: emb for i, emb in enumerate(all_chunk_embeddings)}
        
        # Map raw chunks to their indices for retrieval during MMR
        chunk_id_map = {id(c): i for i, c in enumerate(raw_chunks)}
        
        # ================================
        # 3️⃣ Per-Bucket MMR Selection (Target: n * 7)
        # ================================
        total_target = num_questions * 7
        final_selected_chunks = []
        
        if buckets:
            # 1. First Pass: Distribute share evenly
            share_per_bucket = math.ceil(total_target / len(buckets))
            remaining_target = total_target
            
            # Sort buckets by size (greedy fills from largest first if share allows)
            sorted_bucket_keys = sorted(buckets.keys(), key=lambda k: len(buckets[k]), reverse=True)
            
            # Greedy allocation logic
            bucket_allotments = {}
            for k in sorted_bucket_keys:
                allotment = min(len(buckets[k]), share_per_bucket)
                bucket_allotments[k] = allotment
                remaining_target -= allotment
            
            # 2. Second Pass: If we still have capacity (some buckets were small), redistribute to larger ones
            if remaining_target > 0:
                for k in sorted_bucket_keys:
                    can_take_more = len(buckets[k]) - bucket_allotments[k]
                    take = min(can_take_more, remaining_target)
                    bucket_allotments[k] += take
                    remaining_target -= take
                    if remaining_target <= 0: break
            
            logger.info(f"   🔄 Allocation: {bucket_allotments}")
            
            for bucket_key, count in bucket_allotments.items():
                if count <= 0: continue
                
                bucket_chunks = buckets[bucket_key]
                # Get embeddings for chunks in this bucket
                bucket_embs = [chunk_to_emb[chunk_id_map[id(c)]] for c in bucket_chunks]
                
                # Use MMR for intra-bucket diversity with precomputed embeddings
                selected = pinecone_handler.mmr_select_from_chunks(
                    chunks=bucket_chunks,
                    query_text=query,
                    k=count,
                    lambda_mult=0.5,
                    chunk_embeddings=bucket_embs,
                    query_embedding=query_embedding
                )
                final_selected_chunks.extend(selected)
            
            # ================================
            # 4️⃣ Late Enrichment (SQL Store)
            # ================================
            # Now we enrich ONLY the final chunks (reduces SQL calls from n*10 to n*7)
            logger.info(f"💾 [BUCKET_RETRIEVE] Enriching {len(final_selected_chunks)} final chunks from SQL Content Store...")
            
            final_content = []
            for chunk in final_selected_chunks:
                meta = chunk.get("metadata", {})
                chunk_id = meta.get("chunk_id")
                filename = meta.get("filename")
                
                if chunk_id and filename and pinecone_handler.content_store:
                    full_content = pinecone_handler.content_store.get_chunk(chunk_id, filename)
                    if full_content:
                        chunk["content"] = full_content
                
                final_content.append(chunk)

            logger.info(f"   ✅ Final content selection: {len(final_content)} enriched chunks")
        
        # ================================
        # 5️⃣ PYQ Style Fetch (Exactly 10)
        # ================================
        logger.info("📝 Fetching 10 PYQ chunks for style learning...")
        try:
            pyq_chunks = pinecone_handler.query_documents(
                query_text=query,
                k=10,
                filter_metadata={"source_type": "pyq"},
                use_content_store=True
            )
            logger.info(f"   ✅ Retrieved {len(pyq_chunks)} PYQ chunks")
        except Exception as e:
            logger.warning(f"⚠️ PYQ retrieval failed: {e}")
            pyq_chunks = []
            
    except Exception as e:
        logger.error(f"❌ Content retrieval failed: {e}")
        final_content = []
        pyq_chunks = []

    return pyq_chunks, final_content

@router.get("/domains")
async def get_geography_domains():
    """Get the geography domain structure for dropdowns"""
    return {"domains": GEOGRAPHY_DOMAINS}

@router.post("/generate", response_model=MockTestResponse)
async def generate_mock_test(request: Request, test_request: MockTestRequest):
    """Generate a UPSC-style mock test using hybrid retrieval with progressive fallback and source diversity"""
    try:
        logger.info(f"🚀 [MOCK_TEST] Received request: {test_request.num_questions} questions, topics={test_request.topics}")
        
        pinecone_handler = request.app.state.vector_handler
        
        # Extract major_domain and sub_domain from topics (from dropdowns)
        major_domain, sub_domain = extract_domains_from_topics(test_request.topics)
        logger.info(f"📌 Using domains for retrieval: major_domain={major_domain}, sub_domain={sub_domain}")
        
        # Use hybrid retrieval pipeline with all enhancements
        pyq_chunks, content_chunks = hybrid_retrieve_for_mock_test(
            pinecone_handler=pinecone_handler,
            topics=test_request.topics,
            num_questions=test_request.num_questions,
            subject=test_request.subject
        )
        
        # Fallback: if no PYQ chunks found, use all chunks but warn
        if not pyq_chunks:
            logger.warning("⚠️ No PYQ chunks found. Questions may lack UPSC style patterns.")
            # Use content chunks for both if no PYQs available
            if content_chunks:
                pyq_chunks = content_chunks[:3]  # Use a few content chunks as fallback
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No relevant content found in uploaded materials. Please upload study materials first."
                )
        
        if not content_chunks:
            raise HTTPException(
                status_code=400,
                detail="No relevant content chunks found. Please ensure you have uploaded NCERT/Vision notes."
            )

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Gemini API key not configured. Mock test generation requires Gemini for quality questions."
            )

        return await generate_question_paper(pyq_chunks, content_chunks, test_request, api_key, app_state=request.app.state)
    except Exception as e:
        logger.error(f"❌ Mock test generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def map_topics_to_domains(topics: List[str]) -> Dict[str, List[str]]:
    """
    Map user-selected topics to major_domain and sub_domain values.
    
    Returns:
        Dict with 'major_domains' and 'sub_domains' lists
    """
    major_domains = []
    sub_domains = []
    
    topics_lower = [t.lower() for t in topics]
    
    # Map topics to domains
    for domain, subtopics in GEOGRAPHY_TOPICS.items():
        for sub in subtopics:
            sub_lower = sub.lower()
            # Check if any user topic matches this sub_domain
            if any(topic in sub_lower or sub_lower in topic for topic in topics_lower):
                if domain not in major_domains:
                    major_domains.append(domain)
                if sub not in sub_domains:
                    sub_domains.append(sub)
    
    # Also check direct domain matches
    domain_names = [d.lower() for d in GEOGRAPHY_TOPICS.keys()]
    for topic in topics_lower:
        for domain in GEOGRAPHY_TOPICS.keys():
            if topic in domain.lower() or domain.lower() in topic:
                if domain not in major_domains:
                    major_domains.append(domain)
    
    return {
        "major_domains": major_domains,
        "sub_domains": sub_domains
    }


def is_actual_question_chunk(chunk: Dict[str, Any]) -> bool:
    """Check if a chunk contains an actual question (not just index/contents)"""
    content = chunk.get("content", "").lower()
    
    # Skip if it's too short or looks like index/contents
    if len(content) < 100:
        return False
    
    # Skip index/contents pages
    index_indicators = [
        "table of contents",
        "contents",
        "geomorphology",
        "oceanography",
        "climatology",
        "page",
        "chapter",
        "section"
    ]
    
    # If it starts with index-like content, skip
    content_start = content[:200]
    if any(indicator in content_start for indicator in ["1.", "2.", "3.", "4.", "5."]) and \
       any(ind in content_start for ind in index_indicators):
        return False
    
    # Must contain question-like patterns
    question_indicators = [
        "?",
        "which of the following",
        "consider the following",
        "select",
        "choose",
        "(a)", "(b)", "(c)", "(d)",
        "only",
        "none of the above"
    ]
    
    # Must have at least 2 question indicators
    matches = sum(1 for indicator in question_indicators if indicator in content)
    return matches >= 2



# ============================================================================
# PHASE 1: MICRO-BATCH GENERATION FUNCTIONS
# ============================================================================


async def generate_single_batch(
    batch_num: int,
    chunks: List[Dict],
    num_questions: int,
    topics: List[str],
    api_key: str,
    job_id: str,
    pyq_chunks: List[Dict] = None
) -> Tuple[List[Dict], int, int]:
    """
    Generate a single batch of questions with validation and provenance tracking

    Returns:
        Tuple of (valid_questions, prompt_tokens, completion_tokens)
    """
    batch_id = f"{job_id}_batch_{batch_num}"
    logger.info(f"🔨 Generating batch {batch_num}: {num_questions} questions")

    try:
        # Prepare content from chunks
        content_text = "\n\n".join([chunk['content'] for chunk in chunks])

        # Prepare prompt
        topic = topics[0] if topics else "Geography"
        user_prompt = assemble_upsc_prompt(
            topic=topic,
            num_questions=num_questions,
            retrieved_static_text=content_text,
            retrieved_current_affairs="",
            pyq_chunks=pyq_chunks
        )

        # Use GeminiClient for generation with structured output
        if not GEMINI_API_KEY:
            logger.error("❌ Gemini API key not found")
            return [], 0, 0
            
        gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
        
        try:
            # We need a system prompt
            from ..utils.mock_test_prompting import SYSTEM_PROMPT
            
            # Passed Pydantic model is automatically cleaned by GeminiClient
            response_text = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT,
                response_schema=GeneratedQuestions,
                temperature=0.0
            )
            
            # Simple token estimation for Gemini (Simplified)
            prompt_tokens = len(user_prompt) // 4
            completion_tokens = len(response_text) // 4
            
        except Exception as e:
            logger.error(f"❌ Gemini generation failed for batch {batch_num}: {e}")
            return [], 0, 0

        # Parse JSON response
        import json
        try:
            # Structured generation ensures valid JSON without markdown wrapping
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
        except json.JSONDecodeError as e:
            logger.error(f"❌ Batch {batch_num}: JSON parse error: {e}")
            # Fallback sanitization in case of emergency
            sanitized_text = sanitize_json_response(response_text)
            try:
                response_data = json.loads(sanitized_text)
                questions_data = response_data.get("questions", [])
            except:
                questions_data = []

        # Validate batch
        valid_questions, errors = validate_batch(questions_data)

        if errors:
            logger.warning(f"⚠️ Batch {batch_num}: {len(errors)} validation errors")

        # Store in question bank with provenance
        question_bank = get_question_bank()
        for i, q in enumerate(valid_questions):
            # Calculate quality score
            quality_score = calculate_quality_score(q)

            # Create provenance record
            provenance = QuestionProvenance(
                question_id=f"{batch_id}_q{i+1}",
                question_text=q.get("question", ""),
                options=q.get("options", []),
                correct_answer=q.get("correct_answer", "A"),
                explanation=q.get("explanation", ""),
                generated_at=datetime.now().isoformat(),
                model_used="gemini-2.5-pro",
                prompt_tokens=prompt_tokens // max(len(valid_questions), 1),  # Approximate
                completion_tokens=completion_tokens // max(len(valid_questions), 1),
                total_cost=0.0,
                source_chunks=[{"content": c["content"][:200]} for c in chunks[:3]],
                source_domains=list(set(c.get("metadata", {}).get("major_domain", "General") for c in chunks)),
                pyq_examples_used=[],
                validation_passed=True,
                quality_score=quality_score,
                batch_id=batch_id,
                job_id=job_id,
                topics_requested=topics
            )

            question_bank.store_question(provenance)

        logger.info(f"✅ Batch {batch_num}: Generated {len(valid_questions)} valid questions")
        return valid_questions, prompt_tokens, completion_tokens

    except Exception as e:
        logger.error(f"❌ Batch {batch_num} failed: {e}")
        return [], 0, 0


async def generate_micro_batches(
    all_chunks: List[Dict],
    num_questions: int,
    topics: List[str],
    api_key: str,
    job_id: str,
    job_store,
    pyq_chunks: List[Dict] = None
) -> List[Dict]:
    """
    Generate questions in micro-batches with parallel execution

    Returns:
        List of all generated questions (before deduplication)
    """
    # Calculate batches with 10% buffer
    buffer_factor = 1.1
    target_questions = int(num_questions * buffer_factor)
    questions_per_batch = 10
    num_batches = math.ceil(target_questions / questions_per_batch)

    logger.info(f"📦 Micro-batch plan: {num_batches} batches × {questions_per_batch} questions = {target_questions} total (target: {num_questions})")

    # Partition chunks by domain for diversity
    domain_chunks = defaultdict(list)
    for chunk in all_chunks:
        domain = chunk.get("metadata", {}).get("major_domain", "General")
        domain_chunks[domain].append(chunk)

    logger.info(f"   📊 Content distribution: {dict((d, len(c)) for d, c in domain_chunks.items())}")

    # Distribute chunks across batches (round-robin for diversity)
    batch_chunks = [[] for _ in range(num_batches)]
    chunk_index = 0
    for domain, chunks in domain_chunks.items():
        for chunk in chunks:
            batch_chunks[chunk_index % num_batches].append(chunk)
            chunk_index += 1

    # Update job with total batches
    job = job_store.get_job(job_id)
    if job:
        job.total_batches = num_batches

    # Generate batches in parallel with semaphore (limit concurrency)
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent API calls
    all_questions = []

    async def generate_with_semaphore(batch_num, chunks):
        async with semaphore:
            questions, pt, ct = await generate_single_batch(
                batch_num=batch_num,
                chunks=chunks,
                num_questions=questions_per_batch,
                topics=topics,
                api_key=api_key,
                job_id=job_id,
                pyq_chunks=pyq_chunks
            )

            # Update job progress
            job = job_store.get_job(job_id)
            if job:
                job.update_progress(
                    batches_completed=batch_num,
                    questions_generated=len(all_questions) + len(questions)
                )
                job_store.update_job(
                    job_id,
                    batches_completed=job.batches_completed,
                    questions_generated=job.questions_generated,
                    progress=job.progress
                )

            return questions

    # Run all batches
    tasks = [
        generate_with_semaphore(i+1, batch_chunks[i])
        for i in range(num_batches)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"❌ Batch failed: {result}")
        elif isinstance(result, list):
            all_questions.extend(result)

    logger.info(f"📦 All batches complete: {len(all_questions)} questions generated")
    return all_questions


async def fill_gaps_targeted(
    current_questions: List[Dict],
    target: int,
    topics: List[str],
    api_key: str,
    job_id: str,
    pinecone_handler,
    pyq_chunks: List[Dict] = None
) -> List[Dict]:
    """
    Targeted gap-fill generation for missing questions
    """
    gap = target - len(current_questions)
    if gap <= 0:
        return []

    logger.info(f"🔧 Gap-fill needed: {gap} questions short of {target}")

    # Analyze domain distribution
    current_distribution = defaultdict(int)
    for q in current_questions:
        domain = q.get("source", {}).get("domain", "General")
        current_distribution[domain] += 1

    logger.info(f"   📊 Current distribution: {dict(current_distribution)}")

    # Identify underrepresented domain
    if current_distribution:
        min_domain = min(current_distribution, key=current_distribution.get)
        logger.info(f"   🎯 Targeting underrepresented domain: {min_domain}")

        # Retrieve chunks for this domain
        query = build_query_text(min_domain, None)
        gap_chunks = pinecone_handler.query_documents(
            query_text=query,
            k=max(5, gap // 2),
            filter_metadata={"major_domain": min_domain}
        )
    else:
        # No distribution info, use general retrieval
        gap_chunks = pinecone_handler.query_documents(
            query_text=build_query_text(None, None),
            k=max(5, gap // 2)
        )

    gap_questions, _, _ = await generate_single_batch(
        batch_num=999,  # Special batch number for gap-fill
        chunks=gap_chunks,
        num_questions=gap,
        topics=topics,
        api_key=api_key,
        job_id=job_id,
        pyq_chunks=pyq_chunks
    )

    logger.info(f"   ✅ Generated {len(gap_questions)} gap-fill questions")
    return gap_questions




async def _run_pipeline_with_error_handling(
    job_id: str,
    num_questions: int,
    topics: List[str],
    pinecone_handler,
    embedder,
    api_key: str
):
    """
    Wrapper for generate_async_pipeline that catches and logs ALL exceptions
    """
    job_store = get_job_store()

    try:
        logger.info(f"🎬 [JOB {job_id[:8]}] Background task started")

        await generate_async_pipeline(
            job_id=job_id,
            num_questions=num_questions,
            topics=topics,
            pinecone_handler=pinecone_handler,
            embedder=embedder,
            api_key=api_key
        )

        logger.info(f"🎬 [JOB {job_id[:8]}] Background task completed successfully")

    except Exception as e:
        logger.error(f"💥 [JOB {job_id[:8]}] FATAL ERROR in background task: {type(e).__name__}: {str(e)}", exc_info=True)

        # Mark job as failed in database
        try:
            job = job_store.get_job(job_id)
            if job:
                job.mark_failed(f"{type(e).__name__}: {str(e)}")
                job_store.update_job(
                    job_id,
                    status=job.status,
                    error=job.error,
                    completed_at=job.completed_at
                )
                logger.info(f"📝 [JOB {job_id[:8]}] Marked job as failed in database")
        except Exception as update_error:
            logger.error(f"💥 Failed to update job status: {update_error}")


async def generate_async_pipeline(
    job_id: str,
    num_questions: int,
    topics: List[str],
    pinecone_handler,
    embedder,
    api_key: str
):
    """
    Full async generation pipeline for large tests
    """
    job_store = get_job_store()
    job = job_store.get_job(job_id)

    if not job:
        logger.error(f"❌ Job {job_id} not found")
        return

    try:
        logger.info(f"🚀 [JOB {job_id[:8]}] Starting async pipeline")

        # Mark as started
        logger.info(f"📝 [JOB {job_id[:8]}] Calling job.mark_started()...")
        job.mark_started()
        logger.info(f"📝 [JOB {job_id[:8]}] Calling job_store.update_job()...")
        job_store.update_job(job_id, status=job.status, started_at=job.started_at, progress=job.progress)
        logger.info(f"✅ [JOB {job_id[:8]}] Marked as started in database")

        # Step 1: Retrieve chunks (scaled)
        logger.info(f"📚 [JOB {job_id[:8]}] Step 1: Retrieving content chunks")
        try:
            pyq_chunks, content_chunks = hybrid_retrieve_for_mock_test(
                pinecone_handler=pinecone_handler,
                topics=topics,
                num_questions=num_questions
            )
            logger.info(f"✅ [JOB {job_id[:8]}] Retrieved {len(content_chunks)} content chunks, {len(pyq_chunks)} PYQ chunks")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id[:8]}] Retrieval failed: {e}", exc_info=True)
            raise

        all_chunks = content_chunks  # Use content chunks for generation

        if len(all_chunks) < 10:
            raise Exception(f"Insufficient content: only {len(all_chunks)} chunks retrieved")

        # Step 2: Generate micro-batches
        logger.info(f"🔨 [JOB {job_id[:8]}] Step 2: Generating micro-batches")
        try:
            all_questions = await generate_micro_batches(
                all_chunks=all_chunks,
                num_questions=num_questions,
                topics=topics,
                api_key=api_key,
                job_id=job_id,
                job_store=job_store,
                pyq_chunks=pyq_chunks
            )
            logger.info(f"✅ [JOB {job_id[:8]}] Generated {len(all_questions)} total questions")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id[:8]}] Batch generation failed: {e}", exc_info=True)
            raise

        # Step 3: Semantic deduplication
        logger.info(f"🔍 [JOB {job_id[:8]}] Step 3: Semantic deduplication")
        try:
            unique_questions = await semantic_deduplicate(
                questions=all_questions,
                embedder=embedder,
                threshold=0.88
            )
            logger.info(f"✅ [JOB {job_id[:8]}] After deduplication: {len(unique_questions)} unique questions")
        except Exception as e:
            logger.error(f"💥 [JOB {job_id[:8]}] Deduplication failed: {e}", exc_info=True)
            raise

        # Step 4: Gap-fill if needed
        if len(unique_questions) < num_questions:
            logger.info(f"🔧 [JOB {job_id[:8]}] Step 4: Gap-filling ({len(unique_questions)}/{num_questions})")
            try:
                gap_fill = await fill_gaps_targeted(
                    current_questions=unique_questions,
                    target=num_questions,
                    topics=topics,
                    api_key=api_key,
                    job_id=job_id,
                    pinecone_handler=pinecone_handler,
                    pyq_chunks=pyq_chunks
                )
                unique_questions.extend(gap_fill)
                logger.info(f"✅ [JOB {job_id[:8]}] After gap-fill: {len(unique_questions)} questions")
            except Exception as e:
                logger.error(f"💥 [JOB {job_id[:8]}] Gap-fill failed: {e}", exc_info=True)
                raise

        # Step 5: Final selection and shuffle
        logger.info(f"🎲 [JOB {job_id[:8]}] Step 5: Final selection and shuffle")
        if len(unique_questions) > num_questions:
            # Simple random selection (Phase 2 will add sophisticated reranking)
            unique_questions = random.sample(unique_questions, num_questions)

        random.shuffle(unique_questions)

        # Convert to MockTestQuestion format
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
                    "topics": topics
                }
            })

        # Mark job as completed
        logger.info(f"💾 [JOB {job_id[:8]}] Marking job as completed")
        job.mark_completed(final_questions)
        job_store.update_job(
            job_id,
            status=job.status,
            progress=job.progress,
            questions=job.questions,
            completed_at=job.completed_at
        )
        logger.info(f"✅ [JOB {job_id[:8]}] Job completed: {len(final_questions)} questions")

    except Exception as e:
        logger.error(f"❌ [JOB {job_id[:8]}] Pipeline failed: {type(e).__name__}: {str(e)}", exc_info=True)
        job.mark_failed(str(e))
        job_store.update_job(job_id, status=job.status, error=job.error, completed_at=job.completed_at)
        raise



# ============================================================================
# NEW API ENDPOINTS
# ============================================================================

@router.post("/generate-async")
async def generate_async(
    request: Request,
    test_request: MockTestRequest
):
    """
    Start async mock test generation (for large tests)
    Returns job_id immediately, user polls /status/{job_id}
    """
    import redis.asyncio as redis_async

    try:
        # Validate request
        if test_request.num_questions > 200:
            raise HTTPException(400, "Maximum 200 questions allowed")

        # Create job ID
        job_id = str(uuid4())

        # Get Arq pool
        arq_pool = request.app.state.arq_pool
        if not arq_pool:
            raise HTTPException(500, "Job queue not initialized")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(400, "Gemini API key not configured")

        # Set initial status in Redis
        try:
            client = get_redis_client()
            await client.set(f"job_status:{job_id}", "queued", ex=3600)
            await client.set(f"job_num_questions:{job_id}", str(test_request.num_questions), ex=3600)
            await client.set(f"job_topics:{job_id}", ",".join(test_request.topics), ex=3600)
            await client.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to set initial Redis status: {e}")

        # Enqueue job via Arq
        await arq_pool.enqueue_job(
            "generate_mock_test_task",
            job_id=job_id,
            num_questions=test_request.num_questions,
            topics=test_request.topics,
            api_key=api_key
        )

        # Log task creation
        logger.info(f"🎬 Enqueued job {job_id[:8]} to Arq worker")

        # Estimate time
        estimated_seconds = math.ceil(test_request.num_questions / 40) * 60  # ~60s per 40 questions

        logger.info(f"📋 Created async job {job_id} for {test_request.num_questions} questions")

        return {
            "job_id": job_id,
            "status": "queued",
            "estimated_time_seconds": estimated_seconds,
            "message": f"Generating {test_request.num_questions} questions. Poll /mock-test/status/{job_id} for progress."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to start async generation: {e}")
        raise HTTPException(500, str(e))


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Get status of async mock test generation (Redis-based)
    """
    import redis.asyncio as redis_async
    import json

    try:
        client = get_redis_client()

        status = await client.get(f"job_status:{job_id}")
        if not status:
            await client.close()
            raise HTTPException(404, f"Job {job_id} not found")

        # Build response
        response = {
            "job_id": job_id,
            "status": status
        }

        # Get metadata
        num_questions = await client.get(f"job_num_questions:{job_id}")

        # Semantic logging for polling
        logger.info(f"MOCK_TEST_STATUS - {job_id[:8]}... : {status.upper()}")

        topics = await client.get(f"job_topics:{job_id}")
        
        if num_questions:
            response["num_questions"] = int(num_questions)
        if topics:
            response["topics"] = topics.split(",") if topics else []

        # Get result if completed
        if status == "completed":
            result_json = await client.get(f"job_result:{job_id}")
            if result_json:
                response["result"] = json.loads(result_json)

        # Get error if failed
        if status == "failed":
            error = await client.get(f"job_error:{job_id}")
            if error:
                response["error"] = error

        await client.close()
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/cancel/{job_id}")
async def cancel_mock_test(job_id: str):
    """
    Cancel a running mock test generation job.
    """
    import redis.asyncio as redis_async

    try:
        client = get_redis_client()
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        return {"message": "Cancellation requested"}
    except Exception as e:
        raise HTTPException(500, str(e))
