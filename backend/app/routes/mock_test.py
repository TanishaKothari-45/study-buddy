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
from openai import OpenAI, RateLimitError

from ..core.config import settings
from ..utils.upsc_patterns.loader import get_examples, format_fewshot, get_all_patterns
from ..utils.metadata_enricher import GEOGRAPHY_TOPICS, GEOGRAPHY_DOMAINS
from ..routes.query import deduplicate_chunks
from ..utils.mm_utils import enforce_source_diversity
from ..utils.mock_test_prompting import assemble_upsc_prompt
from ..utils.query_builder import build_query_text, build_current_affairs_query
from ..utils.memory_manager import (
    init_memory_db,
    get_recent_questions,
    filter_recency,
    record_recent_question,
    record_feedback,
    get_high_quality_examples
)

# Phase 1: New imports for scaled generation
from ..utils.question_provenance import QuestionProvenance, get_question_bank
from ..utils.job_tracker import get_job_store, JobStatus
from ..utils.batch_validator import validate_batch, calculate_quality_score
from ..utils.semantic_dedup import semantic_deduplicate, hash_based_deduplicate

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize memory database (only once at startup)
init_memory_db()

class MockTestRequest(BaseModel):
    num_questions: int = 5
    topics: List[str] = []  # Optional topics to focus on
    difficulty: str = "medium"  # easy, medium, hard

class MockTestQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    source: Dict[str, Any]  # Reference to source material

class MockTestResponse(BaseModel):
    questions: List[MockTestQuestion]
    total_marks: int
    time_allowed: str
    instructions: List[str]

