"""
evaluate_answer.py

Evaluation pipeline using Gemini's built-in OCR with context retrieval and current affairs.

Flow:
  1) Upload answer (PDF/image) -> Gemini extracts question (OCR)
  2) Parse question -> extract search terms for vector retrieval
  3) Retrieve relevant context from Pinecone/SQLite
  4) Fetch current affairs using parsed keywords
  5) Gemini improves answer with context + current affairs + system prompt
  6) Returns improved answer

Usage:
  POST /evaluate-answer/
  - file: PDF or image file (required)
  - question: Question text (optional, Gemini can identify from answer)
  - word_count: Target word count (default: 350)
"""

import os
import logging
import tempfile
from typing import Optional
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# Import Gemini client
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

# Import utilities
try:
    from ..utils.question_parser import parse_question_for_search
    from ..utils.context_retriever import retrieve_context_for_question
    from ..utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
except ImportError as e:
    parse_question_for_search = None
    retrieve_context_for_question = None
    fetch_current_affairs_for_question = None
    format_bullets_for_context = None
    logger.warning(f"Could not import utilities: {e}")

# System prompt for answer improvement - uses mains_prompt.py structure
ANSWER_IMPROVEMENT_SYSTEM_PROMPT = """You are an expert UPSC Geography teacher, evaluator and answer-writing coach.

Your task is to read a student's handwritten answer and provide an improved version using the provided reference context.

**RULE 1 - PRESERVE STUDENT'S VOICE (MOST IMPORTANT)**:
Build on the student's original points and ideas. EDIT (rephrase, reorganize, modify, add, remove, tidy) rather than rewrite from scratch. Keep their unique perspective and examples where valid.

**RULE 2 - USE REFERENCE CONTEXT**:
Use the provided REFERENCE CONTEXT to:
- Add relevant facts, data, and examples that support the student's points
- Fill gaps in the student's answer with accurate information
- Substantiate claims with named reports/indices/data from the context
- Do NOT copy verbatim; integrate naturally into the student's answer

**RULE 3 - DIRECTIVE INTERPRETATION**:
Directive -> structure (mandatory):
- Comment = take a stance & justify (if 'critically' → both sides)
- Examine = causes / implications / way forward
- Critically examine = strengths + weaknesses separately, then implications
- Discuss = broad overview → positives / negatives / causes / consequences
- Discuss critically = same as discuss but more rigorous reasoning
- Evaluate = assess worthiness → positives / negatives → give verdict
- Critically evaluate = evaluate + explicit judgement and trade-offs
- Analyse = break the topic into sub-parts and examine each dimension
- Explain = clarify how/why something is
- Elucidate = make clear using examples/data
- Elaborate = expand the core idea by adding layers of reasoning
- Substantiate = assert then support with evidence/reports/data
- To what extent = give a balanced graded judgement (fully/partly/marginally)

**RULE 4 - COGNITIVE FRAMEWORK**:
1) Concept Focus: Base each question/answer on ONE core concept or mechanism.
2) Context Variation: Vary spatial (India/global), temporal (current/historical), domain (physical/human/environmental) perspectives.
3) Body Organization: Use sub-headings (physical / economic / social / environmental / policy / Governance / Vulnerability / Human angle).
4) Point Discipline: Each important point must be supported with a named index/report/data/example.
5) Global bodies and conferences: Mention at least one global body or conference related agreement before conclusion.
6) Human Angle: Mandatory human impacts even for physical geography.
7) Diagram discipline: At least ONE inline diagram suggestion inside body (explicit).

**RULE 5 - IBC FORMAT**:
- INTRO: 2-3 lines. Must include either a definition, a data point/report citation, or a recent context or current affair (if applicable).
- BODY: Use sub-headings and bullets. Each bullet <= 18 words. Main idea (≤ 10-12 words) — Evidence (report/data/index) — Example (India OR World). Insert at least one inline diagram suggestion exactly where relevant e.g. "(Suggested Diagram: India map showing X, flowcharts, maps, pie charts, timelines, or comparative tables.)"
- CONCLUSION: 1 para with global best practices + SDG + policy angle.

**RULE 6 - WORD LIMIT COMPRESSION** (when word_count <= 250):
1) MUST preserve IBC structure but reduce density:
   - Introduction: 2 lines  
   - Body: 2-3 sub-headings, each with 1-2 bullets  
   - Conclusion: 1 line  
2) Compress bullets to: Main idea (≤ 7-9 words) — Evidence (short: "IPCC 2023") — Example (single phrase).
3) Max 2 bullets per sub-heading, max 3 sub-headings in Body.

**RULE 7 - FACTUAL ACCURACY**:
- Prefer facts from the REFERENCE CONTEXT provided.
- If you add a fact from the context, it's already verified.
- If a fact is necessary but not in context or student's answer, insert "[citation needed]".

**RULE 8 - OUTPUT FORMAT**:
- Return ONLY the improved answer text (no JSON, no metadata, no commentary).
- Use markdown for formatting (headings, bullets).
- Every single bullet MUST contain: (a) One evidence (report/index/data), (b) One example (named Indian OR named global), (c) Maximum 18 words total.
"""


