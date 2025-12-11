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
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException, Depends
from pathlib import Path
import json
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# ============================================================
# Pydantic Models for Gemini Structured Output
# ============================================================

class FeedbackDetails(BaseModel):
    """Structured feedback for student answer evaluation."""
    strengths: List[str] = Field(
        default_factory=list,
        description="Specific strengths of the student's answer"
    )
    missing_elements: List[str] = Field(
        default_factory=list,
        description="Key points missing from the student's answer"
    )
    improvements_needed: List[str] = Field(
        default_factory=list,
        description="Actionable suggestions for improvement"
    )
    structure_feedback: str = Field(
        default="",
        description="Comment on IBC format adherence and structure"
    )
    evidence_feedback: str = Field(
        default="",
        description="Comment on use of reports/data/indices/examples"
    )
    overall_assessment: str = Field(
        default="",
        description="Brief overall assessment and encouragement"
    )

class EvaluationResponse(BaseModel):
    """Structured response for answer evaluation."""
    improved_answer: str = Field(
        min_length=1,
        description="Improved answer in markdown format following IBC rules"
    )
    feedback: FeedbackDetails = Field(
        description="Detailed feedback on the student's answer"
    )

# Import Gemini client
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

# Import config for OpenAI API key
from ..core.config import settings
from ..core.deps import get_current_user
from ..models.user import User
OPENAI_API_KEY = settings.OPENAI_API_KEY

# Import utilities
try:
    from ..utils.question_parser import parse_question_for_search
    from ..utils.context_retriever import retrieve_context_for_question
    from ..utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context
    from ..utils.map_proxy import parse_and_generate_maps, check_map_service_health
    from ..utils.cache_manager import get_cache_manager
    from ..utils.user_api_key import get_gemini_api_key_for_request
except ImportError as e:
    parse_question_for_search = None
    retrieve_context_for_question = None
    fetch_current_affairs_for_question = None
    format_bullets_for_context = None
    parse_and_generate_maps = None
    check_map_service_health = None
    get_cache_manager = None
    get_gemini_api_key_for_request = None
    logger.warning(f"Could not import utilities: {e}")

# Import shared prompts for consistency with mains_answer.py
try:
    from ..prompts.shared_mains_prompts import get_evaluation_system_prompt
    USE_SHARED_PROMPTS = True
    logger.info("✅ Using shared prompts for evaluation")
except ImportError as e:
    USE_SHARED_PROMPTS = False
    logger.warning(f"⚠️ Could not import shared prompts, using inline prompt: {e}")

# Legacy inline prompt (fallback only - kept for backward compatibility)
ANSWER_IMPROVEMENT_SYSTEM_PROMPT = """You are an expert UPSC Geography teacher, evaluator and answer-writing coach.

Your task is to read a student's handwritten answer and provide:
1. An improved version using the provided reference context
2. Detailed feedback comparing the student's answer to the ideal answer

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
7) Diagram discipline: At least ONE Mermaid diagram inside body (explicit).

**RULE 5 - IBC FORMAT**:
- INTRO: 2-3 lines. Must include either a definition, a data point/report citation, or a recent context or current affair (if applicable).
- BODY: Use sub-headings and bullets. Each bullet <= 18 words. Main idea (≤ 10-12 words) — Evidence (report/data/index) — Example (India OR World). Include at least ONE Mermaid diagram using ```mermaid code blocks.
- CONCLUSION: 1 para with global best practices + SDG + policy angle + related Indian constitution articles.

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
You MUST return a JSON object with the following structure:
```json
{
  "improved_answer": "The improved answer in markdown format following all IBC rules and including Mermaid diagrams...",
  "feedback": {
    "strengths": [
      "List specific strengths of the student's answer",
      "What they did well (structure, examples, evidence, diagrams, etc.)"
    ],
    "missing_elements": [
      "Key points missing from the student's answer",
      "Important facts, dimensions, data, examples, or diagrams they should have included"
    ],
    "improvements_needed": [
      "Specific actionable suggestions for improvement",
      "What to add, remove, or modify in future answers"
    ],
    "structure_feedback": "Comment on IBC format adherence, sub-headings, bullet discipline, diagram quality",
    "evidence_feedback": "Comment on use of reports/data/indices/examples",
    "overall_assessment": "Brief overall assessment and encouragement"
  }
}
```

**CRITICAL**: Return ONLY valid JSON. No markdown code blocks, no commentary before or after. Just the raw JSON object.
- The improved_answer should use markdown formatting (headings, bullets, Mermaid diagrams)
- Every single bullet MUST contain: (a) One evidence (report/index/data), (b) One example (named Indian OR named global), (c) Maximum 18 words total
- Include at least ONE Mermaid diagram in improved_answer
- Feedback should be constructive, specific, and actionable
"""