def generate_fewshot_examples(
    num_questions: int = 5, 
    topics: List[str] = None, 
    difficulty: str = "medium",
    pyq_chunks: List[Dict] = None
) -> tuple:
    """
    Generate diverse few-shot examples for style learning.
    
    Style learning composition:
    - 40% PYQ chunks (from database)
    - 40% from patterns JSON
    - 30% from feedback (if available, else increase other proportions)
    
    Args:
        num_questions: Number of questions to generate
        topics: List of topics
        difficulty: Difficulty level
        pyq_chunks: PYQ chunks from database (for style learning)
    
    Returns:
        Tuple of (fewshot_string, pattern_list) where pattern_list shows all available patterns
    """
    try:
        style_examples = []
        pattern_info = {}
        
        # ================================
        # 1️⃣ Get patterns from JSON (40% of style learning)
        # ================================
        all_patterns = get_all_patterns()
        pattern_examples_list = []
        
        for pattern in all_patterns:
            # Get at least 1 example from each pattern
            pattern_examples = get_examples(topic=None, pattern=pattern["id"], n=2)
            if pattern_examples:
                example = pattern_examples[0]
                example["_pattern_id"] = pattern["id"]
                example["_pattern_title"] = pattern.get("title", "")
                example["_pattern_explanation"] = pattern.get("explanation", "")
                example["_source"] = "patterns_json"  # Mark as from patterns JSON
                pattern_examples_list.append(example)
                pattern_info[pattern["id"]] = {
                    "title": pattern.get("title", ""),
                    "explanation": pattern.get("explanation", "")
                }
        
        # If we need more examples, get additional ones from random patterns
        if len(pattern_examples_list) < 6:
            additional = get_examples(n=6 - len(pattern_examples_list))
            for ex in additional:
                ex["_source"] = "patterns_json"  # Mark as from patterns JSON
            pattern_examples_list.extend(additional)
        
        # ================================
        # 2️⃣ Get high-quality examples from feedback DB (30% of style learning)
        # ================================
        filter_topic = topics[0] if topics else None
        feedback_examples = get_high_quality_examples(
            limit=3,  # Target 3 examples (30%)
            topic=filter_topic,
            difficulty=difficulty
        )
        
        # ================================
        # 3️⃣ Get PYQ chunks from database (40% of style learning)
        # ================================
        pyq_examples_list = []
        if pyq_chunks:
            # Use PYQ chunks directly (they're already retrieved and filtered)
            for chunk in pyq_chunks[:5]:  # Use top 5 PYQ chunks
                pyq_examples_list.append({
                    "_pattern_id": "pyq_chunk",
                    "_pattern_title": "PYQ Database",
                    "question": chunk.get("content", ""),
                    "options": [],
                    "answer": "N/A",
                    "topic": chunk.get("metadata", {}).get("sub_domain", "N/A"),
                    "year": "PYQ Database",
                    "_source": "database"
                })
            pattern_info["pyq_chunk"] = {
                "title": "PYQ Database Examples",
                "explanation": "Previous Year Questions from database"
            }
        
        # ================================
        # 4️⃣ Combine with proper proportions (40% PYQ + 40% patterns + 30% feedback)
        # ================================
        # Calculate target counts based on total examples needed
        total_style_examples = 10  # Target total style examples
        
        # If feedback available: 40% PYQ, 40% patterns, 30% feedback
        if feedback_examples:
            target_pyq = max(3, int(total_style_examples * 0.4))  # ~4 examples
            target_patterns = max(3, int(total_style_examples * 0.4))  # ~4 examples
            target_feedback = max(2, int(total_style_examples * 0.3))  # ~3 examples
            
            # Add PYQ chunks (40%)
            style_examples.extend(pyq_examples_list[:target_pyq])
            
            # Add patterns (40%)
            style_examples.extend(pattern_examples_list[:target_patterns])
            
            # Add feedback (30%)
            for fb_ex in feedback_examples[:target_feedback]:
                style_examples.append({
                    "_pattern_id": "feedback",
                    "_pattern_title": "User Feedback",
                    "question": fb_ex['text'],
                    "options": [],
                    "answer": "N/A",
                    "topic": fb_ex.get('topic', 'N/A'),
                    "year": "User Feedback",
                    "_reason": fb_ex.get('reason', ''),
                    "_source": "feedback"
                })
                pattern_info["feedback"] = {
                    "title": "User Feedback Examples",
                    "explanation": "High-quality questions from user feedback"
                }
        else:
            # No feedback: redistribute proportions (50% PYQ, 50% patterns)
            target_pyq = max(4, int(total_style_examples * 0.5))  # ~5 examples
            target_patterns = max(4, int(total_style_examples * 0.5))  # ~5 examples
            
            style_examples.extend(pyq_examples_list[:target_pyq])
            style_examples.extend(pattern_examples_list[:target_patterns])
        
        # ================================
        # 5️⃣ Format few-shot examples
        # ================================
        fewshot_parts = []
        for i, ex in enumerate(style_examples, 1):
            pattern_title = ex.get("_pattern_title", "UPSC Pattern")
            pattern_id = ex.get("_pattern_id", "")
            example_text = f"Example {i} - Pattern: {pattern_title} (ID: {pattern_id})\n"
            example_text += f"{ex['question']}\n"
            if ex.get("options"):
                example_text += "\n".join(ex.get("options", [])) + f"\n✅ Correct Answer: ({ex['answer']})\n📘 Topic: {ex.get('topic', 'N/A')} (Year: {ex.get('year', 'N/A')})"
            else:
                example_text += f"📘 Topic: {ex.get('topic', 'N/A')} (Year: {ex.get('year', 'N/A')})"
            # Add reason if it's a feedback example
            if ex.get("_reason"):
                example_text += f"\n💡 Note: {ex['_reason']}"
            fewshot_parts.append(example_text)
        
        fewshot = "\n\n---\n\n".join(fewshot_parts)
        
        # Create pattern summary for prompt
        pattern_summary = "\n".join([
            f"- {info['title']} ({pid}): {info['explanation'][:100]}..."
            for pid, info in pattern_info.items()
        ])
        
        # Log composition
        pyq_count = len([e for e in style_examples if e.get("_source") == "database"])
        feedback_count = len([e for e in style_examples if e.get("_source") == "feedback"])
        pattern_count = len([e for e in style_examples if e.get("_source") == "patterns_json"])
        
        logger.info(f"📚 Generated {len(style_examples)} style learning examples:")
        logger.info(f"   📝 PYQ chunks: {pyq_count} (40%)")
        logger.info(f"   📋 Patterns JSON: {pattern_count} (40%)")
        logger.info(f"   ⭐ Feedback: {feedback_count} ({'30%' if feedback_count > 0 else '0% - redistributed'})")
        
        return fewshot, pattern_summary
    except FileNotFoundError as e:
        logger.warning(f"⚠️ PYQ patterns file not found: {e}")
        return "", ""
    except Exception as e:
        logger.error(f"❌ Failed to generate few-shot examples: {str(e)}")
        return "", ""

from ..utils.langsmith_tracer import trace_llm

