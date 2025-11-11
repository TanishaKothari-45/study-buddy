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

logger = logging.getLogger(__name__)
router = APIRouter()

# Difficulty guide for prompt optimization
DIFFICULTY_GUIDE = {
    "easy": """
 UPSC EASY MODE (Foundation Level)

1. **Concept Focus**
   - One concept per question (e.g., “Weathering” or “Latitude”).
   - Use clear, direct factual statements — no integration.

2. **Option Simplicity**
   - Only 1–2 options should seem plausible.
   - Avoid traps like “only” or “none”.

3. **Single-Domain Coverage**
   - Use pure NCERT-based physical geography or basic human geography.
   - Avoid linking multiple domains.

4. **Explanation Style**
   - Short, one-line factual justification.
   - “Statement 1 is correct because… as per NCERT Class IX, Ch. 2.”

5. **Weightage**
   - 60% Factual | 30% Conceptual | 10% Analytical

6. **Question Framing**
   - Use “Which of the following is correct?” or “Identify the correct pair.”
   - Avoid “NOT correct” or Assertion–Reason type.

""",
    
    "medium": """
⚖️ UPSC MEDIUM MODE (Mainstream UPSC Style)

1. **Balanced Integration**
   - Blend 1–2 subtopics (e.g., Climatology + Indian Monsoon).

2. **Moderate Confusion**
   - 2 options should seem correct.
   - Include one question with "NOT correct" phrasing.

3. **Realistic Cross-Linking**
   - Static + applied concept (e.g., “Monsoon variability and agriculture”).

4. **Explanation Depth**
   - 2-line reasoning — why correct, why others wrong.

5. **Weightage**
   - 40% Conceptual | 40% Analytical | 20% Factual

6. **Question Types**
   - Include “Consider the following statements”, “Match the following”, and one Assertion–Reason type.

""",

    "hard": """
  UPSC HARD MODE (Advanced / Vision IAS Level)

1. **Conceptual Depth**
   - Combine 2–3 subtopics logically (e.g., Climatology + Agriculture, Oceanography + Environment).
   - Questions should test *applied understanding*, not direct recall.

2. **Option Confusion (UPSC Traps)**
   - At least 3 options should sound correct at first glance.
   - Include factual reversals and keywords like "only", "always", "none", or "correctly matched".
   - Avoid obviously wrong distractors.

3. **Cross-domain Integration**
   - Blend physical, human, and environmental geography.
   - Example: "How geomorphology influences settlement distribution" or "Impact of monsoon variability on agriculture".

4. **Explanation Style (Vision IAS Format)**
   - Each explanation must include:
     • Why the correct option is right  
     • Why each other option is wrong  
     • Reference to NCERT / Vision IAS concept or factual base

5. **Difficulty Weightage**
   - 30% Conceptual → understanding cause–effect  
   - 40% Analytical → compare statements, eliminate options  
   - 30% Factual → static UPSC facts with traps

6. **Advanced UPSC Traps**
   - Include at least one “NOT correct” or “incorrect statement” type question.
   - Keep questions precise, multi-layered, and test elimination ability.
   - Use indirect phrasing like “Which of the following best explains…” or “How many of the above are correct?”

"""
}

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
    
    # Prepare content context with explicit markers for Current Affairs vs Static Material
    # Deduplicate overlapping text before combining
    logger.info(f"📝 [MOCK_TEST] Removing overlapping text from content chunks...")
    content_docs_for_dedup = []
    for chunk in content_chunks[:8]:
        from langchain_core.documents import Document
        content_docs_for_dedup.append(Document(
            page_content=chunk['content'],
            metadata=chunk.get('metadata', {})
        ))
    
    # Deduplicate content chunks
    if content_docs_for_dedup:
        original_content_length = sum(len(doc.page_content) for doc in content_docs_for_dedup)
        deduplicated_content = deduplicate_chunks(content_docs_for_dedup, min_overlap_words=20, similarity_threshold=0.6)
        overlap_removed = original_content_length - len(deduplicated_content)
        if overlap_removed > 0:
            logger.info(f"   ✅ Removed {overlap_removed} chars (~{overlap_removed//4} tokens) of overlap from content chunks")
        
        # Mark content based on first chunk's metadata
        context_knowledge_parts = []
        if content_chunks:
            first_meta = content_chunks[0].get("metadata", {})
            filename = first_meta.get("filename", "").lower()
            if "current" in filename or "2025" in filename:
                context_knowledge_parts.append(f"🗞️ [CURRENT AFFAIRS CONTEXT]: {deduplicated_content}")
            else:
                context_knowledge_parts.append(f"📘 [STATIC MATERIAL]: {deduplicated_content}")
        context_knowledge = "\n\n".join(context_knowledge_parts)
    else:
        # Fallback: use original chunks if deduplication fails
        context_knowledge_parts = []
        for chunk in content_chunks[:8]:
            meta = chunk.get("metadata", {})
            filename = meta.get("filename", "").lower()
            if "current" in filename or "2025" in filename:
                context_knowledge_parts.append(f"🗞️ [CURRENT AFFAIRS CONTEXT]: {chunk['content']}")
            else:
                context_knowledge_parts.append(f"📘 [STATIC MATERIAL]: {chunk['content']}")
        context_knowledge = "\n\n".join(context_knowledge_parts)
    
    # Fallback: prepare retrieved PYQ chunks if few-shot not available
    context_style = "\n\n---\n\n".join([chunk["content"] for chunk in pyq_chunks[:8]]) if not fewshot_examples else ""
    
    # If pattern_summary is empty, create a default one
    if not pattern_summary:
        pattern_summary = """- Q1: Concept Definition / Single-Choice - Tests conceptual understanding
- Q2: Multi-Statement Evaluation - Uses "Consider the following statements"
- Q3: Match-the-Pair Questions - Two-column matching (River-Origin, etc.)
- Q4: Assertion-Reason Type - Statement-I and Statement-II format
- Q5: Fact-Based / Direct MCQ - Tests static geographical facts
- Q6: Map / Location / Identification - Tests spatial knowledge"""
    
    logger.info(f"📚 Using {len(content_chunks[:8])} content chunks for knowledge")
    if fewshot_examples:
        logger.info(f"✅ Using few-shot PYQ examples covering all 6 patterns for style learning")
    else:
        logger.warning("⚠️ No few-shot examples available, using retrieved PYQ chunks")
    
    # Enhanced system prompt - concise and structured
    system_prompt = """You are a senior UPSC Prelims Question Setter specializing in Geography.

🎯 GOAL:

Create realistic, UPSC-grade multiple-choice questions based on:

- UPSC PYQs (for style reference)

- Uploaded study material (NCERTs, Vision IAS, Current Affairs)

- Specified difficulty level

Your output must be indistinguishable from authentic UPSC questions.

---

🧩 STYLE LEARNING (FEW-SHOT REFERENCE):

You will study real UPSC PYQs provided below and replicate their:

- Question phrasing ("Which of the following...", "Consider the following...")

- Option style ("1 and 2 only", "All of the above", "None of the above")

- Confusion balance (2–3 plausible distractors)

- Explanation tone (Vision IAS format)

---

DIVERSITY FRAMEWORK FOR QUESTION GENERATION : Ensure that in every test there is topic diversity and in every topic there is diversity in the type of questions.

When generating questions, maintain diversity along these five semantic dimensions:

1. **Conceptual Diversity**
   - Each question must test a different *conceptual type*: definition, mechanism, cause-effect, implication, or application.
   - Example: If one question asks "what is", the next must ask "why" or "how" about a different concept.

2. **Contextual Diversity**
   - Vary the *spatial*, *temporal*, or *domain context*.
   - Example: If one question is India-specific, another should use global or historical context.

3. **Analytical Diversity**
   - Mix factual recall with analytical reasoning.

4. **Topical Breadth**
   - Avoid repeating the same factual entity, keyword, or event across questions.
   - Each question must anchor in a different concept or factual base — even within the same topic.
   - For example, for "Monsoon": one on its mechanism, one on variability, one on human impact.

5. **Current Relevance Integration**
   - If current-affairs materials are available, integrate *1–2 questions* that link a static concept with a recent event or policy.
   - Example: link "Cyclone formation" with a recent IMD report or real cyclone event.

 CHECKLIST BEFORE OUTPUT:

- Each question covers a different combination of conceptual + contextual + analytical dimensions.
- No two questions repeat the same keyword or factual entity (unless testing different aspects).
- If user selected a topic, questions explore its sub-concepts rather than repeat the same one.

---

🗞️ CURRENT AFFAIRS INTEGRATION:

When relevant content (filename or metadata containing "current" or "2025") overlaps with the topic:

   - Blend static + dynamic info naturally.

   - Example: "Recently, Cyclone Remal affected India's east coast. Consider the following statements about tropical cyclones..."

   - Use max 1–2 such questions per paper.

   - Avoid specific dates; use "Recently" or "In recent years".

🧩 CONTEXT MARKERS:

- Text starting with "🗞️ [CURRENT AFFAIRS CONTEXT]" is from recent events (e.g., 2025).

- Text starting with "📘 [STATIC MATERIAL]" is from standard study sources (NCERT, Vision Notes).

When forming questions:

1. Prefer static sources for factual base.

2. When current affairs context matches the static topic, combine both.

3. Begin such questions with "Recently…" or include one statement from the current event.

4. Do not force current affairs; only use if relevant by subject.

---

⚙️ STRUCTURE REQUIREMENTS:

Each question must:

- Follow a unique UPSC pattern (Multi-Statement, Assertion–Reason, Match-the-Pair, Concept, Fact-based, or Map-based).

- Be formatted as:

  {{
    "question": "...",
    "options": ["(a)...", "(b)...", "(c)...", "(d)..."],
    "correct_answer": "A" | "B" | "C" | "D",
    "explanation": "...",
    "source": {{...}}
  }}

- Use at least 4 different patterns per paper.

- Maintain exact UPSC tone and conciseness.

---

✅ FINAL VERIFICATION CHECKLIST:

- [ ] Includes Q2 (Multi-Statement), Q4 (Assertion–Reason), Q3 (Match-the-Pair)

- [ ] At least 4 unique patterns used

- [ ] 2–3 plausible distractors per question

- [ ] One question uses "NOT correct"

- [ ] 1–2 questions integrate Current Affairs

- [ ] Each explanation justifies correct and incorrect options

- [ ] Each question tests a different conceptual type (definition vs mechanism vs application)

- [ ] No two questions repeat the same keyword/factual entity (unless testing different aspects)

- [ ] Questions vary in spatial/temporal context (India vs global, current vs historical)

IMPORTANT: The "options" field must be a JSON array of strings, not a dictionary.
Example: "options": ["(a) Option 1", "(b) Option 2", "(c) Option 3", "(d) Option 4"]
NOT: "options": {{"A": "Option 1", "B": "Option 2"}}
    """

    try:
        # Get difficulty guide text (default to medium if not found)
        difficulty_text = DIFFICULTY_GUIDE.get(
            request.difficulty.lower(), 
            DIFFICULTY_GUIDE["medium"]
        )
        
        # Pattern plan injection - fixed skeleton for better pattern diversity
        # This gives the LLM a fixed skeleton, making it 10× more likely to follow pattern diversity precisely
        pattern_plan = [
            "Q1: Multi-Statement Evaluation",
            "Q2: Assertion–Reason Type",
            "Q3: Match-the-Pair",
            "Q4: Concept Definition",
            "Q5: Current-Affairs-Integrated Question"
        ]
        # Use pattern plan for first 5 questions, then let LLM vary for remaining
        pattern_instructions = "\n".join([f"- {p}" for p in pattern_plan[:min(5, request.num_questions)]])
        
        client = OpenAI(api_key=api_key)
        # Use large model (gpt-4o) for final question generation - this is the critical quality step
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL_LARGE,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""🧩 UPSC PYQ Style References (Few-shot examples):