from ..utils.langsmith_tracer import trace_chain

@router.post("/")
@trace_chain("evaluate_answer_endpoint")
async def evaluate_answer_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    question: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user)
):
    """
    Evaluate and improve student answer using Gemini with context retrieval and current affairs.
    
    Flow:
    1. Upload answer files (PDF/images) -> Gemini extracts question (OCR)
    2. Parse question -> extract search terms for vector retrieval
    3. Retrieve relevant context from Pinecone/SQLite
    4. Fetch current affairs using parsed keywords
    5. Gemini improves answer with context + current affairs + system prompt
    6. Returns improved answer
    
    Args:
        files: List of PDF or image files containing the handwritten answer (supports multi-page)
        question: Optional question text (Gemini can identify from answer if not provided)
    
    Returns:
        - question: Identified or provided question
        - student_answer: Original answer text (extracted by Gemini)
        - improved_answer: Improved version of the answer
        - sources: List of sources used for context
    """
    # Use default word count
    word_count_int = 350
    
    if not GeminiClient:
        raise HTTPException(
            status_code=500, 
            detail="Gemini client not available. Please check configuration."
        )
    
    # Get Gemini API key (user's personal key or system default)
    try:
        gemini_api_key = get_gemini_api_key_for_request(current_user) if get_gemini_api_key_for_request else GEMINI_API_KEY
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail="No Gemini API key configured. Please set your personal API key in settings to use this feature."
        )
    
    if not gemini_api_key:
        raise HTTPException(
            status_code=400, 
            detail="No Gemini API key available. Please set your personal API key in settings to use this feature."
        )
    
    # Create temp directory for file
    temp_dir = tempfile.mkdtemp()
    temp_file_path = None
    
    try:
        logger.info("=" * 70)
        logger.info("🔁 Starting evaluate_answer endpoint...")
        logger.info(f"   • Files: {len(files)} file(s)")
        for idx, f in enumerate(files, 1):
            logger.info(f"     {idx}. {f.filename}")
        logger.info(f"   • Question: {question[:100] if question else 'None (will identify)'}...")
        logger.info(f"   • Word count: {word_count_int}")
        logger.info("=" * 70)
        
        # Check map service health (non-blocking)
        if check_map_service_health:
            logger.info("🔍 [EVALUATE] Checking map service health...")
            map_service_healthy = await check_map_service_health()
            if map_service_healthy:
                logger.info("✅ [EVALUATE] Map service is available")
            else:
                logger.warning("⚠️  [EVALUATE] Map service is unavailable - maps will not be generated")
        
        # Process all files and save to temp directory
        temp_file_paths = []
        all_is_pdf = True
        all_is_image = True
        
        for file in files:
            # Read file content
            file_content = await file.read()
            
            # Save uploaded file temporarily
            file_ext = Path(file.filename).suffix.lower() if file.filename else '.pdf'
            temp_file_path = os.path.join(temp_dir, f"answer_{len(temp_file_paths)}{file_ext}")
            
            with open(temp_file_path, "wb") as buffer:
                buffer.write(file_content)
            
            temp_file_paths.append(temp_file_path)
            logger.info(f"✅ File {len(temp_file_paths)} saved to: {temp_file_path}")
            
            # Check file types
            is_pdf = file_ext == '.pdf'
            is_image = file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
            
            if not (is_pdf or is_image):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {file_ext}. Please upload PDF or image file."
                )
            
            all_is_pdf = all_is_pdf and is_pdf
            all_is_image = all_is_image and is_image
        
        # Initialize Gemini client with Pro model and user's API key
        gemini_client = GeminiClient(
            api_key=gemini_api_key,
            model_name="gemini-2.5-pro"
        )
        
        # ============================================================
        # STEP 1: Extract question from files if not provided
        # ============================================================
        identified_question = question
        if not identified_question:
            logger.info("📝 STEP 1: Extracting question from uploaded files...")
            try:
                question_prompt = """Read the handwritten answer and identify the QUESTION it is answering.

Look for:
- Question written at the top of the page
- Topic/subject being discussed
- Any numbered question (Q1, Q2, etc.)

Return ONLY the question text, nothing else. If you can't find an explicit question, infer it from the answer content."""
                
                # Use first file to extract question
                if all_is_pdf:
                    question_response = await gemini_client.generate_response(
                        user_prompt=question_prompt,
                        pdf_path=temp_file_paths[0],
                        temperature=0.0,
                        max_retries=2
                    )
                else:
                    question_response = await gemini_client.generate_response(
                        user_prompt=question_prompt,
                        image_path=temp_file_paths[0],
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
        # STEP 2: Retrieve context from Pinecone/SQLite (FULL question)
        # ============================================================
        context = ""
        sources = []
        
        if retrieve_context_for_question:
            logger.info("📚 STEP 2: Retrieving context using full question...")
            try:
                vector_handler = request.app.state.vector_handler
                if vector_handler:
                    context, sources = retrieve_context_for_question(
                        search_query=identified_question,  # Full question for Pinecone
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
            logger.info("⚠️ STEP 2: Skipping context retrieval (utility not available)")
        
        # ============================================================
        # STEP 3: Parse question for current affairs (keywords better for news)
        # ============================================================
        parsed_topics = {}
        
        if parse_question_for_search and identified_question != "Question not identified":
            logger.info("🔍 STEP 3: Parsing question for current affairs search...")
            try:
                parsed_topics = await parse_question_for_search(
                    question=identified_question,
                    openai_api_key=OPENAI_API_KEY
                )
                logger.info(f"✅ Parsed for current affairs: {parsed_topics.get('search_query', '')[:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ Question parsing failed: {e}")
                parsed_topics = {}
        
        # ============================================================
        # STEP 4: Fetch current affairs using parsed keywords (with caching)
        # ============================================================
        current_affairs_bullets = []
        time_range = "3months"
        
        if fetch_current_affairs_for_question and parsed_topics:
            # Initialize cache manager
            cache = get_cache_manager() if get_cache_manager else None
            cached_news = None
            
            # Check news cache first
            if cache:
                cached_news = cache.get_cached_news(parsed_topics, time_range)
            
            if cached_news:
                # News cache HIT
                logger.info(f"🎯 STEP 4: [NEWS CACHE HIT] Using cached news ({len(cached_news)} bullets)")
                current_affairs_bullets = cached_news
            else:
                # News cache MISS - fetch from MCP
                logger.info("🗞️ STEP 4: [NEWS CACHE MISS] Fetching current affairs from MCP...")
                try:
                    current_affairs_bullets = await fetch_current_affairs_for_question(
                        parsed_keywords=parsed_topics,
                        max_bullets=5,
                        time_range=time_range,
                        gemini_api_key=None  # use system key fallback
                    )
                    logger.info(f"✅ Retrieved {len(current_affairs_bullets)} current affairs bullets")
                    
                    # Cache the news bullets
                    if cache:
                        cache.set_cached_news(parsed_topics, current_affairs_bullets, time_range)
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
        # STEP 4.5: Load training examples for few-shot learning (0-5 examples)
        # ============================================================
        logger.info("🎓 STEP 4.5: Loading training examples for few-shot learning...")
        training_examples = []
        try:
            training_data_file = Path(__file__).parent.parent.parent / "data" / "training_examples.json"
            if training_data_file.exists():
                with open(training_data_file, 'r', encoding='utf-8') as f:
                    training_data = json.load(f)
                    all_examples = training_data.get("training_examples", [])
                    # Get last 5 examples (most recent)
                    training_examples = all_examples[-3:] if len(all_examples) > 3 else all_examples
                    logger.info(f"✅ Loaded {len(training_examples)} training examples for few-shot learning")
            else:
                logger.info("ℹ️ No training examples file found (this is okay for first use)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load training examples: {e}")
            training_examples = []
        
        # ============================================================
        # STEP 5: Build enhanced prompt with context + current affairs
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
        
        # Add few-shot examples if available
        if training_examples:
            user_prompt_parts.append("\n**FEW-SHOT EXAMPLES** (learn from these feedback examples):\n")
            user_prompt_parts.append("---\n")
            for idx, example in enumerate(training_examples, 1):
                user_prompt_parts.append(f"\n**Example {idx}:**\n")
                user_prompt_parts.append(f"Question: {example.get('question', 'N/A')[:150]}...\n\n")
                user_prompt_parts.append(f"Student Answer Preview: {example.get('student_answer', 'N/A')[:200]}...\n\n")
                user_prompt_parts.append(f"Ideal Feedback Given:\n{example.get('ideal_feedback', 'N/A')}\n")
                user_prompt_parts.append("\n---\n")
            logger.info(f"📚 Added {len(training_examples)} few-shot examples to prompt")
        
        user_prompt_parts.append(f"""\n**TASK**: Read the student's handwritten answer from the uploaded file and provide:
1. An improved version in strict IBC format
2. Detailed feedback comparing the student's answer to the ideal answer

**Requirements for Improved Answer**:
1. Preserve the student's voice and original points
2. Use the REFERENCE CONTEXT above to add facts, data, and examples
3. Follow strict IBC format (Introduction-Body-Conclusion)
4. Target word count: approximately {word_count_int} words
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
        
        user_prompt = "".join(user_prompt_parts)
        
        # ============================================================
        # STEP 6: Call Gemini to generate improved answer with all files
        # ============================================================
        logger.info("🤖 STEP 6: Generating improved answer with Gemini 2.5 Pro...")
        
        # Use shared prompt if available, otherwise fallback to inline prompt
        system_prompt = get_evaluation_system_prompt() if USE_SHARED_PROMPTS else ANSWER_IMPROVEMENT_SYSTEM_PROMPT
        
        # For multiple files, we need to pass them all to Gemini
        if all_is_pdf:
            # Pass all PDF paths as a list
            response_text = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                pdf_path=temp_file_paths,  # Pass list directly
                temperature=0.2,
                max_retries=3
            )
        elif all_is_image:
            # Pass all image paths as a list
            response_text = await gemini_client.generate_response(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                image_path=temp_file_paths,  # Pass list directly
                temperature=0.2,
                max_retries=3
            )
        else:
            # Mixed types - process separately and combine
            # For now, just use first file
            logger.warning("⚠️ Mixed file types detected, using first file only")
            if temp_file_paths[0].endswith('.pdf'):
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    pdf_path=temp_file_paths[0],
                    temperature=0.2,
                    max_retries=3
                )
            else:
                response_text = await gemini_client.generate_response(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    image_path=temp_file_paths[0],
                    temperature=0.2,
                    max_retries=3
                )
        
        logger.info(f"✅ Received response: {len(response_text)} chars")
        
        # Parse response - try structured format first, then fallback to JSON parsing
        try:
            # Try parsing as structured Pydantic response
            logger.info("🔍 Attempting to parse Gemini response as structured output...")
            
            # Clean response text (remove markdown code blocks if present)
            cleaned_response = response_text.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]  # Remove ```json
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]  # Remove ```
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]  # Remove trailing ```
            cleaned_response = cleaned_response.strip()
            
            # Parse JSON first
            response_data = json.loads(cleaned_response)
            
            # Validate with Pydantic (provides type safety and defaults)
            evaluation_response = EvaluationResponse(**response_data)
            
            # Extract from validated model
            improved_answer = evaluation_response.improved_answer
            feedback = {
                "strengths": evaluation_response.feedback.strengths,
                "missing_elements": evaluation_response.feedback.missing_elements,
                "improvements_needed": evaluation_response.feedback.improvements_needed,
                "structure_feedback": evaluation_response.feedback.structure_feedback,
                "evidence_feedback": evaluation_response.feedback.evidence_feedback,
                "overall_assessment": evaluation_response.feedback.overall_assessment
            }
            
            logger.info(f"✅ Parsed response with Pydantic validation")
            logger.info(f"   • Improved answer: {len(improved_answer)} chars")
            logger.info(f"   • Feedback sections: {list(feedback.keys())}")
            
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON parsing failed: {e}")
            logger.warning(f"   Response preview: {response_text[:200]}...")
            # Fallback: treat entire response as improved answer
            improved_answer = response_text
            feedback = {
                "strengths": [],
                "missing_elements": [],
                "improvements_needed": [],
                "structure_feedback": "Unable to generate feedback - JSON parsing failed",
                "evidence_feedback": "Unable to generate feedback - JSON parsing failed",
                "overall_assessment": "Please review the improved answer above."
            }
        except Exception as e:
            logger.warning(f"⚠️ Pydantic validation failed: {e}")
            logger.warning(f"   Falling back to direct JSON extraction")
            # Fallback to direct dict access (backward compatibility)
            try:
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
                logger.info(f"✅ Using fallback JSON extraction (backward compatible)")
            except:
                # Ultimate fallback
                improved_answer = response_text
                feedback = {
                    "strengths": [],
                    "missing_elements": [],
                    "improvements_needed": [],
                    "structure_feedback": "Unable to generate feedback",
                    "evidence_feedback": "Unable to generate feedback",
                    "overall_assessment": "Please review the improved answer above."
                }
        
        # Process map-json blocks in improved answer
        if parse_and_generate_maps:
            logger.info("🗺️  [EVALUATE] Checking for map-json blocks in improved answer...")
            try:
                improved_answer = await parse_and_generate_maps(improved_answer)
                logger.info("✅ [EVALUATE] Map processing completed")
            except Exception as e:
                logger.error(f"❌ [EVALUATE] Map processing failed: {str(e)}", exc_info=True)
                # Continue with answer even if map generation fails
        
        logger.info("=" * 70)
        logger.info("✅ Evaluation complete!")
        logger.info("=" * 70)
        
        return {
            "question": identified_question,
            "student_answer": "Answer extracted by Gemini (see improved version below)",
            "improved_answer": improved_answer,
            "feedback": feedback,
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
        # Clean up temp files
        if 'temp_file_paths' in locals():
            for temp_path in temp_file_paths:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        # Clean up temp directory
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