@trace_llm("mock_test_generation")
def generate_question_paper(pyq_chunks: List[Dict], content_chunks: List[Dict], 
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
    # Generate style learning examples (40% PYQ + 40% patterns + 30% feedback)
    # PYQ chunks are passed directly for style learning (not used in content)
    fewshot_examples, pattern_summary = generate_fewshot_examples(
        num_questions=request.num_questions,
        topics=request.topics,
        difficulty=request.difficulty,
        pyq_chunks=pyq_chunks  # Pass PYQ chunks for style learning
    )
    
    # Prepare content context from final_content (already optimized through diversity + MMR)
    # No need to split again - use the best chunks we already have!
    logger.info(f"📝 [MOCK_TEST] Preparing content context from {len(content_chunks)} optimized chunks...")
    
    # Convert chunks to documents for deduplication
    content_docs = []
    for chunk in content_chunks[:15]:  # Use top 15 optimized chunks
        from langchain_core.documents import Document
        content_docs.append(Document(
            page_content=chunk['content'],
            metadata=chunk.get('metadata', {})
        ))
    
    # Deduplicate content chunks (already optimized, just remove overlaps)
    if content_docs:
        content_text = deduplicate_chunks(content_docs, min_overlap_words=20, similarity_threshold=0.6)
        logger.info(f"   ✅ Prepared {len(content_chunks)} content chunks (deduplicated, already optimized)")
    else:
        content_text = "\n\n".join([chunk['content'] for chunk in content_chunks[:15]])
    
    # Style learning examples (already includes PYQ chunks + patterns + feedback)
    style_examples_text = fewshot_examples if fewshot_examples else ""
    
    # Extract topic from request (use first topic or "Geography" as default)
    topic = request.topics[0] if request.topics else "Geography"
    
    # Log content vs style proportions
    total_content_chars = len(content_text)
    total_style_chars = len(style_examples_text)
    total_chars = total_content_chars + total_style_chars
    
    if total_chars > 0:
        content_percent = (total_content_chars / total_chars) * 100
        style_percent = (total_style_chars / total_chars) * 100
        logger.info(f"📊 Prompt composition:")
        logger.info(f"   📘 Content (factual): {content_percent:.1f}% ({len(content_chunks)} optimized chunks)")
        logger.info(f"   📝 Style learning: {style_percent:.1f}% (PYQ chunks + patterns + feedback)")
    
    if fewshot_examples:
        logger.info(f"✅ Style learning examples ready (includes PYQ chunks + patterns + feedback)")
    else:
        logger.warning("⚠️ No style learning examples available")
    
    # Use new prompt system
    try:
        # Assemble prompt using new system
        # Use single content_text (already optimized mix of static + current affairs)
        user_prompt = assemble_upsc_prompt(
            topic=topic,
            difficulty=request.difficulty,
            num_questions=request.num_questions,
            retrieved_static_text=content_text,  # Single optimized content (70%)
            retrieved_current_affairs="",  # Already included in content_text
            pyq_examples=style_examples_text  # Style learning (30%)
        )
        
        client = OpenAI(api_key=api_key)
        # Use large model (gpt-4o) for final question generation - this is the critical quality step
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL_LARGE,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.85 if request.difficulty == "hard" else 0.7,
            max_tokens=min(4000, 500 * request.num_questions),  # Dynamic tokens: ~500 per question, max 4000
            response_format={ "type": "json_object" }
        )
        
        # Parse GPT response
        response_text = completion.choices[0].message.content
        
        # Parse JSON response
        import json
        try:
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
        except json.JSONDecodeError:
            # Fallback: try to extract questions from text
            logger.warning("Failed to parse JSON response, using fallback parsing")
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
                        "topics": q_data.get("source", {}).get("topics", request.topics),
                        "difficulty": request.difficulty
                    }
                )
                questions.append(question)
                
                # 🆕 STEP 5: Memory Update - Store question in recency DB
                try:
                    # Extract topic and subtopic from request
                    topic = request.topics[0] if request.topics else "Geography"
                    subtopic = request.topics[1] if len(request.topics) > 1 else topic
                    
                    # Store in recency DB
                    record_recent_question(
                        question_text=question_text,
                        topic=topic,
                        subtopic=subtopic,
                        difficulty=request.difficulty
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

def hybrid_retrieve_for_mock_test(
    pinecone_handler,
    topics: List[str],
    num_questions: int = 10,
    difficulty: str = "medium"
) -> Tuple[List[Dict], List[Dict]]:
    """
    Hybrid retrieval using source_type metadata filters with adaptive, difficulty-aware queries.
    
    This function implements:
    1. Adaptive query generation based on domain granularity and difficulty
    2. PYQ retrieval using source_type="pyq" filter (for style learning)
    3. Concept retrieval using source_type="concept" filter (for content knowledge)
    4. Current affairs retrieval using source_type="current_affairs" filter (semantically related to concepts)
    5. Source diversity enforcement using enforce_source_diversity
    6. Final MMR re-ranking for cross-source diversity
    
    Args:
        pinecone_handler: PineconeHandler instance
        topics: List of topics (sub-domains or major domains from dropdowns)
        num_questions: Number of questions to generate (for context sizing)
        difficulty: Difficulty level ("easy", "medium", "hard") - affects query semantics
    
    Returns:
        Tuple of (pyq_chunks, content_chunks) ready for question generation
    """
    # Extract domains from topics
    major_domain, sub_domain = extract_domains_from_topics(topics)
    
    logger.info(f"🎯 [HYBRID_RETRIEVE] Starting retrieval: major_domain={major_domain}, sub_domain={sub_domain}, difficulty={difficulty}")
    
    # Build adaptive, semantically rich query using query builder
    query = build_query_text(major_domain, sub_domain, difficulty)
    
    # Set retrieval parameters based on domain granularity AND question count
    # Phase 1: Scale retrieval based on num_questions (1 chunk per 2 questions)
    base_chunks_needed = max(10, num_questions // 2)
    
    if sub_domain:
        k_target = base_chunks_needed  # Focused retrieval
        lambda_mult = 0.65
        logger.info(f"   🎯 Sub-domain mode: {k_target} chunks for {num_questions} questions in {sub_domain}")
    elif major_domain:
        k_target = base_chunks_needed + 2  # Slightly more for domain diversity
        lambda_mult = 0.65
        logger.info(f"   🎯 Major-domain mode: {k_target} chunks for {num_questions} questions")
    else:
        k_target = base_chunks_needed + 5  # Even more for general coverage
        lambda_mult = 0.6
        logger.info(f"   🎯 General mode: {k_target} chunks for {num_questions} questions (broad coverage)")
    
    logger.info(f"   📝 Generated query: {query[:150]}...")
    
    # ================================
    # 1️⃣ Conceptual Base Retrieval (source_type="concept")
    # ================================
    # Flow: Pinecone vector search → get chunk_ids → enrich from local DB (content store)
    # 🆕 STEP 1: Apply recency filter to avoid repeating recently generated questions
    logger.info("📘 Retrieving conceptual chunks (source_type='concept')...")
    logger.info("   🔍 Step 1: Querying Pinecone vectorstore for similar embeddings...")
    try:
        # Retrieve k_target + 3 chunks as buffer for recency filtering
        # Use MMR for diversity based on granularity (lambda_mult varies by domain)
        initial_k = k_target + 3
        fetch_k = initial_k * 3  # Fetch more candidates for MMR diversity selection
        concept_chunks = pinecone_handler.query_documents_mmr(
            query_text=query,
            fetch_k=fetch_k,  # Fetch more candidates for MMR
            k=initial_k,  # Final count: k_target + 3 buffer for recency filtering
            lambda_mult=lambda_mult,  # Use granularity-based diversity (0.65 for sub/major, 0.6 for general)
            filter_metadata={"source_type": "concept"}
        )
        # Enrich with full content from content store (query_documents_mmr doesn't support use_content_store)
        if concept_chunks:
            try:
                from ..utils.content_store import ContentStore
                content_store = ContentStore()
                
                for chunk in concept_chunks:
                    chunk_id = chunk.get("metadata", {}).get("chunk_id")
                    filename = chunk.get("metadata", {}).get("filename")
                    chapter = chunk.get("metadata", {}).get("chapter")
                    
                    if chunk_id and filename:
                        full_content = content_store.get_chunk(
                            chunk_id=chunk_id,
                            filename=filename,
                            chapter=chapter
                        )
                        if full_content:
                            chunk["content"] = full_content
                            chunk["metadata"]["_content_source"] = "content_store"
                        else:
                            chunk["metadata"]["_content_source"] = "content_preview"
            except Exception as e:
                logger.debug(f"⚠️ Content store enrichment failed: {e}, using preview content")
                for chunk in concept_chunks:
                    chunk["metadata"]["_content_source"] = "content_preview"
        logger.info(f"   ✅ Retrieved {len(concept_chunks)} concept chunks (enriched from content store)")
        
        # 🆕 STEP 1 (continued): Apply recency filter
        logger.info("   🔄 Applying recency filter (last 7 days)...")
        recent_questions = get_recent_questions(days=7)
        concept_chunks = filter_recency(concept_chunks, recent_questions)
        logger.info(f"   ✅ After recency filter: {len(concept_chunks)} concept chunks")
    except Exception as e:
        logger.warning(f"⚠️ Concept retrieval failed: {e}")
        concept_chunks = []
    
    # ================================
    # 2️⃣ PYQ Retrieval for Style (source_type="pyq")
    # ================================
    # Flow: Pinecone vector search → get chunk_ids → enrich from local DB (content store)
    # Note: PYQ chunks are historical examples, so recency filter is less critical
    logger.info("📝 Retrieving PYQ chunks (source_type='pyq') for style reference...")
    logger.info("   🔍 Step 1: Querying Pinecone vectorstore for similar embeddings...")
    try:
        # PYQ retrieval fixed at 6 (for style learning, no variation needed)
        # Use MMR for diversity in PYQ retrieval
        pyq_chunks = pinecone_handler.query_documents_mmr(
            query_text=query,
            fetch_k=18,  # Fetch more candidates for MMR diversity (6 * 3)
            k=6,  # Fixed for style learning
            lambda_mult=0.6,  # Moderate diversity for PYQ style examples
            filter_metadata={"source_type": "pyq", "source_subtype": "prelims"}
        )
        # Enrich with full content from content store (query_documents_mmr doesn't support use_content_store)
        if pyq_chunks:
            try:
                from ..utils.content_store import ContentStore
                content_store = ContentStore()
                
                for chunk in pyq_chunks:
                    chunk_id = chunk.get("metadata", {}).get("chunk_id")
                    filename = chunk.get("metadata", {}).get("filename")
                    chapter = chunk.get("metadata", {}).get("chapter")
                    
                    if chunk_id and filename:
                        full_content = content_store.get_chunk(
                            chunk_id=chunk_id,
                            filename=filename,
                            chapter=chapter
                        )
                        if full_content:
                            chunk["content"] = full_content
                            chunk["metadata"]["_content_source"] = "content_store"
                        else:
                            chunk["metadata"]["_content_source"] = "content_preview"
            except Exception as e:
                logger.debug(f"⚠️ PYQ content store enrichment failed: {e}, using preview content")
                for chunk in pyq_chunks:
                    chunk["metadata"]["_content_source"] = "content_preview"
        logger.info(f"   ✅ Retrieved {len(pyq_chunks)} PYQ chunks (enriched from content store)")
    except Exception as e:
        logger.warning(f"⚠️ PYQ retrieval failed: {e}")
        pyq_chunks = []
    
    # ================================
    # 3️⃣ Current Affairs Overlay (Semantically Related to Concept)
    # ================================
    # Flow: For each concept chunk → Pinecone vector search → get chunk_ids → enrich from local DB
    # Only retrieve current affairs for medium/hard difficulty
    current_chunks = []
    if difficulty.lower() in ["medium", "hard"]:
        logger.info("🗞️ Retrieving current affairs chunks (source_type='current_affairs')...")
        logger.info("   🔍 Querying Pinecone for semantically related current affairs...")
        try:
            # For each concept chunk, find semantically related current affairs using improved query
            for chunk in concept_chunks[:5]:  # Limit to first 5 to control cost
                try:
                    # Extract conceptual focus from metadata (preferred) or content
                    meta = chunk.get("metadata", {})
                    topic_title = meta.get("section") or meta.get("chapter") or meta.get("sub_domain")
                    
                    if topic_title:
                        conceptual_focus = topic_title
                    else:
                        # Fallback: extract from content (first 100 chars, clean)
                        content_preview = chunk.get("content", "")[:100].strip()
                        # Remove common prefixes and clean
                        conceptual_focus = content_preview.split('.')[0].split('\n')[0].strip()
                        if len(conceptual_focus) < 10:
                            conceptual_focus = "Geography concept"
                    
                    # Build semantic query for current affairs
                    query_text = build_current_affairs_query(
                        conceptual_focus=conceptual_focus,
                        difficulty=difficulty
                    )
                    
                    # Retrieve current affairs chunks (varies by difficulty)
                    current_affairs_k = 2 if difficulty.lower() == "medium" else 3
                    matches = pinecone_handler.query_documents(
                        query_text=query_text,
                        k=current_affairs_k,
                        filter_metadata={"source_type": "current_affairs"},
                        use_content_store=True  # Enriches with full content from local DB using chunk_ids
                    )
                    current_chunks.extend(matches)
                    logger.debug(f"   ✅ Found {len(matches)} current affairs for '{conceptual_focus}'")
                except Exception as e:
                    logger.debug(f"   ⚠️ Current affairs search failed for chunk: {e}")
                    continue
            
            # Deduplicate current chunks
            seen_content = set()
            unique_current_chunks = [] 
            for chunk in current_chunks:
                content_hash = hash(chunk["content"][:100])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    unique_current_chunks.append(chunk)
            current_chunks = unique_current_chunks
            
            logger.info(f"   ✅ Retrieved {len(current_chunks)} unique current affairs chunks")
        except Exception as e:
            logger.warning(f"⚠️ Current affairs retrieval failed: {e}")
            current_chunks = []
    else:
        logger.info("   ⏭️ Skipping current affairs retrieval (easy mode)")
    
    # ================================
    # 4️⃣ Process Content Chunks Only (PYQ chunks kept separate for style learning)
    # ================================
    # IMPORTANT: PYQ chunks are NOT included in source diversity/MMR - they're for style learning only
    content_chunks_only = concept_chunks + current_chunks
    logger.info(f"📊 Content chunks: {len(concept_chunks)} concept + {len(current_chunks)} current affairs = {len(content_chunks_only)} total")
    logger.info(f"📝 PYQ chunks (for style learning): {len(pyq_chunks)} chunks (NOT in source diversity/MMR)")
    
    # Apply recency filter to content chunks only (not PYQ chunks)
    logger.info("🔄 Applying recency filter to content chunks...")
    recent_questions = get_recent_questions(days=7)
    content_chunks_only = filter_recency(content_chunks_only, recent_questions)
    logger.info(f"   ✅ After recency filter: {len(content_chunks_only)} content chunks")
    
    # Calculate adaptive total_target for source diversity (15-20 range, adaptive to available chunks)
    # Ensures we have enough chunks while respecting availability
    available_chunks = len(content_chunks_only)
    # Target between 15-20, but don't exceed available chunks
    # Formula: k_target + 5 gives us a good target, clamped to 15-20 range and available chunks
    total_target = min(max(15, k_target + 5), min(20, available_chunks))
    logger.info(f"   🎯 Source diversity target: {total_target} chunks (available: {available_chunks}, k_target: {k_target})")
    
    # Apply source diversity v2 (ONLY on content chunks - no PYQ chunks)
    # PYQ chunks are handled separately for style learning, not included in content diversity
    diverse_content_chunks = enforce_source_diversity(
        content_chunks_only,
        total_target=total_target,  # Adaptive: 15-20 range, respects available chunks
        source_weights={"current_affairs": 0.4, "concept": 0.6},  # No PYQ - PYQ chunks are separate for style learning
        concept_subweights={"ncert": 0.25, "topic": 0.25},
        max_per_file=2
    )
    
    # ================================
    # 5️⃣ Final MMR Re-ranking (ONLY content chunks)
    # ================================
    logger.info("🔄 Applying final MMR re-ranking to content chunks...")
    if diverse_content_chunks:
        # MMR uses same k as source diversity target (ensures consistency)
        mmr_k = min(total_target, len(diverse_content_chunks))
        final_content = pinecone_handler.mmr_select_from_chunks(
            chunks=diverse_content_chunks,
            query_text=query,
            k=mmr_k,  # Use total_target from source diversity
            lambda_mult=lambda_mult
        )
        logger.info(f"   ✅ MMR selected {len(final_content)}/{len(diverse_content_chunks)} chunks (target: {mmr_k})")
    else:
        final_content = diverse_content_chunks
    
    # Fallback: if we don't have enough content chunks, use original with proper ratio
    if len(final_content) < 3 and concept_chunks:
        logger.warning(f"⚠️ Only {len(final_content)} content chunks after filtering, using fallback")
        # Use total_target with proper ratio (60% concept, 40% current affairs)
        fallback_concept_count = int(total_target * 0.6)
        fallback_current_count = int(total_target * 0.4)
        final_content = concept_chunks[:fallback_concept_count] + current_chunks[:fallback_current_count]
        logger.info(f"   📊 Fallback: {fallback_concept_count} concept + {fallback_current_count} current affairs = {len(final_content)} total")
    
    # PYQ chunks remain separate - no filtering, no MMR, used directly for style learning
    pyq_final = pyq_chunks[:5]  # Use top 5 PYQ chunks for style learning
    
    logger.info(f"📊 Final selection:")
    logger.info(f"   📝 PYQ chunks (style learning): {len(pyq_final)} chunks")
    logger.info(f"   📘 Content chunks (factual knowledge): {len(final_content)} chunks")
    
    return pyq_final, final_content

@router.get("/domains")
async def get_geography_domains():
    """Get the geography domain structure for dropdowns"""
    return {"domains": GEOGRAPHY_DOMAINS}

@router.post("/generate", response_model=MockTestResponse)
async def generate_mock_test(request: Request, test_request: MockTestRequest):
    """Generate a UPSC-style mock test using hybrid retrieval with progressive fallback and source diversity"""
    try:
        logger.info(f"🚀 [MOCK_TEST] Received request: {test_request.num_questions} questions, topics={test_request.topics}, difficulty={test_request.difficulty}")
        
        pinecone_handler = request.app.state.vector_handler
        
        # Extract major_domain and sub_domain from topics (from dropdowns)
        major_domain, sub_domain = extract_domains_from_topics(test_request.topics)
        logger.info(f"📌 Using domains for retrieval: major_domain={major_domain}, sub_domain={sub_domain}")
        
        # Use hybrid retrieval pipeline with all enhancements
        pyq_chunks, content_chunks = hybrid_retrieve_for_mock_test(
            pinecone_handler=pinecone_handler,
            topics=test_request.topics,
            num_questions=test_request.num_questions,
            difficulty=test_request.difficulty  # Pass difficulty for adaptive query generation
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
                detail="OpenAI API key not configured. Mock test generation requires GPT for quality questions."
            )

        return generate_question_paper(pyq_chunks, content_chunks, test_request, api_key, app_state=request.app.state)
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
    difficulty: str,
    topics: List[str],
    api_key: str,
    job_id: str
) -> Tuple[List[Dict], int, int]:
    """
    Generate a single batch of questions with validation and provenance tracking
    
    Returns:
        Tuple of (valid_questions, prompt_tokens, completion_tokens)
    """
    batch_id = f"{job_id}_batch_{batch_num}"
    logger.info(f"🔨 Generating batch {batch_num}: {num_questions} questions")
    
    try:
        # Get PYQ examples for style learning
        fewshot_examples, pattern_summary = generate_fewshot_examples(
            num_questions=num_questions,
            topics=topics,
            difficulty=difficulty,
            pyq_chunks=[]  # PYQ chunks already in main retrieval
        )
        
        # Prepare content from chunks
        from langchain_core.documents import Document
        content_docs = [Document(page_content=chunk['content'], metadata=chunk.get('metadata', {})) 
                       for chunk in chunks]
        
        content_text = deduplicate_chunks(content_docs, min_overlap_words=20, similarity_threshold=0.6)
        
        # Assemble prompt
        topic = topics[0] if topics else "Geography"
        user_prompt = assemble_upsc_prompt(
            topic=topic,
            difficulty=difficulty,
            num_questions=num_questions,
            retrieved_static_text=content_text,
            retrieved_current_affairs="",
            pyq_examples=fewshot_examples
        )
        
        # Call LLM
        client = OpenAI(api_key=api_key)
        
        # Model selection based on difficulty (cost optimization)
        if difficulty == "hard":
            model = settings.LLM_MODEL_LARGE  # GPT-4o for hard questions
        else:
            model = "gpt-4o-mini"  # Cheaper for easy/medium
        
        logger.info(f"   🤖 Using model: {model}")
        
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.85 if difficulty == "hard" else 0.7,
            max_tokens=min(4000, 500 * num_questions),
            response_format={"type": "json_object"}
        )
        
        response_text = completion.choices[0].message.content
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
        
        # Parse JSON response
        import json
        try:
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
        except json.JSONDecodeError as e:
            logger.error(f"❌ Batch {batch_num}: JSON parse error: {e}")
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
                model_used=model,
                prompt_tokens=prompt_tokens // max(len(valid_questions), 1),  # Approximate
                completion_tokens=completion_tokens // max(len(valid_questions), 1),
                total_cost=(prompt_tokens * 0.0000025 + completion_tokens * 0.00001) / max(len(valid_questions), 1),
                source_chunks=[{"content": c["content"][:200]} for c in chunks[:3]],
                source_domains=list(set(c.get("metadata", {}).get("major_domain", "General") for c in chunks)),
                pyq_examples_used=[],
                validation_passed=True,
                quality_score=quality_score,
                batch_id=batch_id,
                job_id=job_id,
                difficulty=difficulty,
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
    difficulty: str,
    topics: List[str],
    api_key: str,
    job_id: str,
    job_store
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
                difficulty=difficulty,
                topics=topics,
                api_key=api_key,
                job_id=job_id
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
    difficulty: str,
    topics: List[str],
    api_key: str,
    job_id: str,
    pinecone_handler
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
        query = build_query_text(min_domain, None, difficulty)
        gap_chunks = pinecone_handler.query_documents(
            query_text=query,
            k=max(5, gap // 2),
            filter_metadata={"major_domain": min_domain}
        )
    else:
        # No distribution info, use general retrieval
        gap_chunks = pinecone_handler.query_documents(
            query_text=build_query_text(None, None, difficulty),
            k=max(5, gap // 2)
        )
    
    # Generate gap-fill questions
    gap_questions, _, _ = await generate_single_batch(
        batch_num=999,  # Special batch number for gap-fill
        chunks=gap_chunks,
        num_questions=gap,
        difficulty=difficulty,
        topics=topics,
        api_key=api_key,
        job_id=job_id
    )
    
    logger.info(f"   ✅ Generated {len(gap_questions)} gap-fill questions")
    return gap_questions




async def _run_pipeline_with_error_handling(
    job_id: str,
    num_questions: int,
    topics: List[str],
    difficulty: str,
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
            difficulty=difficulty,
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
    difficulty: str,
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
                num_questions=num_questions,
                difficulty=difficulty
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
                difficulty=difficulty,
                topics=topics,
                api_key=api_key,
                job_id=job_id,
                job_store=job_store
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
                    difficulty=difficulty,
                    topics=topics,
                    api_key=api_key,
                    job_id=job_id,
                    pinecone_handler=pinecone_handler
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
                    "topics": topics,
                    "difficulty": difficulty
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
    try:
        # Validate request
        if test_request.num_questions > 200:
            raise HTTPException(400, "Maximum 200 questions allowed")
        
        # Create job
        job_id = str(uuid4())
        job_store = get_job_store()
        job_store.create_job(
            job_id=job_id,
            num_questions=test_request.num_questions,
            topics=test_request.topics,
            difficulty=test_request.difficulty
        )
        
        # Get dependencies
        pinecone_handler = request.app.state.vector_handler
        embedder = pinecone_handler.embedder
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise HTTPException(400, "OpenAI API key not configured")
        
        # Start background task using asyncio with error handling wrapper
        # Use ensure_future to get a task reference (prevents garbage collection)
        task = asyncio.ensure_future(
            _run_pipeline_with_error_handling(
                job_id=job_id,
                num_questions=test_request.num_questions,
                topics=test_request.topics,
                difficulty=test_request.difficulty,
                pinecone_handler=pinecone_handler,
                embedder=embedder,
                api_key=api_key
            )
        )
        
        # Log task creation
        logger.info(f"🎬 Created background task for job {job_id[:8]}, task_id={id(task)}")
        
        # Estimate time
        estimated_seconds = math.ceil(test_request.num_questions / 40) * 60  # ~60s per 40 questions
        
        logger.info(f"📋 Created async job {job_id} for {test_request.num_questions} questions")
        
        return {
            "job_id": job_id,
            "status": "pending",
            "estimated_time_seconds": estimated_seconds,
            "message": f"Generating {test_request.num_questions} questions. Poll /mock-test/status/{job_id} for progress."
        }
    
    except Exception as e:
        logger.error(f"❌ Failed to start async generation: {e}")
        raise HTTPException(500, str(e))


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Get status of async mock test generation
    """
    job_store = get_job_store()
    job = job_store.get_job(job_id)
    
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    
    # Cleanup old jobs
    job_store.cleanup_old_jobs()
    
    return job.to_dict()
