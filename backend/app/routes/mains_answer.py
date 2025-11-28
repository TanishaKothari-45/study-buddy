"""
mains_answer.py
Main handler for mains answer generation using the prompt templates.

Uses MCP current affairs server for latest news (not web_searcher).

Usage:
  from mains_prompt import assemble_mains_prompt
  from mains_answer import generate_answer

Config:
  export OPENAI_API_KEY=sk-...
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

# Import Gemini client for question parsing
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# -- Utility small guards and postprocessors --
def enforce_diagrams(answer: str, required: int = 1) -> str:
    """Ensure at least `required` '(Suggested Diagram:' instances exist."""
    have = answer.count("(Suggested Diagram:")
    if have >= required:
        return answer
    inserts = []
    for i in range(required - have):
        inserts.append("\n\n(Suggested Diagram: India map showing relevant regions)")
    # place inserts after first body heading if exists; else append
    parts = re.split(r"\n#{1,3}\s", answer, maxsplit=1)
    if len(parts) == 2:
        return parts[0] + "\n\n" + "(Suggested Diagram: India map showing relevant regions)\n\n" + parts[1]
    return answer + "\n\n" + "\n".join(inserts)

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

def generate_verdict(question: str, openai_client) -> Optional[str]:
    """Call OpenAI for a short 20-30 word verdict (use sparingly)."""
    if not openai_client:
        return None
    try:
        prompt = f"In one balanced 25-word sentence, give a verdict for: {question}"
        res = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            max_tokens=40,
            temperature=0.0
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        logger.debug(f"Verdict generation failed: {e}")
        return None

# -- Main entrypoint --
def generate_answer(
    question: str,
    static_context: Optional[str] = None,
    word_count: int = 350,
    produce_verdict: bool = True
) -> dict:
    """
    Top-level function to generate a mains answer.
    
    Note: Current affairs are now fetched in the endpoint using MCP server
    and appended to static_context before calling this function.

    Returns:
      { "answer": str, "sources": list }
    """
    # Current affairs bullets are now included in static_context
    # (fetched via MCP server in the endpoint)
    current_bullets_text = ""  # Kept for backward compatibility with assemble_mains_prompt

    # 1) Assemble prompt
    prompt_pair = assemble_mains_prompt(
        question=question,
        context=static_context,
        current_bullets=current_bullets_text,
        word_count=word_count
    )

    # 2) Call LLM (OpenAI) - guarded usage
    answer_text = ""
    sources = []
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set - cannot generate answer")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Compose final messages (system + user)
        system_msg = prompt_pair["system"]
        user_msg = prompt_pair["user"]

        # Prefer a single call; instruct model to be concise. Keep temperature moderate for variety.
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":system_msg},
                {"role":"user","content":user_msg}
            ],
            max_tokens=int(word_count * 2.2),  # conservative tokens mapping
            temperature=0.15
        )
        answer_text = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        # Fallback simple template answer to avoid blank responses
        answer_text = f"**Introduction**\nBrief introduction based on provided materials.\n\n**Body**\n• Key point 1\n• Key point 2\n\n**Conclusion**\nSynthesis and policy suggestion."

    # 3) Post-processing: ensure diagrams, word-count, verdict when needed
    answer_text = enforce_diagrams(answer_text, required=1)
    answer_text = enforce_word_count(answer_text, target=word_count)

    # 4) If produce_verdict and directive likely needs it, create short verdict (sparing OpenAI calls)
    verdict_text = None
    if produce_verdict and OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client_v = OpenAI(api_key=OPENAI_API_KEY)
            verdict_text = generate_verdict(question, client_v)
            if verdict_text:
                answer_text += f"\n\n**Verdict**: {verdict_text}"
        except Exception as e:
            logger.debug(f"Verdict generation failed: {e}")

    # 5) Pack result
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

        # Generate answer using the generate_answer function
        # Note: Current affairs are already included in context via MCP fetch above
        logger.info(f"🤖 [MAINS] Generating answer...")
        result = generate_answer(
            question=mains_request.question,
            static_context=context,
            word_count=mains_request.word_count,
            produce_verdict=False  # Disabled to save API calls
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