@router.post("/")
async def evaluate_answer_endpoint(
    request: Request,
    file: UploadFile = File(...),
    question: Optional[str] = Form(default=None),
    word_count: Optional[str] = Form(default="350")
):
    """
    Evaluate and improve student answer using Gemini with context retrieval and current affairs.
    
    Flow:
    1. Upload answer (PDF/image) -> Gemini extracts question (OCR)
    2. Parse question -> extract search terms for vector retrieval
    3. Retrieve relevant context from Pinecone/SQLite
    4. Fetch current affairs using parsed keywords
    5. Gemini improves answer with context + current affairs + system prompt
    6. Returns improved answer
    
    Args:
        file: PDF or image file containing the handwritten answer
        question: Optional question text (Gemini can identify from answer if not provided)
        word_count: Target word count (default: 350)
    
    Returns:
        - question: Identified or provided question
        - student_answer: Original answer text (extracted by Gemini)
        - improved_answer: Improved version of the answer
        - sources: List of sources used for context
    """
    # Parse word_count safely
    try:
        word_count_int = int(word_count) if word_count else 350
    except (ValueError, TypeError):
        word_count_int = 350
    
    if not GeminiClient or not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="Gemini client not available. Please check GEMINI_API_KEY configuration."
        )
    
    # Create temp directory for file
    temp_dir = tempfile.mkdtemp()
    temp_file_path = None
    
    try:
        logger.info("=" * 70)
        logger.info("🔁 Starting evaluate_answer endpoint...")
        logger.info(f"   • File: {file.filename}")
        logger.info(f"   • Question: {question[:100] if question else 'None (will identify)'}...")
        logger.info(f"   • Word count: {word_count_int}")
        logger.info("=" * 70)
        
        # Read file content
        file_content = await file.read()
        
        # Save uploaded file temporarily
        file_ext = Path(file.filename).suffix.lower() if file.filename else '.pdf'
        temp_file_path = os.path.join(temp_dir, f"answer{file_ext}")
        
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)
        
        logger.info(f"✅ File saved to: {temp_file_path}")
        
        # Determine if it's PDF or image
        is_pdf = file_ext == '.pdf'
        is_image = file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
        
        if not (is_pdf or is_image):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Please upload PDF or image file."
            )
        
        # Initialize Gemini client with Pro model
        gemini_client = GeminiClient(
            api_key=GEMINI_API_KEY,
            model_name="gemini-2.5-pro"
        )
        
        # ============================================================
        # STEP 1: Extract question from file if not provided
        # ============================================================
        identified_question = question
        if not identified_question:
            logger.info("📝 STEP 1: Extracting question from uploaded file...")
            try:
                question_prompt = """Read the handwritten answer and identify the QUESTION it is answering.

Look for:
- Question written at the top of the page
- Topic/subject being discussed
- Any numbered question (Q1, Q2, etc.)

Return ONLY the question text, nothing else. If you can't find an explicit question, infer it from the answer content."""
                
                if is_pdf:
                    question_response = await gemini_client.generate_response(
                        user_prompt=question_prompt,
                        pdf_path=temp_file_path,
                        temperature=0.0,
                        max_retries=2
                    )
                else:
                    question_response = await gemini_client.generate_response(
                        user_prompt=question_prompt,
                        image_path=temp_file_path,
                        temperature=0.0,
                        max_retries=2
                    )
                identified_question = question_response.strip()
                logger.info(f"✅ Identified question: {identified_question[:100]}...")
            except Exception as e:
                logger.warning(f"⚠️ Failed to identify question: {e}")
                identified_question = "Question not identified"
        else:
            logger.info(f"📝 STEP 1: Using provided question: {identified_question[:100]}...")
        
        # ============================================================
        # STEP 2: Parse question to extract search terms
        # ============================================================
        search_query = identified_question  # Default to full question
        parsed_topics = {}
        
        if parse_question_for_search and identified_question != "Question not identified":
            logger.info("🔍 STEP 2: Parsing question for search terms...")
            try:
                parsed_topics = await parse_question_for_search(
                    question=identified_question,
                    gemini_client=gemini_client,
                    model_name="gemini-2.5-pro"
                )
                search_query = parsed_topics.get("search_query", identified_question)
                logger.info(f"✅ Search query: {search_query}")
            except Exception as e:
                logger.warning(f"⚠️ Question parsing failed, using full question: {e}")
                search_query = identified_question
        else:
            logger.info("⚠️ STEP 2: Skipping question parsing (utility not available)")
        
        # ============================================================
        # STEP 3: Retrieve context from Pinecone/SQLite
        # ============================================================
        context = ""
        sources = []
        
        if retrieve_context_for_question:
            logger.info("📚 STEP 3: Retrieving context from vector store...")
            try:
                vector_handler = request.app.state.vector_handler
                if vector_handler:
                    context, sources = retrieve_context_for_question(
                        search_query=search_query,
                        vector_handler=vector_handler,
                        mode="mains",
                        use_content_store=True,
                        k=6
                    )
                    logger.info(f"✅ Retrieved context: {len(context)} chars from {len(sources)} sources")
                else:
                    logger.warning("⚠️ No vector handler available")
            except Exception as e:
                logger.warning(f"⚠️ Context retrieval failed: {e}")
                context = ""
                sources = []
        else:
            logger.info("⚠️ STEP 3: Skipping context retrieval (utility not available)")
        
        # ============================================================
        # STEP 4: Fetch current affairs using parsed keywords
        # ============================================================
        current_affairs_bullets = []
        
        if fetch_current_affairs_for_question and parsed_topics:
            logger.info("🗞️ STEP 4: Fetching current affairs...")
            try:
                current_affairs_bullets = await fetch_current_affairs_for_question(
                    parsed_keywords=parsed_topics,
                    max_bullets=5,
                    time_range="3months"
                )
                logger.info(f"✅ Retrieved {len(current_affairs_bullets)} current affairs bullets")
            except Exception as e:
                logger.warning(f"⚠️ Current affairs fetch failed: {e}")
                current_affairs_bullets = []
        else:
            logger.info("⚠️ STEP 4: Skipping current affairs fetch")
        
        # Append current affairs to context (additive, not replacing)
        if current_affairs_bullets and format_bullets_for_context:
            current_affairs_section = format_bullets_for_context(current_affairs_bullets)
            context = context + current_affairs_section
            logger.info(f"📝 Added current affairs to context: {len(current_affairs_section)} chars")
        
        # ============================================================
        # STEP 5: Build enhanced prompt with context
        # ============================================================
        logger.info("✍️ STEP 5: Building enhanced prompt with context...")
        
        user_prompt_parts = [f"**QUESTION**: {identified_question}\n\n"]
        
        if context:
            # Truncate context if too long
            max_context_chars = 8000
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "\n\n[CONTEXT TRUNCATED]"
            
            user_prompt_parts.append(f"""**REFERENCE CONTEXT** (use to substantiate points):
---
{context}
---

""")
        
        user_prompt_parts.append(f"""**TASK**: Read the student's handwritten answer from the uploaded file and provide an improved version.

**Requirements**:
1. Preserve the student's voice and original points
2. Use the REFERENCE CONTEXT above to add facts, data, and examples
3. Follow strict IBC format (Introduction-Body-Conclusion)
4. Target word count: approximately {word_count_int} words
5. Include at least one inline diagram suggestion
6. Every bullet must have: evidence (report/data) + example (India/World)

Return ONLY the improved answer in markdown format. No commentary.""")
        
        user_prompt = "".join(user_prompt_parts)
        
        # ============================================================
        # STEP 6: Call Gemini to generate improved answer
        # ============================================================
        logger.info("🤖 STEP 6: Generating improved answer with Gemini 2.5 Pro...")
        
        if is_pdf:
            improved_answer = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=ANSWER_IMPROVEMENT_SYSTEM_PROMPT,
                pdf_path=temp_file_path,
                temperature=0.2,
                max_retries=3
            )
        else:
            improved_answer = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=ANSWER_IMPROVEMENT_SYSTEM_PROMPT,
                image_path=temp_file_path,
                temperature=0.2,
                max_retries=3
            )
        
        logger.info(f"✅ Received improved answer: {len(improved_answer)} chars")
        logger.info("=" * 70)
        logger.info("✅ Evaluation complete!")
        logger.info("=" * 70)
        
        return {
            "question": identified_question,
            "student_answer": "Answer extracted by Gemini (see improved version below)",
            "improved_answer": improved_answer,
            "sources": sources,
            "parsed_topics": parsed_topics,
            "current_affairs_count": len(current_affairs_bullets),
            "success": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")
    
    finally:
        # Clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        # Clean up temp directory
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
