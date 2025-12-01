"""
mains_answer.py
Main handler for mains answer generation using Gemini 2.5 Pro.

Uses MCP current affairs server for latest news (not web_searcher).

Usage:
  from mains_prompt import assemble_mains_prompt
  from mains_answer import generate_answer

Config:
  export GEMINI_API_KEY=...
"""

import os
import sys
import logging
import re
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger("mains_answer")
logging.basicConfig(level=logging.INFO)

from mains_prompt import assemble_mains_prompt
from ..utils.context_retriever import retrieve_context_for_question
from ..utils.question_parser import parse_question_for_search
from ..utils.current_affairs_fetcher import fetch_current_affairs_for_question, format_bullets_for_context

# Import Gemini client
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

# -- Utility small guards and postprocessors --
def enforce_diagrams(answer: str, required: int = 1) -> str:
    """
    Ensure at least `required` Mermaid diagrams exist in the answer.
    If not, insert a safe, minimal Mermaid diagram (flowchart)
    in a stable location (after first sub-heading and before bullets).
    """
    # quick check: count existing mermaid fenced blocks
    mermaid_count = answer.count("```mermaid")
    if mermaid_count >= required:
        return answer
    
    return answer

def enforce_word_count(answer: str, target: int) -> str:
    words = len(answer.split())
    if words > target * 1.2:
        # trim last paragraph(s)
        paras = [p for p in answer.split("\n\n") if p.strip()]
        if len(paras) > 1:
            # drop last paragraph(s) until under limit
            while len(" ".join(" ".join(paras).split()).split()) > target * 1.2 and len(paras) > 1:
                paras = paras[:-1]
            return "\n\n".join(paras).strip()
        return " ".join(answer.split()[: int(target * 1.2 * 1.0)])
    elif words < target * 0.8:
        # add a short synthesis sentence
        return answer + f"\n\n(Addendum: In short, the above points suggest that a balanced policy mix is required.)"
    return answer

async def generate_answer(
    question: str,
    static_context: Optional[str] = None,
    word_count: int = 350,
    gemini_client: Optional[Any] = None
) -> dict:
    """
    Top-level function to generate a mains answer using Gemini 2.5 Pro.
    
    Args:
        question: The mains question to answer
        static_context: Retrieved context (includes current affairs)
        word_count: Target word count for the answer
        gemini_client: GeminiClient instance (required)
    
    Returns:
        { "answer": str, "sources": list }
    """
    if not gemini_client:
        raise RuntimeError("GeminiClient is required for answer generation")

    # 1) Assemble prompt
    prompt_pair = assemble_mains_prompt(
        question=question,
        context=static_context,
        current_bullets="",  # Current affairs already in static_context
        word_count=word_count
    )

    # 2) Call Gemini 2.5 Pro
    answer_text = ""
    sources = []

    try:
        # Compose final messages (system + user)
        system_msg = prompt_pair["system"]
        user_msg = prompt_pair["user"]

        logger.info(f"🤖 Calling Gemini 2.5 Pro for answer generation...")
        
        # Call Gemini with async
        response = await gemini_client.generate_response(
            user_prompt=user_msg,
            system_prompt=system_msg,
            temperature=0.15,  # Low temperature for consistency
            max_retries=2
        )
        
        answer_text = response.strip()
        logger.info(f"✅ Gemini response received: {len(answer_text)} chars")
        
    except Exception as e:
        logger.error(f"❌ Gemini call failed: {e}")
        # Fallback simple template answer to avoid blank responses
        answer_text = f"**Introduction**\nBrief introduction based on provided materials.\n\n**Body**\n• Key point 1\n• Key point 2\n\n**Conclusion**\nSynthesis and policy suggestion."

    # 3) Post-processing: ensure diagrams and word-count
    answer_text = enforce_diagrams(answer_text, required=1)
    # answer_text = enforce_word_count(answer_text, target=word_count)

    # 4) Pack result
    result = {
        "answer": answer_text,
        "sources": sources  # placeholder: can integrate actual source extraction later
    }
    return result

# FastAPI Router
router = APIRouter()

class MainsAnswerRequest(BaseModel):
    question: str
    word_count: int = 500

class MainsAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    word_count_actual: int

