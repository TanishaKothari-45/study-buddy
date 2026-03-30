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
import uuid
from datetime import datetime
import asyncio
import math
from uuid import uuid4
from datetime import datetime
from collections import defaultdict
# from openai import OpenAI, RateLimitError  # No longer used for generation
import numpy as np

from ..core.config import settings
from ..core.deps import get_redis_client
from ..utils.metadata_enricher import GEOGRAPHY_TOPICS, GEOGRAPHY_DOMAINS, SUBJECT_DOMAINS
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
from ..utils.batch_validator import (
    validate_batch,
    calculate_quality_score,
    partition_all_batches,
    subdomain_entropy_score,
)

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

def format_mock_test_response(questions_data: List[Dict], job_id: str, topics: List[str]) -> MockTestResponse:
    """Helper to convert list of question dicts into a formatted MockTestResponse."""
    questions = []
    for i, q_data in enumerate(questions_data):
        if isinstance(q_data, dict):
            # Handle options - convert dict to list if needed
            options_raw = q_data.get("options", [])
            if isinstance(options_raw, dict):
                options_list = [options_raw.get(key, "") for key in ["A", "B", "C", "D"]]
                options_list = [opt for opt in options_list if opt]
            elif isinstance(options_raw, list):
                options_list = options_raw
            else:
                options_list = ["A", "B", "C", "D"]
            
            question_text = q_data.get("question", f"Question {i+1}")
            
            # Map source data
            src = q_data.get("source", {})
            if isinstance(src, str): src = {} # Fallback
            
            question = MockTestQuestion(
                question=question_text,
                options=options_list,
                correct_answer=q_data.get("correct_answer", "A"),
                explanation=q_data.get("explanation", "No explanation provided"),
                source=QuestionSource(
                    topic=src.get("topic", topics[0] if topics else "General"),
                    sub_domain=src.get("sub_domain", "General")
                )
            )
            questions.append(question)
            
            # Memory Update - Store question in recency DB
            try:
                topic = topics[0] if topics else "Geography"
                subtopic = topics[1] if len(topics) > 1 else topic
                record_recent_question(
                    question_text=question_text,
                    topic=topic,
                    subtopic=subtopic
                )
            except Exception as e:
                logger.debug(f"⚠️ Memory update skipped: {e}")

    # Fallback
    if not questions:
        questions = [MockTestQuestion(
            question="What is the primary focus of Geography as a discipline?",
            options=["Physical features", "Human-environment interactions", "Maps", "Weather"],
            correct_answer="B",
            explanation="Geography is the study of human-environment interactions.",
            source=QuestionSource(topic="General", sub_domain="General")
        )]
    
    # Calculate time/marks
    total_marks = len(questions) * 2
    total_minutes = len(questions) * 1.2
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)
    time_allowed = f"{hours}h {minutes}m" if hours > 0 else f"{int(minutes)} minutes"
    
    instructions = [
        "Attempt all questions.",
        f"Each question carries 2 marks.",
        f"Total marks: {total_marks}.",
        "Negative marking: -0.67 marks (1/3) for each wrong answer.",
        "Questions are based on your uploaded study materials."
    ]
    
    return MockTestResponse(
        questions=questions,
        total_marks=total_marks,
        time_allowed=time_allowed,
        instructions=instructions
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
    
    Checks against ALL supported subjects (Geography, History, etc.) in SUBJECT_DOMAINS.
    Returns the first matching major_domain and sub_domain found.
    
    Args:
        topics: List of topics (can be sub-domains or major domains)
    
    Returns:
        Tuple of (major_domain, sub_domain) or (None, None) if not found
    """
    if not topics:
        return None, None
    
    major_domain = None
    sub_domain = None
    
    topics_lower = [t.lower() for t in topics]
    
    # Iterate over all subjects (Geography, History)
    for subject, domains_dict in SUBJECT_DOMAINS.items():
        
        # 1. Check direct major domain match
        for domain in domains_dict.keys():
            if domain.lower() in topics_lower or any(domain.lower() == t for t in topics_lower):
                major_domain = domain
                logger.info(f"📌 Found Major Domain match: {major_domain} (Subject: {subject})")
                break
        
        if major_domain: break

    # If no major domain found, or to find sub-domain, check sub-domains across all subjects
    for subject, domains_dict in SUBJECT_DOMAINS.items():
        for domain, subdomains in domains_dict.items():
            for sub in subdomains:
                if sub.lower() in topics_lower or any(sub.lower() == t for t in topics_lower):
                    sub_domain = sub
                    # If we found a sub-domain, its parent is the major domain
                    if not major_domain:
                        major_domain = domain
                        logger.info(f"📌 Found Major Domain {major_domain} via Sub-domain {sub_domain} (Subject: {subject})")
                    break
            if sub_domain: break
        if sub_domain: break
            
    # If we found a sub-domain but no major domain (unlikely with above logic, but safety net)
    if sub_domain and not major_domain:
        for subject, domains_dict in SUBJECT_DOMAINS.items():
            for domain, subdomains in domains_dict.items():
                if sub_domain in subdomains:
                    major_domain = domain
                    break
            if major_domain: break
    
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
    
    # 🎯 [OPTIMIZATION] Skip Pinecone retrieval ONLY for subjects without vector data
    # Economy, Polity, Environment have been/are being indexed.
    skip_subjects = ["science & technology", "science & tech", "science"]
    if any(s in subject.lower() for s in skip_subjects):
        logger.info(f"⏩ [BUCKET_RETRIEVE] Skipping Pinecone retrieval for '{subject}' (No vector data yet). Bypassing to search-only grounding.")
        return [], []
        
    # 🎯 Optimize: Compute embedding once for reuse
    # This saves 3-4 OpenAI API calls per generation
    logger.info("⚡ Generating query embedding once for reuse...")
    query_vector = pinecone_handler.langchain_embeddings.embed_query(query)
    
    # ================================
    # 1️⃣ Raw Content Fetch (n * 10)
    # ================================
    target_fetch = num_questions * 10
    logger.info(f"📘 Fetching {target_fetch} content chunks (excluding PYQs)...")
    
    try:
        # metadata filter: source_type IN ['concept', 'current_affairs']
        content_filter = {"source_type": {"$in": ["concept", "current_affairs"]}}
        
        if sub_domain:
            content_filter["sub_domain"] = sub_domain
        elif major_domain:
            content_filter["major_domain"] = major_domain
            
        # New: Add subject filter if specific subject is requested
        if subject and subject.lower() != "general":
            content_filter["subject"] = subject

        raw_chunks = []
        
        # New: If no domain/sub_domain selected, fetch across all major domains for diversity
        if not major_domain:
            from ..utils.metadata_enricher import GEOGRAPHY_DOMAINS
            logger.info("🌍 [BUCKET_RETRIEVE] No topic selected. Fetching cross-domain for diversity...")
            all_major_domains = list(GEOGRAPHY_DOMAINS.keys())
            
            chunks_per_domain = math.ceil(target_fetch / len(all_major_domains))
            
            for domain in all_major_domains:
                domain_filter = content_filter.copy()
                domain_filter["major_domain"] = domain
                # Reuse query vector (saves calls)
                
                logger.debug(f"   🔍 Fetching diversity chunks for domain: {domain}")
                domain_chunks = pinecone_handler.query_documents(
                    query_text=query,
                    k=chunks_per_domain,
                    filter_metadata=domain_filter,
                    use_content_store=False,
                    query_vector=query_vector # Reuse vector
                )
                raw_chunks.extend(domain_chunks)
            
            logger.info(f"   ✅ Retrieved {len(raw_chunks)} raw content chunks across {len(all_major_domains)} domains")
        else:
            # Standard fetch with metadata filter
            raw_chunks = pinecone_handler.query_documents(
                query_text=query,
                k=target_fetch,
                filter_metadata=content_filter,
                use_content_store=False,
                query_vector=query_vector # Reuse vector
            )
            logger.info(f"   ✅ Retrieved {len(raw_chunks)} raw content chunks (using metadata filter)")
        
        if not raw_chunks:
            logger.warning("⚠️ No chunks found with specific filters, falling back to general query...")
            fallback_filter = {"source_type": {"$in": ["concept", "current_affairs"]}}
            if subject and subject.lower() != "general":
                fallback_filter["subject"] = subject
                
            raw_chunks = pinecone_handler.query_documents(
                query_text=query,
                k=target_fetch,
                filter_metadata=fallback_filter,
                use_content_store=False,
                query_vector=query_vector # Reuse vector
            )
        
        # ================================
        # 2️⃣ Adaptive Metadata Bucketing
        # ================================
        # Initial bucket attempt
        buckets = bucket_chunks_by_metadata(raw_chunks, major_domain, sub_domain)
        
        # 🛡️ Adaptive Granularity: If only 1 bucket formed, force finer granularity
        if len(buckets) < 2 and raw_chunks:
            logger.info(f"⚠️ Only {len(buckets)} bucket formed. Forcing finer granularity (Level 3 - Micro Topic)...")
            # Force bucket by section/micro-topic regardless of current level
            buckets = defaultdict(list)
            for chunk in raw_chunks:
                meta = chunk.get("metadata", {})
                bucket_key = meta.get("section") or meta.get("chapter") or meta.get("micro_topic") or "General"
                buckets[bucket_key].append(chunk)
                
        bucket_stats = {k: len(v) for k, v in buckets.items()}
        logger.info(f"   📊 Final Buckets ({len(buckets)}): {bucket_stats}")
        
        # Pre-embed query and all chunks once to minimize Embedding calls
        logger.info(f"   📝 Pre-embedding {len(raw_chunks)} chunks for efficient MMR...")
        # Query embedding already done as query_vector
        query_embedding = np.array(query_vector)
        
        all_chunk_texts = [c.get("content", "") for c in raw_chunks]
        all_chunk_embeddings = [np.array(emb) for emb in pinecone_handler.langchain_embeddings.embed_documents(all_chunk_texts)]
        
        # Create a mapping from chunk content to embedding for quick lookup
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
                    else:
                        # User strictly wants FULL TEXT ONLY. Clear metadata fallback.
                        chunk["content"] = ""
                else:
                    chunk["content"] = ""
                
                final_content.append(chunk)

            logger.info(f"   ✅ Final content selection: {len(final_content)} enriched chunks")
        else:
            final_content = []
        
        # ================================
        # 5️⃣ PYQ Style Fetch (Exactly 10)
        # ================================
        logger.info("📝 Fetching 10 PYQ chunks with prioritized topic matching...")
        try:
            pyq_chunks_raw = []
            
            # Step A: Try most specific filter (sub_domain)
            if sub_domain:
                logger.debug(f"   🔍 Level 1: Fetching PYQs for sub_domain: {sub_domain}")
                pyq_filter = {"source_type": "pyq", "sub_domain": sub_domain}
                if subject and subject.lower() != "general":
                    pyq_filter["subject"] = subject
                    
                res = pinecone_handler.query_documents(
                    query_text=query,
                    k=10,
                    filter_metadata=pyq_filter,
                    use_content_store=False,
                    query_vector=query_vector # Reuse vector
                )
                pyq_chunks_raw.extend(res)
                
            # Step B: If still need more, try major_domain
            if len(pyq_chunks_raw) < 10 and major_domain:
                needed = 10 - len(pyq_chunks_raw)
                logger.debug(f"   🔍 Level 2: Fetching {needed} more PYQs for major_domain: {major_domain}")
                existing_ids = [p.get("metadata", {}).get("chunk_id") for p in pyq_chunks_raw]
                
                # Fetch more with major_domain filter
                pyq_filter_major = {"source_type": "pyq", "major_domain": major_domain}
                if subject and subject.lower() != "general":
                    pyq_filter_major["subject"] = subject
                    
                res = pinecone_handler.query_documents(
                    query_text=query,
                    k=needed,
                    filter_metadata=pyq_filter_major,
                    use_content_store=False,
                    query_vector=query_vector # Reuse vector
                )
                
                # De-duplicate manually (Pinecone filter doesn't support NOT IN easily in this handler)
                for p in res:
                    if p.get("metadata", {}).get("chunk_id") not in existing_ids:
                        pyq_chunks_raw.append(p)
                        if len(pyq_chunks_raw) >= 10: break
            
            # Step C: Fallback to general PYQs if still less than 10
            if len(pyq_chunks_raw) < 10:
                needed = 10 - len(pyq_chunks_raw)
                logger.debug(f"   🔍 Level 3: Fetching {needed} general PYQs")
                existing_ids = [p.get("metadata", {}).get("chunk_id") for p in pyq_chunks_raw]
                
                pyq_filter_general = {"source_type": "pyq"}
                if subject and subject.lower() != "general":
                    pyq_filter_general["subject"] = subject
                    
                res = pinecone_handler.query_documents(
                    query_text=query,
                    k=needed,
                    filter_metadata=pyq_filter_general,
                    use_content_store=False,
                    query_vector=query_vector # Reuse vector
                )
                
                for p in res:
                    if p.get("metadata", {}).get("chunk_id") not in existing_ids:
                        pyq_chunks_raw.append(p)
                        if len(pyq_chunks_raw) >= 10: break
            
            # Enrich PYQs from SQL Content Store to get domain metadata
            pyq_chunks = []
            for pyq in pyq_chunks_raw:
                meta = pyq.get("metadata", {})
                chunk_id = meta.get("chunk_id")
                filename = meta.get("filename")
                
                if chunk_id and filename and pinecone_handler.content_store:
                    # Use get_enriched_chunk to get classification + content
                    enriched = pinecone_handler.content_store.get_enriched_chunk(chunk_id, filename)
                    if enriched:
                        pyq["content"] = enriched.get("full_content", "") # Strict full text
                        # Only keep major_domain and sub_domain to save tokens
                        pyq["metadata"]["major_domain"] = enriched.get("major_domain")
                        pyq["metadata"]["sub_domain"] = enriched.get("sub_domain")
                    else:
                        pyq["content"] = "" # No enrichment = no content
                else:
                    pyq["content"] = ""
                pyq_chunks.append(pyq)
                
            logger.info(f"   ✅ Retrieved and enriched {len(pyq_chunks)} PYQ chunks (Topic matched: {len(pyq_chunks_raw)})")
        except Exception as e:
            logger.warning(f"⚠️ PYQ retrieval failed: {e}")
            pyq_chunks = []
            
    except Exception as e:
        logger.error(f"❌ Content retrieval failed: {e}")
        final_content = []
        pyq_chunks = []

    return pyq_chunks, final_content

@router.get("/domains")
async def get_subject_domains(subject: str = "Geography"):
    """Get the domain structure for dropdowns for a specific subject"""
    # Standardize subject name for lookup
    subj_map = {
        "geography": "Geography",
        "history": "History",
        "economy": "Economy",
        "science & tech": "Science & Tech",
        "environment & ecology": "Environment & Ecology",
        "polity": "Polity"
    }
    
    std_subject = subj_map.get(subject.lower(), subject)
    domains = SUBJECT_DOMAINS.get(std_subject, GEOGRAPHY_DOMAINS)
    return {"domains": domains}

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

        # Use generate_single_batch (the unified pipeline with research)
        batch_questions, _, _ = await generate_single_batch(
            batch_num=1,
            chunks=content_chunks,  # Limit chunks for sync speed
            num_questions=test_request.num_questions,
            topics=test_request.topics,
            api_key=api_key,
            job_id=f"sync_{uuid.uuid4().hex[:8]}",
            pyq_chunks=pyq_chunks,
            subject=test_request.subject
        )
        
        return format_mock_test_response(batch_questions, None, test_request.topics)
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

def _detect_subject(cluster: Dict[str, Any]) -> str:
    """
    Return a canonical subject string from cluster metadata.
    Priority: explicit 'subject' key → infer from major_domain.
    """
    subject = cluster.get("subject", "").lower().strip()
    major = cluster.get("major_domain", "").lower().strip()

    if subject:
        for key in ("geography", "history", "economy", "polity", "environment", "science"):
            if key in subject:
                return key

    for key in ("geography", "history", "economy", "polity", "environment", "science"):
        if key in major:
            return key

    geography_signals = ["physical", "human", "indian geography", "world geography",
                         "climatology", "geomorphology", "oceanography", "monsoon",
                         "soil", "drainage", "physiography"]
    history_signals   = ["ancient", "medieval", "modern", "art & culture", "art and culture",
                         "revolt", "nationalist", "colonial"]
    economy_signals   = ["banking", "fiscal", "monetary", "inflation", "gdp", "rbi",
                         "taxation", "budget", "trade", "sector", "macroeconomics",
                         "microeconomics", "external sector", "arthapedia"]
    polity_signals    = ["constitution", "parliament", "judiciary", "fundamental rights",
                         "directive", "governor", "election", "panchayat", "union government",
                         "state government", "federal"]
    env_signals       = ["ecology", "biodiversity", "pollution", "climate change",
                         "conservation", "ecosystem", "wetland", "forest", "ramsar",
                         "unfccc", "paris agreement", "wildlife"]
    sci_signals       = ["space", "isro", "defence", "biotechnology", "ai ", "artificial intel",
                         "nanotechnology", "semiconductor", "quantum", "cybersecurity",
                         "it ", "information tech", "emerging tech"]

    for sig in geography_signals:
        if sig in major:
            return "geography"
    for sig in history_signals:
        if sig in major:
            return "history"
    for sig in economy_signals:
        if sig in major:
            return "economy"
    for sig in polity_signals:
        if sig in major:
            return "polity"
    for sig in env_signals:
        if sig in major:
            return "environment"
    for sig in sci_signals:
        if sig in major:
            return "science"

    return "general"


def _top_subs(sub_topics_list: List[str], n: int = 2) -> str:
    """Return top-n cleaned sub-topics joined as a string."""
    noise = {"general", "introduction", "types", "overview", "basics", "concept", "definition"}
    valid = [s.strip() for s in sub_topics_list
             if isinstance(s, str) and len(s) > 3 and s.lower().strip() not in noise]
    return " ".join(valid[:n])


def _queries_geography(mt: str, subs: str, major: str) -> List[Dict]:
    if "physical" in major:
        return [
            {"q": f"{mt} {subs} India extreme weather anomaly 2024 2025 IMD IPCC official report",
             "recency": 365},
            {"q": f"{mt} {subs} recent scientific study impact climate geomorphology 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} physical geography standard explanation UPSC",
             "recency": 1500},
        ]
    elif "indian" in major:
        return [
            {"q": f"{mt} {subs} India government report ministry 2024 2025 data official",
             "recency": 365},
            {"q": f"{mt} {subs} India infrastructure river dam project news 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in OR site:surveyofindia.gov.in {mt} {subs} Indian geography static facts",
             "recency": 1500},
        ]
    elif "human" in major or "economic geography" in major:
        return [
            {"q": f"{mt} {subs} India population urbanisation migration 2024 2025 census UN report",
             "recency": 365},
            {"q": f"{mt} {subs} India agriculture industry economic geography policy 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} human economic geography fundamentals UPSC",
             "recency": 1500},
        ]
    elif "world" in major:
        return [
            {"q": f"{mt} {subs} world geography international summit treaty 2024 2025 impact",
             "recency": 365},
            {"q": f"{mt} {subs} global report index ranking 2024 2025 official",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} world geography map spatial facts UPSC",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"{mt} {subs} India geography disaster anomaly policy 2024 2025 official",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} geography core concept UPSC",
             "recency": 1500},
        ]


def _queries_history(mt: str, subs: str, major: str) -> List[Dict]:
    if "ancient" in major:
        return [
            {"q": f"{mt} {subs} ASI archaeological excavation discovery news 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} ancient India history civilization facts UPSC",
             "recency": 1500},
        ]
    elif "medieval" in major:
        return [
            {"q": f"{mt} {subs} medieval India heritage conservation UNESCO news 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} medieval India sultanate mughal history facts UPSC",
             "recency": 1500},
        ]
    elif "modern" in major:
        return [
            {"q": f"{mt} {subs} modern India freedom movement anniversary 2024 2025 government commemoration",
             "recency": 365},
            {"q": f"{mt} {subs} British India reform policy analysis 2024 2025 academic",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} modern history India freedom struggle reforms UPSC",
             "recency": 1500},
        ]
    elif "art" in major or "culture" in major:
        return [
            {"q": f"{mt} {subs} UNESCO intangible heritage ASI listing India 2024 2025",
             "recency": 365},
            {"q": f"{mt} {subs} India art culture festival restoration government initiative 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in OR site:indiaculture.gov.in {mt} {subs} art culture architecture India static",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"{mt} {subs} India history heritage news 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} history India UPSC standard",
             "recency": 1500},
        ]


def _queries_economy(mt: str, subs: str, major: str) -> List[Dict]:
    major_l = major.lower()
    if "monetary" in major_l:
        return [
            {"q": f"RBI {mt} {subs} monetary policy committee repo rate decision 2024 2025 official",
             "recency": 365},
            {"q": f"RBI annual report {mt} {subs} inflation CPI WPI data 2024 2025",
             "recency": 365},
            {"q": f"site:arthapedia.in {mt} {subs} monetary policy concept definition",
             "recency": 1500},
        ]
    elif "fiscal" in major_l:
        return [
            {"q": f"Union Budget 2024 2025 {mt} {subs} fiscal deficit FRBM data official",
             "recency": 365},
            {"q": f"Ministry of Finance {mt} {subs} fiscal consolidation expenditure 2024 2025",
             "recency": 365},
            {"q": f"site:arthapedia.in OR site:indiabudget.gov.in {mt} {subs} fiscal policy concept UPSC",
             "recency": 1500},
        ]
    elif "banking" in major_l or "finance" in major_l:
        return [
            {"q": f"RBI {mt} {subs} banking regulation circular notification 2024 2025",
             "recency": 365},
            {"q": f"{mt} {subs} financial inclusion PMJDY microfinance India 2024 2025 report",
             "recency": 365},
            {"q": f"site:arthapedia.in {mt} {subs} banking finance term definition UPSC",
             "recency": 1500},
        ]
    elif "external" in major_l or "trade" in major_l or "bop" in major_l:
        return [
            {"q": f"DGFT WTO India {mt} {subs} trade balance current account 2024 2025 official data",
             "recency": 365},
            {"q": f"India FDI FPI {mt} {subs} external sector DPIIT RBI report 2024 2025",
             "recency": 365},
            {"q": f"site:arthapedia.in {mt} {subs} external sector balance of payments concept UPSC",
             "recency": 1500},
        ]
    elif "taxation" in major_l or "gst" in major_l:
        return [
            {"q": f"GST Council {mt} {subs} rate revision notification 2024 2025 official",
             "recency": 365},
            {"q": f"Income Tax direct tax reform {mt} {subs} India 2024 2025 Finance Act",
             "recency": 365},
            {"q": f"site:cbic.gov.in OR site:incometaxindia.gov.in {mt} {subs} taxation concept UPSC",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"Economic Survey India 2024 2025 {mt} {subs} data findings highlights",
             "recency": 365},
            {"q": f"NITI Aayog {mt} {subs} India development index report 2024 2025",
             "recency": 365},
            {"q": f"site:arthapedia.in OR site:vikaspedia.in {mt} {subs} economy concept India UPSC",
             "recency": 1500},
        ]


def _queries_polity(mt: str, subs: str, major: str) -> List[Dict]:
    major_l = major.lower()
    if "constitutional" in major_l or "fundamental" in major_l or "directive" in major_l:
        return [
            {"q": f"Supreme Court {mt} {subs} constitutional interpretation judgement 2024 2025",
             "recency": 365},
            {"q": f"{mt} {subs} constitutional amendment Parliament India 2024 2025",
             "recency": 365},
            {"q": f"site:legislative.gov.in OR site:prsindia.org {mt} {subs} constitutional provision UPSC",
             "recency": 1500},
        ]
    elif "parliament" in major_l or "union government" in major_l:
        return [
            {"q": f"Lok Sabha Rajya Sabha {mt} {subs} bill passed ordinance 2024 2025 Parliament",
             "recency": 365},
            {"q": f"site:prsindia.org {mt} {subs} parliamentary committee report India 2024 2025",
             "recency": 365},
            {"q": f"site:legislative.gov.in {mt} {subs} Parliament procedure constitutional provisions UPSC",
             "recency": 1500},
        ]
    elif "judiciary" in major_l:
        return [
            {"q": f"Supreme Court High Court {mt} {subs} landmark judgement ruling 2024 2025 India",
             "recency": 365},
            {"q": f"{mt} {subs} judicial review constitutional bench India 2024 2025",
             "recency": 365},
            {"q": f"site:legislative.gov.in {mt} {subs} judiciary powers India constitutional UPSC",
             "recency": 1500},
        ]
    elif "electoral" in major_l or "election" in major_l:
        return [
            {"q": f"Election Commission India {mt} {subs} notification guidelines reform 2024 2025 official",
             "recency": 365},
            {"q": f"{mt} {subs} electoral bond VVPAT EVM reform law India 2024 2025",
             "recency": 365},
            {"q": f"site:eci.gov.in {mt} {subs} election procedure law India UPSC",
             "recency": 1500},
        ]
    elif "panchayat" in major_l or "local" in major_l or "municipal" in major_l:
        return [
            {"q": f"{mt} {subs} panchayati raj local government India devolution fund 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in OR site:gov.in {mt} {subs} 73rd 74th amendment local bodies UPSC",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"Yojana Kurukshetra magazine {mt} {subs} governance analysis 2024 2025 India",
             "recency": 730},
            {"q": f"CAG report {mt} {subs} India governance accountability 2024 2025",
             "recency": 365},
            {"q": f"site:prsindia.org OR site:gov.in {mt} {subs} governance polity UPSC",
             "recency": 1500},
        ]


def _queries_environment(mt: str, subs: str, major: str) -> List[Dict]:
    major_l = major.lower()
    if "biodiversity" in major_l or "conservation" in major_l:
        return [
            {"q": f"IUCN Red List {mt} {subs} species status India 2024 2025 update",
             "recency": 365},
            {"q": f"{mt} {subs} wildlife sanctuary national park India notification 2024 2025 MoEF",
             "recency": 365},
            {"q": f"site:moef.gov.in OR site:wiienvis.nic.in {mt} {subs} biodiversity conservation India UPSC",
             "recency": 1500},
        ]
    elif "climate" in major_l:
        return [
            {"q": f"IPCC UNFCCC COP {mt} {subs} India NDC climate target 2024 2025 official",
             "recency": 365},
            {"q": f"India climate change {mt} {subs} heatwave glacier sea level 2024 2025 data",
             "recency": 365},
            {"q": f"site:moef.gov.in {mt} {subs} climate change India framework UPSC",
             "recency": 1500},
        ]
    elif "pollution" in major_l:
        return [
            {"q": f"CPCB NGT {mt} {subs} India pollution data air water soil 2024 2025 official",
             "recency": 365},
            {"q": f"{mt} {subs} India pollution control regulation notification 2024 2025",
             "recency": 365},
            {"q": f"site:cpcb.nic.in OR site:moef.gov.in {mt} {subs} pollution standards UPSC",
             "recency": 1500},
        ]
    elif "law" in major_l or "legislation" in major_l or "legal" in major_l:
        return [
            {"q": f"MoEF NGT {mt} {subs} India environment law notification amendment 2024 2025",
             "recency": 365},
            {"q": f"{mt} {subs} India environment protection act rules 2024 2025 official",
             "recency": 365},
            {"q": f"site:moef.gov.in {mt} {subs} environmental law India UPSC",
             "recency": 1500},
        ]
    elif "natural resource" in major_l or "forest" in major_l or "water" in major_l:
        return [
            {"q": f"Forest Survey India {mt} {subs} forest cover water body report 2024 2025",
             "recency": 365},
            {"q": f"{mt} {subs} India natural resource management Jal Jeevan Mission 2024 2025",
             "recency": 365},
            {"q": f"site:fsi.nic.in OR site:moef.gov.in {mt} {subs} forest resources India UPSC",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"{mt} {subs} India ecology environment summit treaty news 2024 2025",
             "recency": 365},
            {"q": f"Ramsar Wetland CITES CBD {mt} {subs} India status 2024 2025",
             "recency": 365},
            {"q": f"site:moef.gov.in {mt} {subs} ecology environment concept India UPSC",
             "recency": 1500},
        ]


def _queries_science(mt: str, subs: str, major: str) -> List[Dict]:
    major_l = major.lower()
    if "space" in major_l or "defence" in major_l:
        return [
            {"q": f"ISRO {mt} {subs} mission launch satellite 2024 2025 official update",
             "recency": 365},
            {"q": f"DRDO India {mt} {subs} defence technology acquisition test 2024 2025",
             "recency": 365},
            {"q": f"site:isro.gov.in OR site:drdo.gov.in {mt} {subs} space defence technology India UPSC",
             "recency": 1500},
        ]
    elif "biotech" in major_l or "biotechnology" in major_l:
        return [
            {"q": f"DBT ICMR India {mt} {subs} biotechnology approval regulation 2024 2025",
             "recency": 365},
            {"q": f"India {mt} {subs} GM crop gene therapy clinical trial 2024 2025 approval",
             "recency": 365},
            {"q": f"site:dbtindia.gov.in OR site:icmr.gov.in {mt} {subs} biotechnology India UPSC",
             "recency": 1500},
        ]
    elif "ai" in major_l or "information" in major_l or "emerging" in major_l or "cyber" in major_l:
        return [
            {"q": f"MeitY India {mt} {subs} AI policy digital regulation cyber law 2024 2025 official",
             "recency": 365},
            {"q": f"India {mt} {subs} artificial intelligence data protection IT act 2024 2025",
             "recency": 365},
            {"q": f"site:meity.gov.in {mt} {subs} information technology AI India UPSC concept",
             "recency": 1500},
        ]
    elif "fundamental" in major_l or "physics" in major_l or "chemistry" in major_l or "biology" in major_l:
        return [
            {"q": f"{mt} {subs} fundamental science discovery application 2024 2025 research India",
             "recency": 365},
            {"q": f"site:ncert.nic.in {mt} {subs} science physics chemistry biology principle UPSC",
             "recency": 1500},
        ]
    else:
        return [
            {"q": f"India {mt} {subs} science technology innovation news 2024 2025 official",
             "recency": 365},
            {"q": f"{mt} {subs} technology application India policy scheme 2024 2025",
             "recency": 365},
            {"q": f"site:ncert.nic.in OR site:dst.gov.in {mt} {subs} science technology India UPSC",
             "recency": 1500},
        ]


def _queries_general(mt: str, subs: str) -> List[Dict]:
    return [
        {"q": f"{mt} {subs} India recent development news 2024 2025 official report",
         "recency": 365},
        {"q": f"site:gov.in {mt} {subs} India core concept UPSC standard",
         "recency": 1500},
    ]


def build_current_search_queries(topic_clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate targeted Google Search queries per topic cluster for UPSC question grounding.

    Each cluster produces:
      - 1-2 DYNAMIC queries  (recency=365): specific recent events, data, policy
      - 1   STATIC ANCHOR    (recency=1500): authoritative source for core concept

    Args:
        topic_clusters: list of dicts, each with keys:
            micro_topic   (str)  — most granular topic label, e.g. "Monsoon"
            major_domain  (str)  — domain label, e.g. "Physical_Geography"
            sub_topics    (list) — finer sub-labels, e.g. ["Onset", "Withdrawal"]
            subject       (str)  — optional explicit subject, e.g. "Geography"

    Returns:
        List of query dicts: [{"q": "...", "recency": int}, ...]
    """
    all_queries: List[Dict[str, Any]] = []

    for cluster in topic_clusters:
        mt    = cluster.get("micro_topic", "").strip()
        major = cluster.get("major_domain", "").lower().strip()
        subs  = _top_subs(cluster.get("sub_topics", []))

        subject = _detect_subject(cluster)

        if subject == "geography":
            queries = _queries_geography(mt, subs, major)
        elif subject == "history":
            queries = _queries_history(mt, subs, major)
        elif subject == "economy":
            queries = _queries_economy(mt, subs, major)
        elif subject == "polity":
            queries = _queries_polity(mt, subs, major)
        elif subject == "environment":
            queries = _queries_environment(mt, subs, major)
        elif subject == "science":
            queries = _queries_science(mt, subs, major)
        else:
            queries = _queries_general(mt, subs)

        all_queries.extend(queries)

    return all_queries


async def generate_single_batch(
    batch_num: int,
    chunks: List[Dict],
    num_questions: int,
    topics: List[str],
    api_key: str,
    job_id: str,
    pyq_chunks: List[Dict] = None,
    subject: str = "Geography"
) -> Tuple[List[Dict], int, int]:
    """
    Generate a single batch of questions with validation and provenance tracking

    Returns:
        Tuple of (valid_questions, prompt_tokens, completion_tokens)
    """
    batch_id = f"{job_id}_batch_{batch_num}"
    logger.info(f"🔨 Generating batch {batch_num}: {num_questions} questions for subject={subject}")

    try:
        # Prepare content from chunks
        content_text = "\n\n".join([chunk['content'] for chunk in chunks])

        # Step 0: Build current affairs search queries from chunk metadata
        logger.info(f"📊 [BATCH {batch_num}] Extracting metadata from {len(chunks)} chunks...")
        topic_clusters = []
        for i, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {})
            logger.debug(f"   Chunk {i+1} metadata: {meta}")
            micro = meta.get("micro_topic") or meta.get("section") or meta.get("chapter")
            subs = meta.get("sub_topics") or []
            major_domain = meta.get("major_domain") or meta.get("domain") or ""
            if micro:
                topic_clusters.append({"micro_topic": micro, "sub_topics": subs, "major_domain": major_domain})
                logger.debug(f"   ✅ Chunk {i+1}: micro_topic='{micro}', major_domain='{major_domain}'")
            else:
                logger.warning(f"   ⚠️ Chunk {i+1}: No micro_topic found in metadata")
        
        # Deduplicate topic clusters early
        seen_mt = set()
        unique_clusters = []
        for cluster in topic_clusters:
            mt = cluster.get("micro_topic", "")
            if mt and mt not in seen_mt:
                seen_mt.add(mt)
                unique_clusters.append(cluster)
        
        # 🧪 Topic-Based Research Fallback: If no clusters from metadata, use provided topics or subject taxonomy
        if not unique_clusters:
            logger.info(f"🧪 [BATCH {batch_num}] No metadata clusters found. Implementing synthetic topic clustering fallback.")
            
            # Case A: User provided specific topics (e.g., "Monetary Policy")
            # We filter out the subject name itself if it's in topics to get real topics
            real_topics = [t for t in topics if t.lower() != subject.lower()]
            
            if real_topics:
                for t in real_topics:
                    unique_clusters.append({
                        "micro_topic": t,
                        "sub_topics": [],
                        "major_domain": subject # Use subject as fallback domain
                    })
            else:
                # Case B: No specific topics or only subject name - use taxonomy sweep
                # This is critical for subjects without vector data (Economy, etc.)
                subj_taxonomy = SUBJECT_DOMAINS.get(subject, {})
                if subj_taxonomy:
                    # Pick a few diverse major domains
                    major_domains = list(subj_taxonomy.keys())
                    random.shuffle(major_domains)
                    
                    # Target MAX_RESEARCH_TOPICS
                    target_count = max(5, (num_questions // 2) + 2)
                    
                    for i in range(min(target_count, len(major_domains))):
                        major = major_domains[i]
                        sub_list = subj_taxonomy[major]
                        # Pick a random sub-topic for specificity
                        sub = random.choice(sub_list) if sub_list else ""
                        
                        unique_clusters.append({
                            "micro_topic": sub or major,
                            "sub_topics": [major] if sub else [],
                            "major_domain": major
                        })
                    logger.info(f"   🧬 Synthesized {len(unique_clusters)} topics from {subject} taxonomy for research.")
                else:
                    # Final fallback to subject name
                    unique_clusters.append({
                        "micro_topic": subject,
                        "sub_topics": [],
                        "major_domain": subject
                    })
        
        # Limit unique clusters dynamically based on number of questions
        # Rule: For 10 questions -> ~7 topics. For 5 questions -> 5 topics.
        # Logic: max(5, num_questions // 2 + 2)
        MAX_RESEARCH_TOPICS = max(5, (num_questions // 2) + 2)
        
        if len(unique_clusters) > MAX_RESEARCH_TOPICS:
            logger.info(f"⚖️  Limiting research from {len(unique_clusters)} to {MAX_RESEARCH_TOPICS} topics (Scaling with N={num_questions})")
            unique_clusters = unique_clusters[:MAX_RESEARCH_TOPICS]
        
        logger.info(f"📦 [BATCH {batch_num}] Extracted {len(topic_clusters)} total clusters, using {len(unique_clusters)} for research:")
        for i, cluster in enumerate(unique_clusters):
            logger.info(f"   Research Topic {i+1}: micro_topic='{cluster['micro_topic']}', sub_topics={cluster['sub_topics']}")
        
        logger.info(f"🔍 [BATCH {batch_num}] Building search queries from {len(unique_clusters)} unique clusters...")
        # Add subject to each cluster for query building
        for cluster in unique_clusters:
            cluster["subject"] = subject
            
        search_queries = build_current_search_queries(unique_clusters)
        logger.info(f"✅ [BATCH {batch_num}] Generated {len(search_queries)} search queries ({len(search_queries)//3} topics × 3 queries):")
        for i, sq in enumerate(search_queries[:9]):  # Show first 9 queries (3 topics)
            logger.info(f"   Query {i+1}: {sq['q'][:100]}... (recency: {sq['recency']} days)")
        if len(search_queries) > 9:
            logger.info(f"   ... and {len(search_queries) - 9} more queries")
        
        # Prepare prompt
        topic = topics[0] if topics else subject 
        user_prompt = assemble_upsc_prompt(
            topic=topic,
            subject=subject,
            num_questions=num_questions,
            retrieved_static_text=content_text,
            retrieved_current_affairs="", # Will be filled by Gemini tool use
            pyq_chunks=pyq_chunks,
            search_queries=search_queries # Pass queries to prompt builder
        )

        # Use GeminiClient for generation with structured output
        if not GEMINI_API_KEY:
            logger.error("❌ Gemini API key not found")
            return [], 0, 0
            
        gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
        
        try:
            # We need a system prompt
            from ..utils.mock_test_prompting import get_system_prompt
            system_prompt = get_system_prompt(subject)
            
            # IMPORTANT: Gemini doesn't support response_schema + Google Search together
            # We must parse JSON manually when using search tool
            response_text = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response_schema=None,  # Cannot use with Google Search
                temperature=0.8,
                use_google_search=True # Enable search
            )
            
            # Simple token estimation for Gemini (Simplified)
            prompt_tokens = len(user_prompt) // 4
            completion_tokens = len(response_text) // 4
            
            # Log raw response for debugging
            logger.info(f"📥 [BATCH {batch_num}] Gemini raw response length: {len(response_text)} chars")
            logger.debug(f"📥 [BATCH {batch_num}] First 500 chars: {response_text[:500]}")
            
        except Exception as e:
            logger.error(f"❌ Gemini generation failed for batch {batch_num}: {e}")
            return [], 0, 0

        # Parse JSON response - handle markdown wrapping and other issues
        import json
        import re
        
        questions_data = []
        factual_units = []
        current_affairs_bullets = []
        
        try:
            # First try direct parse
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
            factual_units = response_data.get("factual_units", [])
            current_affairs_bullets = response_data.get("current_affairs_bullets", [])
            
            if factual_units:
                logger.info(f"🧬 [BATCH {batch_num}] Extracted {len(factual_units)} Atomic Factual Units for grounding")
                for i, unit in enumerate(factual_units[:5]):
                    logger.info(f"   Fact {i+1}: {unit[:120]}...")
            
            logger.info(f"✅ [BATCH {batch_num}] Direct JSON parse successful")
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [BATCH {batch_num}] Direct JSON parse failed: {e}. Attempting extraction...")
            
            # Markdown code block extraction
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match:
                 # Try finding just { ... } if no code blocks
                 json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            
            if json_match:
                try:
                    response_data = json.loads(json_match.group(1))
                    questions_data = response_data.get("questions", [])
                    factual_units = response_data.get("factual_units", [])
                    current_affairs_bullets = response_data.get("current_affairs_bullets", [])
                    
                    if factual_units:
                        logger.info(f"🧬 [BATCH {batch_num}] Extracted {len(factual_units)} Factual Units from markdown block")
                    
                    logger.info(f"✅ [BATCH {batch_num}] JSON extraction successful")
                except Exception as ex:
                    logger.error(f"❌ [BATCH {batch_num}] Both direct parse and extraction failed: {ex}")
            else:
                logger.error(f"❌ [BATCH {batch_num}] No JSON found in response")
            
            # Try to find raw JSON object if questions_data is still empty
            if not questions_data:
                json_obj_match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', response_text)
                if json_obj_match:
                    try:
                        response_data = json.loads(json_obj_match.group(0))
                        questions_data = response_data.get("questions", [])
                        current_affairs_bullets = response_data.get("current_affairs_bullets", [])
                        logger.info(f"✅ [BATCH {batch_num}] Extracted JSON via regex")
                    except json.JSONDecodeError:
                        pass
            
            # Final fallback: use sanitize_json_response
            if not questions_data:
                logger.warning(f"⚠️ [BATCH {batch_num}] Trying sanitize_json_response fallback...")
                sanitized_text = sanitize_json_response(response_text)
                try:
                    response_data = json.loads(sanitized_text)
                    questions_data = response_data.get("questions", [])
                    current_affairs_bullets = response_data.get("current_affairs_bullets", [])
                    logger.info(f"✅ [BATCH {batch_num}] Sanitization fallback successful")
                except:
                    logger.error(f"❌ [BATCH {batch_num}] All JSON parsing attempts failed")
        
        # Log current affairs bullets if found
        if current_affairs_bullets:
            logger.info(f"🗞️ [BATCH {batch_num}] Found {len(current_affairs_bullets)} current affairs bullets:")
            for i, bullet in enumerate(current_affairs_bullets[:5]):
                logger.info(f"   CA Bullet {i+1}: {bullet[:100]}...")

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
    pyq_chunks: List[Dict] = None,
    subject: str = "Geography"
) -> Tuple[List[Dict], List[str]]:
    """
    Generate questions in micro-batches with parallel execution.

    Returns:
        Tuple of (all_questions, gap_subdomains) where gap_subdomains lists
        under-represented sub-domains when entropy is below threshold.
    """
    # Calculate batches with 10% buffer
    buffer_factor = 1.1
    target_questions = int(num_questions * buffer_factor)
    questions_per_batch = 10
    num_batches = math.ceil(target_questions / questions_per_batch)

    logger.info(f"📦 Micro-batch plan: {num_batches} batches × {questions_per_batch} questions = {target_questions} total (target: {num_questions})")

    # Partition chunks with sub-domain diversity enforced per batch
    batch_chunks = partition_all_batches(
        all_chunks, num_batches,
        batch_size=questions_per_batch,
        max_per_subdomain=3,
    )

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
                pyq_chunks=pyq_chunks,
                subject=subject
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

    # Entropy-based diversity check
    chunk_subdomains = {
        c.get("metadata", {}).get("sub_domain", "Unknown") for c in all_chunks
    }
    entropy = subdomain_entropy_score(all_questions)
    logger.info(f"📊 Sub-domain entropy of generated questions: {entropy:.3f}")

    gap_subdomains: List[str] = []
    if entropy < 0.6 and len(chunk_subdomains) > 1:
        question_sd_counts: Dict[str, int] = defaultdict(int)
        for q in all_questions:
            sd = q.get("source", {}).get("sub_domain", "Unknown")
            question_sd_counts[sd] += 1

        avg_count = len(all_questions) / max(len(chunk_subdomains), 1)
        for sd in chunk_subdomains:
            if question_sd_counts.get(sd, 0) < avg_count * 0.5:
                gap_subdomains.append(sd)

        logger.warning(
            f"⚠️ Low sub-domain entropy ({entropy:.3f} < 0.6). "
            f"Under-represented sub-domains: {gap_subdomains}"
        )

    return all_questions, gap_subdomains


async def fill_gaps_targeted(
    current_questions: List[Dict],
    target: int,
    topics: List[str],
    api_key: str,
    job_id: str,
    pinecone_handler,
    pyq_chunks: List[Dict] = None,
    target_subdomains: List[str] = None,
) -> List[Dict]:
    """
    Targeted gap-fill generation for missing questions.

    When *target_subdomains* is provided (from the entropy check), retrieval
    targets those specific sub-domains instead of only looking at major_domain.
    """
    gap = target - len(current_questions)
    if gap <= 0:
        return []

    logger.info(f"🔧 Gap-fill needed: {gap} questions short of {target}")

    all_gap_questions: List[Dict] = []

    if target_subdomains:
        logger.info(f"   🎯 Targeting under-represented sub-domains: {target_subdomains}")
        questions_per_sd = max(1, gap // len(target_subdomains))

        for sd in target_subdomains:
            query = build_query_text(None, sd)
            sd_chunks = pinecone_handler.query_documents(
                query_text=query,
                k=max(5, questions_per_sd),
                filter_metadata={"sub_domain": sd},
            )
            if not sd_chunks:
                logger.warning(f"   ⚠️ No chunks found for sub-domain '{sd}', skipping")
                continue

            sd_questions, _, _ = await generate_single_batch(
                batch_num=998,
                chunks=sd_chunks,
                num_questions=questions_per_sd,
                topics=topics,
                api_key=api_key,
                job_id=job_id,
                pyq_chunks=pyq_chunks,
            )
            all_gap_questions.extend(sd_questions)
            if len(all_gap_questions) >= gap:
                break
    else:
        current_distribution = defaultdict(int)
        for q in current_questions:
            domain = q.get("source", {}).get("domain", "General")
            current_distribution[domain] += 1

        logger.info(f"   📊 Current distribution: {dict(current_distribution)}")

        if current_distribution:
            min_domain = min(current_distribution, key=current_distribution.get)
            logger.info(f"   🎯 Targeting underrepresented domain: {min_domain}")

            query = build_query_text(min_domain, None)
            gap_chunks = pinecone_handler.query_documents(
                query_text=query,
                k=max(5, gap // 2),
                filter_metadata={"major_domain": min_domain},
            )
        else:
            gap_chunks = pinecone_handler.query_documents(
                query_text=build_query_text(None, None),
                k=max(5, gap // 2),
            )

        gap_questions, _, _ = await generate_single_batch(
            batch_num=999,
            chunks=gap_chunks,
            num_questions=gap,
            topics=topics,
            api_key=api_key,
            job_id=job_id,
            pyq_chunks=pyq_chunks,
        )
        all_gap_questions.extend(gap_questions)

    logger.info(f"   ✅ Generated {len(all_gap_questions)} gap-fill questions")
    return all_gap_questions




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
            logger.warning(f"⚠️ [JOB {job_id[:8]}] Low content mode: only {len(all_chunks)} chunks retrieved. Proceeding with LLM knowledge and research fallback.")

        # Step 2: Generate micro-batches
        logger.info(f"🔨 [JOB {job_id[:8]}] Step 2: Generating micro-batches")
        try:
            all_questions, gap_subdomains = await generate_micro_batches(
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

        # Step 4: Gap-fill if needed (quantity shortfall OR low sub-domain diversity)
        needs_quantity_fill = len(unique_questions) < num_questions
        needs_diversity_fill = bool(gap_subdomains)

        if needs_quantity_fill or needs_diversity_fill:
            reason = []
            if needs_quantity_fill:
                reason.append(f"quantity {len(unique_questions)}/{num_questions}")
            if needs_diversity_fill:
                reason.append(f"diversity gaps in {gap_subdomains}")
            logger.info(f"🔧 [JOB {job_id[:8]}] Step 4: Gap-filling ({', '.join(reason)})")

            try:
                gap_fill = await fill_gaps_targeted(
                    current_questions=unique_questions,
                    target=num_questions,
                    topics=topics,
                    api_key=api_key,
                    job_id=job_id,
                    pinecone_handler=pinecone_handler,
                    pyq_chunks=pyq_chunks,
                    target_subdomains=gap_subdomains if needs_diversity_fill else None,
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
            subject=test_request.subject,
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
