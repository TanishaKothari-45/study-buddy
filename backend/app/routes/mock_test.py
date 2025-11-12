"""
Mock test generation endpoint
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import os
import random
import logging
import time
from openai import OpenAI, RateLimitError

from ..core.config import settings
from ..utils.upsc_patterns.loader import get_examples, format_fewshot, get_all_patterns
from ..utils.metadata_enricher import GEOGRAPHY_TOPICS, GEOGRAPHY_DOMAINS
from ..routes.query import deduplicate_chunks
from ..utils.mm_utils import enforce_source_diversity
from ..utils.mock_test_prompting import assemble_upsc_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

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

def generate_fewshot_examples(num_questions: int = 5) -> tuple:
    """
    Generate diverse few-shot examples from ALL 6 PYQ patterns for style learning.
    
    Returns:
        Tuple of (fewshot_string, pattern_list) where pattern_list shows all available patterns
    """
    try:
        all_patterns = get_all_patterns()
        
        # CRITICAL: Get at least ONE example from EACH of the 6 patterns
        # This ensures the LLM sees all question types
        all_examples = []
        pattern_info = {}
        
        for pattern in all_patterns:
            # Get at least 1 example from each pattern
            pattern_examples = get_examples(topic=None, pattern=pattern["id"], n=2)
            if pattern_examples:
                # Take first example from each pattern
                example = pattern_examples[0]
                example["_pattern_id"] = pattern["id"]
                example["_pattern_title"] = pattern.get("title", "")
                example["_pattern_explanation"] = pattern.get("explanation", "")
                all_examples.append(example)
                pattern_info[pattern["id"]] = {
                    "title": pattern.get("title", ""),
                    "explanation": pattern.get("explanation", "")
                }
        
        # If we need more examples, get additional ones from random patterns
        if len(all_examples) < 6:
            # Fill up to 6 with random examples
            additional = get_examples(n=6 - len(all_examples))
            all_examples.extend(additional)
        
        # Format few-shot examples with clear pattern identification
        fewshot_parts = []
        for i, ex in enumerate(all_examples[:6], 1):  # Show all 6 patterns
            pattern_title = ex.get("_pattern_title", "UPSC Pattern")
            pattern_id = ex.get("_pattern_id", "")
            example_text = f"Example {i} - Pattern: {pattern_title} (ID: {pattern_id})\n"
            example_text += f"{ex['question']}\n"
            example_text += "\n".join(ex.get("options", [])) + f"\n✅ Correct Answer: ({ex['answer']})\n📘 Topic: {ex.get('topic', 'N/A')} (Year: {ex.get('year', 'N/A')})"
            fewshot_parts.append(example_text)
        
        fewshot = "\n\n---\n\n".join(fewshot_parts)
        
        # Create pattern summary for prompt
        pattern_summary = "\n".join([
            f"- {info['title']} ({pid}): {info['explanation'][:100]}..."
            for pid, info in pattern_info.items()
        ])
        
        logger.info(f"📚 Generated {len(all_examples)} few-shot examples covering {len(pattern_info)} patterns")
        return fewshot, pattern_summary
    except FileNotFoundError as e:
        logger.warning(f"⚠️ PYQ patterns file not found: {e}")
        return "", ""
    except Exception as e:
        logger.error(f"❌ Failed to generate few-shot examples: {e}")
        return "", ""

def generate_question_paper(pyq_chunks: List[Dict], content_chunks: List[Dict], 
                            request: MockTestRequest, api_key: str) -> MockTestResponse:
    """
    Generate UPSC-style mock test questions using few-shot PYQ examples + content knowledge.
    
    Cost Optimization Strategy:
    - Embeddings: Already using text-embedding-3-small (cheap)
    - Question Generation: Uses gpt-4o (large model) for quality
    - Other tasks (evaluation, query, etc.): Use gpt-4o-mini (small model)
    
    This balances cost (~90% tasks use mini) with quality (final questions use 4o).
    """
    # Generate diverse few-shot examples from ALL 6 patterns (style learning is universal)
    # Note: We don't filter by user topics here because any topic can use any question pattern
    # We ensure diversity by getting examples from ALL patterns
    fewshot_examples, pattern_summary = generate_fewshot_examples(
        num_questions=request.num_questions
    )
    
    # Prepare content context: Separate static and current affairs
    logger.info(f"📝 [MOCK_TEST] Preparing content context from {len(content_chunks)} chunks...")
    
    # Separate static and current affairs chunks
    static_chunks = []
    current_affairs_chunks = []
    
    for chunk in content_chunks:
        meta = chunk.get("metadata", {})
        source_type = meta.get("source_type", "").lower()
        filename = meta.get("filename", "").lower()
        
        # Check source_type first, then fallback to filename
        if source_type == "current_affairs" or "current" in filename or "2025" in filename:
            current_affairs_chunks.append(chunk)
        else:
            static_chunks.append(chunk)
    
    # Deduplicate static chunks
    static_text = ""
    if static_chunks:
        static_docs_for_dedup = []
        for chunk in static_chunks[:8]:
            from langchain_core.documents import Document
            static_docs_for_dedup.append(Document(
                page_content=chunk['content'],
                metadata=chunk.get('metadata', {})
            ))
        
        if static_docs_for_dedup:
            deduplicated_static = deduplicate_chunks(static_docs_for_dedup, min_overlap_words=20, similarity_threshold=0.6)
            static_text = deduplicated_static
            logger.info(f"   ✅ Prepared {len(static_chunks)} static chunks (deduplicated)")
        else:
            static_text = "\n\n".join([chunk['content'] for chunk in static_chunks[:8]])
    
    # Prepare current affairs text
    current_affairs_text = ""
    if current_affairs_chunks:
        current_affairs_text = "\n\n".join([chunk['content'] for chunk in current_affairs_chunks[:5]])
        logger.info(f"   ✅ Prepared {len(current_affairs_chunks)} current affairs chunks")
    
    # Prepare PYQ examples
    pyq_examples_text = fewshot_examples if fewshot_examples else "\n\n---\n\n".join([chunk["content"] for chunk in pyq_chunks[:8]])
    
    # Extract topic from request (use first topic or "Geography" as default)
    topic = request.topics[0] if request.topics else "Geography"
    
    logger.info(f"📚 Using {len(static_chunks)} static chunks and {len(current_affairs_chunks)} current affairs chunks")
    if fewshot_examples:
        logger.info(f"✅ Using few-shot PYQ examples for style learning")
    else:
        logger.warning("⚠️ No few-shot examples available, using retrieved PYQ chunks")
    
    # Use new prompt system
    try:
        # Assemble prompt using new system
        user_prompt = assemble_upsc_prompt(
            topic=topic,
            difficulty=request.difficulty,
            num_questions=request.num_questions,
            retrieved_static_text=static_text,
            retrieved_current_affairs=current_affairs_text,
            pyq_examples=pyq_examples_text
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
                
                question = MockTestQuestion(
                    question=q_data.get("question", f"Question {i+1}"),
                    options=options_list,
                    correct_answer=q_data.get("correct_answer", "A"),
                    explanation=q_data.get("explanation", "No explanation provided"),
                    source={"filename": "Generated", "chapter": "Mock Test", "section": f"Question {i+1}"}
                )
                questions.append(question)
        
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
    num_questions: int = 10
) -> Tuple[List[Dict], List[Dict]]:
    """
    Hybrid retrieval using source_type metadata filters for cleaner, more accurate retrieval.
    
    This function implements:
    1. PYQ retrieval using source_type="pyq" filter (for style learning)
    2. Concept retrieval using source_type="concept" filter (for content knowledge)
    3. Current affairs retrieval using source_type="current_affairs" filter (semantically related to concepts)
    4. Source diversity enforcement using enforce_source_diversity
    5. Final MMR re-ranking for cross-source diversity
    
    Args:
        pinecone_handler: PineconeHandler instance
        topics: List of topics (sub-domains or major domains from dropdowns)
        num_questions: Number of questions to generate (for context sizing)
    
    Returns:
        Tuple of (pyq_chunks, content_chunks) ready for question generation
    """
    # Extract domains from topics
    major_domain, sub_domain = extract_domains_from_topics(topics)
    
    logger.info(f"🎯 [HYBRID_RETRIEVE] Starting retrieval: major_domain={major_domain}, sub_domain={sub_domain}")
    
    # Build query based on domain granularity
    if sub_domain:
        query = f"{sub_domain} geography concepts NCERT vision notes important topics"
        k_target = 10
        lambda_mult = 0.65
        logger.info(f"   🎯 Sub-domain mode: focusing on micro-topics within {sub_domain}")
    elif major_domain:
        query = f"{major_domain} major subtopics theories NCERT vision notes"
        k_target = 10
        lambda_mult = 0.65
        logger.info(f"   🎯 Major-domain mode: diversifying across sub-domains in {major_domain}")
    else:
        query = "important geography topics for UPSC NCERT vision notes static and current"
        k_target = 12
        lambda_mult = 0.6
        logger.info(f"   🎯 General mode: broad coverage")
    
    # ================================
    # 1️⃣ Conceptual Base Retrieval (source_type="concept")
    # ================================
    # Flow: Pinecone vector search → get chunk_ids → enrich from local DB (content store)
    logger.info("📘 Retrieving conceptual chunks (source_type='concept')...")
    logger.info("   🔍 Step 1: Querying Pinecone vectorstore for similar embeddings...")
    try:
        concept_chunks = pinecone_handler.query_documents(
            query_text=query,
            k=10,
            filter_metadata={"source_type": "concept"},
            use_content_store=True  # Enriches with full content from local DB using chunk_ids
        )
        logger.info(f"   ✅ Retrieved {len(concept_chunks)} concept chunks (enriched from content store)")
    except Exception as e:
        logger.warning(f"⚠️ Concept retrieval failed: {e}")
        concept_chunks = []
    
    # ================================
    # 2️⃣ PYQ Retrieval for Style (source_type="pyq")
    # ================================
    # Flow: Pinecone vector search → get chunk_ids → enrich from local DB (content store)
    logger.info("📝 Retrieving PYQ chunks (source_type='pyq') for style reference...")
    logger.info("   🔍 Step 1: Querying Pinecone vectorstore for similar embeddings...")
    try:
        pyq_chunks = pinecone_handler.query_documents(
            query_text=query,
            k=5,
            filter_metadata={"source_type": "pyq"},
            use_content_store=True  # Enriches with full content from local DB using chunk_ids
        )
        logger.info(f"   ✅ Retrieved {len(pyq_chunks)} PYQ chunks (enriched from content store)")
    except Exception as e:
        logger.warning(f"⚠️ PYQ retrieval failed: {e}")
        pyq_chunks = []
    
    # ================================
    # 3️⃣ Current Affairs Overlay (Semantically Related to Concept)
    # ================================
    # Flow: For each concept chunk → Pinecone vector search → get chunk_ids → enrich from local DB
    logger.info("🗞️ Retrieving current affairs chunks (source_type='current_affairs')...")
    logger.info("   🔍 Querying Pinecone for semantically related current affairs...")
    current_chunks = []
    try:
        # For each concept chunk, find semantically related current affairs
        for chunk in concept_chunks[:5]:  # Limit to first 5 to avoid too many queries
            topic_text = chunk["content"][:250]
            try:
                matches = pinecone_handler.query_documents(
                    query_text=topic_text,
                    k=2,
                    filter_metadata={"source_type": "current_affairs"},
                    use_content_store=True  # Enriches with full content from local DB using chunk_ids
                )
                current_chunks.extend(matches)
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
        
        logger.info(f"   ✅ Retrieved {len(current_chunks)} current affairs chunks")
    except Exception as e:
        logger.warning(f"⚠️ Current affairs retrieval failed: {e}")
        current_chunks = []
    
    # ================================
    # 4️⃣ Combine and Apply Source Diversity
    # ================================
    all_chunks = pyq_chunks + concept_chunks + current_chunks
    logger.info(f"📊 Combined chunks: {len(pyq_chunks)} PYQ + {len(concept_chunks)} concept + {len(current_chunks)} current affairs = {len(all_chunks)} total")
    
    # Apply source diversity v2 (enforces diversity across source types and files)
    diverse_chunks = enforce_source_diversity(
        all_chunks,
    total_target=15,
    source_weights={"pyq": 0.2, "current_affairs": 0.3, "concept": 0.5},
    concept_subweights={"ncert": 0.25, "topic": 0.25},
    max_per_file=2
    )
    
    # ================================
    # 5️⃣ Final MMR Re-ranking
    # ================================
    logger.info("🔄 Applying final MMR re-ranking...")
    if diverse_chunks:
        final_context = pinecone_handler.mmr_select_from_chunks(
            chunks=diverse_chunks,
            query_text=query,
            k=min(15, len(diverse_chunks)),
            lambda_mult=lambda_mult
        )
    else:
        final_context = diverse_chunks
    
    # ================================
    # 6️⃣ Separate Back into PYQ and Content
    # ================================
    pyq_final = [c for c in final_context if c.get("metadata", {}).get("source_type") == "pyq"]
    content_final = [
        c for c in final_context 
        if c.get("metadata", {}).get("source_type") in ["concept", "current_affairs"]
    ]
    
    # Fallback: if we don't have enough after filtering, use original chunks
    if len(pyq_final) < 2 and pyq_chunks:
        logger.warning(f"⚠️ Only {len(pyq_final)} PYQ chunks after filtering, using original")
        pyq_final = pyq_chunks[:5]
    
    if len(content_final) < 3 and concept_chunks:
        logger.warning(f"⚠️ Only {len(content_final)} content chunks after filtering, using original")
        content_final = concept_chunks[:8] + current_chunks[:2]
    
    logger.info(f"📊 Final selection: {len(pyq_final)} PYQ chunks and {len(content_final)} content chunks")
    
    return pyq_final, content_final

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
            num_questions=test_request.num_questions
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

        return generate_question_paper(pyq_chunks, content_chunks, test_request, api_key)
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