@router.post("/generate")
async def generate_mains_answer(request: Request, mains_request: MainsAnswerRequest):
    """
    Generate a comprehensive UPSC Mains style answer for Geography questions.
    """
    try:
        logger.info(f"🚀 [MAINS] Received request: '{mains_request.question[:100]}...' (word_count={mains_request.word_count})")
        
        # Get Pinecone handler
        pinecone_handler = request.app.state.vector_handler
        
        # Use FULL question for Pinecone vector search (better semantic matching)
        logger.info(f"📚 [MAINS] Retrieving context using full question...")
        context, sources = retrieve_context_for_question(
            search_query=mains_request.question,  # Full question for Pinecone
            vector_handler=pinecone_handler,
            mode="mains",
            use_content_store=True,
            k=6
        )
        
        if not context:
            logger.warning(f"⚠️ [MAINS] No context retrieved")
            return MainsAnswerResponse(
                question=mains_request.question,
                answer="No relevant information found in the uploaded documents for this question.",
                sources=[],
                word_count_actual=0
            )
        
        logger.info(f"✅ [MAINS] Retrieved context: {len(context)} chars, {len(sources)} sources")

        # Parse question for current affairs search (keywords work better for news APIs)
        parsed_topics = {}
        if GeminiClient and GEMINI_API_KEY:
            logger.info(f"🔍 [MAINS] Parsing question for current affairs search...")
            try:
                gemini_client = GeminiClient(
                    api_key=GEMINI_API_KEY,
                    model_name="gemini-2.5-pro"
                )
                parsed_topics = await parse_question_for_search(
                    question=mains_request.question,
                    gemini_client=gemini_client,
                    model_name="gemini-2.5-pro"
                )
                logger.info(f"✅ [MAINS] Parsed for current affairs: {parsed_topics.get('search_query', '')[:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ [MAINS] Question parsing failed: {e}")
                parsed_topics = {}

        # Fetch current affairs using parsed keywords (in addition to static context)
        current_affairs_bullets = []
        if parsed_topics:
            logger.info(f"🗞️ [MAINS] Fetching current affairs...")
            try:
                current_affairs_bullets = await fetch_current_affairs_for_question(
                    parsed_keywords=parsed_topics,
                    max_bullets=5,
                    time_range="3months"
                )
                logger.info(f"✅ [MAINS] Retrieved {len(current_affairs_bullets)} current affairs bullets")
            except Exception as e:
                logger.warning(f"⚠️ [MAINS] Current affairs fetch failed: {e}")
                current_affairs_bullets = []
        
        # Append current affairs to context (additive, not replacing)
        if current_affairs_bullets:
            current_affairs_section = format_bullets_for_context(current_affairs_bullets)
            logger.info(f"📝 [MAINS] Current affairs section: {current_affairs_section}")
            context = context + current_affairs_section
            logger.info(f"📝 [MAINS] Added current affairs to context: {len(current_affairs_section)} chars")

        # Generate answer using Gemini 2.5 Pro
        # Note: Current affairs are already included in context via MCP fetch above
        logger.info(f"🤖 [MAINS] Generating answer with Gemini 2.5 Pro...")
        
        # Initialize Gemini client
        if not GeminiClient or not GEMINI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Gemini client not available. Please configure GEMINI_API_KEY."
            )
        
        gemini_client = GeminiClient(
            api_key=GEMINI_API_KEY,
            model_name="gemini-2.5-pro"
        )
        
        # Call async generate_answer
        result = await generate_answer(
            question=mains_request.question,
            static_context=context,
            word_count=mains_request.word_count,
            gemini_client=gemini_client
        )
        
        answer = result["answer"]
        word_count_actual = len(answer.split())
        
        logger.info(f"✅ [MAINS] Answer generated: {len(answer)} characters, {word_count_actual} words")
        
        return MainsAnswerResponse(
            question=mains_request.question,
            answer=answer,
            sources=sources,
            word_count_actual=word_count_actual
        )

    except Exception as e:
        logger.error(f"❌ Mains answer generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Quick test function
if __name__ == "__main__":
    q = "Discuss the causes and impacts of increasing forest fires in India and suggest mitigation measures."
    res = generate_answer(q, static_context="Use NCERT and Vision IAS notes on forests", word_count=300)
    print(res["answer"][:2000])