{fewshot_examples if fewshot_examples else context_style}

---

📚 Study Material for Content (NCERTs, Vision, Current Affairs):

{context_knowledge}

---

🧠 Pattern Plan for this test:
{pattern_instructions}

🧠 DIFFICULTY MODE INSTRUCTIONS:
{difficulty_text}

Generate {request.num_questions} UPSC Prelims-style MCQs following all the rules above.

Return ONLY valid JSON in this structure:

{{
  "questions": [
    {{
      "question": "...",
      "options": ["(a)...", "(b)...", "(c)...", "(d)..."],
      "correct_answer": "A",
      "explanation": "...",
      "source": {{"topic": "...", "sub_domain": "..."}}
    }}
  ]
}}"""}
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

def filter_chunks_by_topic(chunks: List[Dict], topics: Optional[List[str]] = None) -> List[Dict]:
    """
    Filter chunks by topic using metadata (major_domain/sub_domain).
    If no topics provided, returns all chunks.
    """
    if not topics:
        return chunks
    
    domain_mapping = map_topics_to_domains(topics)
    major_domains = domain_mapping["major_domains"]
    sub_domains = domain_mapping["sub_domains"]
    
    filtered = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        chunk_major = metadata.get("major_domain", "")
        chunk_sub = metadata.get("sub_domain", "")
        
        # Match if major_domain or sub_domain matches
        if chunk_major in major_domains or chunk_sub in sub_domains:
            filtered.append(chunk)
        # Also include if any topic keyword appears in metadata
        elif any(topic.lower() in str(metadata).lower() for topic in topics):
            filtered.append(chunk)
    
    return filtered

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
    Hybrid retrieval with progressive fallback, source diversity, and domain-aware strategies.
    
    This function implements:
    1. Progressive fallback for PYQ retrieval (sub-domain → major-domain → general)
    2. Domain-aware content retrieval with different strategies based on granularity
    3. Source diversity enforcement (max 2 chunks per file)
    4. Final MMR re-ranking for cross-source diversity
    
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
    
    # ================================
    # 1️⃣ Progressive PYQ Retrieval (Style Learning)
    # ================================
    pyq_chunks = []
    
    def retrieve_pyqs(query_text: str, k: int = 5):
        """Helper to retrieve and filter PYQ chunks"""
        try:
            retriever = pinecone_handler.get_retriever_for_mode("prelims", use_content_store=True)
            if hasattr(retriever, 'invoke'):
                docs = retriever.invoke(query_text)
            else:
                docs = retriever.get_relevant_documents(query_text)
            
            # Convert to chunk format
            chunks = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
            
            # Filter: PYQ files + actual questions
            pyq_file_chunks = [c for c in chunks if is_pyq_chunk(c)]
            pyq_question_chunks = [c for c in pyq_file_chunks if is_actual_question_chunk(c)]
            
            # Prefer actual questions, fallback to all PYQ chunks
            return pyq_question_chunks if pyq_question_chunks else pyq_file_chunks[:k]
        except Exception as e:
            logger.warning(f"⚠️ PYQ retrieval failed for '{query_text}': {e}")
            return []
    
    # Progressive fallback: sub-domain → major-domain → general
    # Goal: Ensure at least 5 PYQ chunks for stylistic variation
    TARGET_PYQ_CHUNKS = 5
    
    if sub_domain:
        logger.info(f"   🔍 Retrieving PYQs for sub-domain: {sub_domain}")
        retrieved = retrieve_pyqs(f"UPSC prelims geography questions {sub_domain} which of the following consider")
        pyq_chunks.extend(retrieved)
        logger.info(f"      → Got {len(retrieved)} chunks from sub-domain search (total: {len(pyq_chunks)})")
    
    # Deduplicate after each step to avoid counting duplicates
    seen_content = set()
    unique_pyq_chunks = []
    for chunk in pyq_chunks:
        content_hash = hash(chunk["content"][:100])  # Use first 100 chars as hash
        if content_hash not in seen_content:
            seen_content.add(content_hash)
            unique_pyq_chunks.append(chunk)
    pyq_chunks = unique_pyq_chunks
    
    # If we don't have enough, try major-domain
    if len(pyq_chunks) < TARGET_PYQ_CHUNKS and major_domain:
        logger.info(f"   🔍 Retrieving PYQs for major-domain: {major_domain} (need {TARGET_PYQ_CHUNKS - len(pyq_chunks)} more)")
        retrieved = retrieve_pyqs(f"UPSC prelims geography questions {major_domain} which of the following consider")
        # Add only new chunks
        for chunk in retrieved:
            content_hash = hash(chunk["content"][:100])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                pyq_chunks.append(chunk)
        logger.info(f"      → Got {len(retrieved)} chunks from major-domain search (total: {len(pyq_chunks)})")
    
    # If still not enough, try general PYQ retrieval
    if len(pyq_chunks) < TARGET_PYQ_CHUNKS:
        logger.info(f"   🔍 Retrieving general PYQs (fallback, need {TARGET_PYQ_CHUNKS - len(pyq_chunks)} more)")
        retrieved = retrieve_pyqs("UPSC prelims geography questions which of the following consider select")
        # Add only new chunks
        for chunk in retrieved:
            content_hash = hash(chunk["content"][:100])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                pyq_chunks.append(chunk)
        logger.info(f"      → Got {len(retrieved)} chunks from general search (total: {len(pyq_chunks)})")
    
    # Limit to reasonable max but ensure we have at least what we got (up to 8 for prompt focus)
    pyq_chunks = pyq_chunks[:8]  # Upper limit for prompt focus
    logger.info(f"✅ Retrieved {len(pyq_chunks)} PYQ chunks for style reference (target was {TARGET_PYQ_CHUNKS})")
    
    # ================================
    # 2️⃣ Domain-Aware Content Retrieval (Knowledge)
    # ================================
    logger.info("📘 Retrieving factual content chunks...")
    
    # Adjust retrieval strategy based on granularity
    if sub_domain:
        # Micro-topic diversity under sub-domain
        query = f"{sub_domain} geography concepts NCERT vision notes important topics"
        k_target = 10
        lambda_mult = 0.65
        logger.info(f"   🎯 Sub-domain mode: focusing on micro-topics within {sub_domain}")
    elif major_domain:
        # Diversify across sub-domains within major domain
        query = f"{major_domain} major subtopics theories NCERT vision notes"
        k_target = 10
        lambda_mult = 0.65
        logger.info(f"   🎯 Major-domain mode: diversifying across sub-domains in {major_domain}")
    else:
        # Very general query → broad coverage
        query = "important geography topics for UPSC NCERT vision notes static and current"
        k_target = 12
        lambda_mult = 0.6
        logger.info(f"   🎯 General mode: broad coverage")
    
    try:
        content_retriever = pinecone_handler.get_retriever_for_mode("prelims", use_content_store=True)
        if hasattr(content_retriever, 'invoke'):
            content_docs = content_retriever.invoke(query)
        else:
            content_docs = content_retriever.get_relevant_documents(query)
    except Exception as e:
        logger.warning(f"⚠️ Content retrieval failed: {e}")
        content_docs = []
    
    # Convert to chunk format and filter out PYQ files
    content_chunks = [
        {"content": doc.page_content, "metadata": doc.metadata}
        for doc in content_docs
        if not is_pyq_chunk({"metadata": doc.metadata})
    ]
    
    # Apply source diversity enforcement (max 2 chunks per file)
    content_chunks = enforce_source_diversity(content_chunks, max_per_file=2)
    
    logger.info(f"✅ Retrieved {len(content_chunks)} content chunks for factual grounding")
    
    # ================================
    # 3️⃣ Tag Chunks with Source Metadata
    # ================================
    for chunk in pyq_chunks:
        if "metadata" not in chunk:
            chunk["metadata"] = {}
        chunk["metadata"]["source"] = "pyq"
    
    for chunk in content_chunks:
        if "metadata" not in chunk:
            chunk["metadata"] = {}
        chunk["metadata"]["source"] = "content"
    
    # ================================
    # 4️⃣ Final MMR Re-ranking for Cross-Source Diversity
    # ================================
    logger.info("🔄 Applying final cross-source MMR diversity selection...")
    combined_chunks = pyq_chunks + content_chunks
    
    if combined_chunks:
        # Create combined query for MMR relevance calculation
        combined_query = query if query else "UPSC Geography important topics"
        
        diverse_chunks = pinecone_handler.mmr_select_from_chunks(
            chunks=combined_chunks,
            query_text=combined_query,
            k=min(k_target + 2, len(combined_chunks)),  # +2 to ensure we have enough after separation
            lambda_mult=lambda_mult
        )
        
        # Separate back into PYQ and content using source metadata
        diverse_pyq_chunks = [c for c in diverse_chunks if c.get("metadata", {}).get("source") == "pyq"]
        diverse_content_chunks = [c for c in diverse_chunks if c.get("metadata", {}).get("source") == "content"]
        
        # Use diverse chunks, but fallback to original if MMR didn't preserve enough
        if len(diverse_pyq_chunks) >= 2:
            pyq_chunks = diverse_pyq_chunks
        else:
            logger.warning(f"⚠️ MMR didn't preserve enough PYQ chunks ({len(diverse_pyq_chunks)}), using original")
        
        if len(diverse_content_chunks) >= 3:
            content_chunks = diverse_content_chunks
        else:
            logger.warning(f"⚠️ MMR didn't preserve enough content chunks ({len(diverse_content_chunks)}), using original")
    
    logger.info(f"📊 Final selection: {len(pyq_chunks)} PYQ chunks and {len(content_chunks)} content chunks")
    
    return pyq_chunks, content_chunks

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

def filter_chunks_by_topic(chunks: List[Dict], topics: Optional[List[str]] = None) -> List[Dict]:
    """
    Filter chunks by topic using metadata (major_domain/sub_domain).
    If no topics provided, returns all chunks.
    """
    if not topics:
        return chunks
    
    domain_mapping = map_topics_to_domains(topics)
    major_domains = domain_mapping["major_domains"]
    sub_domains = domain_mapping["sub_domains"]
    
    if not major_domains and not sub_domains:
        # No mapping found, return all chunks
        return chunks
    
    filtered = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        chunk_major = metadata.get("major_domain", "")
        chunk_sub = metadata.get("sub_domain", "")
        
        # Check if chunk matches any mapped domain/subdomain
        matches = False
        if major_domains and chunk_major in major_domains:
            matches = True
        if sub_domains and chunk_sub in sub_domains:
            matches = True
        
        if matches:
            filtered.append(chunk)
    
    # If filtering resulted in too few chunks, return original
    if len(filtered) < 2 and len(chunks) > 5:
        logger.warning(f"⚠️ Topic filtering too strict ({len(filtered)} chunks), using all chunks")
        return chunks
    
    logger.info(f"📊 Filtered {len(chunks)} → {len(filtered)} chunks by topic")
    return filtered

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


