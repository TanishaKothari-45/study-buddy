"""
question_parser.py

LLM-powered question parser that extracts search-friendly keywords from UPSC questions.
Converts verbose questions into optimized search queries for NEWS/CURRENT AFFAIRS retrieval only.

NOTE: This is NOT used for vector database retrieval - that uses the full question directly.
      Keywords work better for news search, while full questions work better for embeddings.

Uses GPT-4o-mini with Structured Output (Pydantic) and Redis caching for better performance.

Usage:
    from question_parser import parse_question_for_search
    
    result = await parse_question_for_search(
        question="Discuss climate change and its impact on agriculture and latest initiatives to mitigate it",
        openai_api_key="sk-..."
    )
    # Returns: {
    #     "main_topic": "climate change",
    #     "sub_topics": ["impact on agriculture", "mitigation initiatives"],
    #     "search_query": "climate change impact agriculture mitigation initiatives"
    # }
"""

import logging
import json
import hashlib
from typing import Optional
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================
# Pydantic Models for Structured Output
# ============================================================

class ParsedQuestion(BaseModel):
    """Structured output schema for question parsing."""
    main_topic: str = Field(
        description="Core subject combined with specific entity/demographic (2-4 words). Examples: 'tribal agriculture', 'coastal flooding', 'urban migration'"
    )
    sub_topics: list[str] = Field(
        description="2-5 meaningful phrases ranked by importance (1-3 words each). Priority: Geography > Qualifiers > Related concepts"
    )
    search_query: str = Field(
        description="Combined main_topic + sub_topics (space-separated, optimized for vector search)"
    )

# Redis cache for parsed questions
try:
    from .cache_manager import get_cache_manager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    logger.warning("⚠️ Cache manager not available for question parser")

# System prompt for question parsing (for news/current affairs search only)
QUESTION_PARSER_SYSTEM_PROMPT = """
You extract search-focused keywords from UPSC questions for NEWS and CURRENT AFFAIRS search.

TASK:
- MAIN TOPIC: Combine core subject + specific entity/demographic (2-4 words)
  Examples: "tribal agriculture", "coastal flooding", "urban migration", "forest fires"
- SUB TOPICS: 2-5 meaningful phrases ranked by importance (1-3 words each)
  Priority: Geography > Qualifiers > Related concepts
- SEARCH_QUERY: main_topic + sub_topics (space-separated, optimized for news search)
- Remove filler verbs (discuss, examine, critically, analyze)

KEYWORD COMBINATION RULES:
1. Combine subject + entity in MAIN TOPIC: "tribal agriculture" NOT "agriculture" + "tribal" separately
2. Keep geographic names in SUB TOPICS: "Odisha", "Northeast India", "Western Ghats"
3. Combine related qualifiers: "drought impact" NOT "drought" + "impact" separately
4. Rank SUB TOPICS by importance: region first, then qualifiers, then generic terms

Examples:
Q: "Impact of drought on tribal agriculture in Odisha"
→ {"main_topic":"tribal agriculture drought","sub_topics":["Odisha","rural livelihoods","food security"],"search_query":"tribal agriculture drought Odisha rural livelihoods"}

Q: "Causes and impacts of forest fires in India; suggest mitigation measures."
→ {"main_topic":"forest fires","sub_topics":["causes impacts","mitigation measures","India"],"search_query":"forest fires causes impacts mitigation measures India"}

Q: "Role of monsoons in shaping Indian agriculture; recent trends."
→ {"main_topic":"monsoon agriculture","sub_topics":["India","rainfall patterns","crop production"],"search_query":"monsoon agriculture India rainfall patterns crop production"}

Q: "Climate change effects on coastal women in Kerala"
→ {"main_topic":"coastal communities climate","sub_topics":["Kerala","women livelihoods","vulnerability"],"search_query":"coastal communities climate Kerala women livelihoods vulnerability"}

Q: "Migration patterns of scheduled tribes in Northeast India"
→ {"main_topic":"tribal migration","sub_topics":["Northeast India","displacement patterns","indigenous rights"],"search_query":"tribal migration Northeast India displacement patterns"}

Q: "Urbanization affecting groundwater in India; remedial measures."
→ {"main_topic":"urbanization groundwater","sub_topics":["depletion impacts","remedial measures","India"],"search_query":"urbanization groundwater depletion impacts remedial measures India"}
"""



from .langsmith_tracer import trace_llm


from ..gemini_core.gemini_client import GeminiClient
from ..core.config import settings

@trace_llm("question_parser")
async def parse_question_for_search(
    question: str,
    gemini_api_key: Optional[str] = None
) -> dict:
    """
    Parse a UPSC question to extract search-friendly keywords for NEWS/CURRENT AFFAIRS retrieval.
    Uses Gemini 2.5 Flash with Structured Output and Redis caching.
    
    NOTE: This is ONLY for news search. Vector database uses the full question directly.
    
    Args:
        question: The full question text
        gemini_api_key: Gemini API key (optional, will use env var or settings if not provided)
    
    Returns:
        dict with keys:
            - main_topic: str - central subject (1-3 words)
            - sub_topics: list[str] - specific aspects (2-5 items)
            - search_query: str - combined query optimized for news search
    """
    if not question or not question.strip():
        logger.warning("Empty question provided to parser")
        return {
            "main_topic": "",
            "sub_topics": [],
            "search_query": ""
        }
    
    # Check cache first
    if CACHE_AVAILABLE:
        cache = get_cache_manager()
        cache_key = f"qparse:{hashlib.md5(question.encode()).hexdigest()}"
        
        try:
            if cache.enabled:
                cached_result = cache.redis.get(cache_key)
                if cached_result:
                    logger.info(f"🎯 [CACHE HIT] Question parser cache hit")
                    return json.loads(cached_result)
        except Exception as e:
            logger.warning(f"⚠️ Cache read failed: {e}")
    
    # Use system key if no user key provided
    key_to_use = gemini_api_key or settings.GEMINI_API_KEY
    
    try:
        logger.info(f"🔍 [CACHE MISS] Parsing question with Gemini Flash (Structured Output): {question[:80]}...")
        
        client = GeminiClient(api_key=key_to_use, model_name=settings.GEMINI_MODEL_FLASH)
        
        # We need to construct a JSON schema for Gemini structured output
        # Pydantic schema is already defined in ParsedQuestion class
        
        prompt = f"""Extract search keywords from this UPSC question for NEWS search:

Question: {question}

Return the result purely in JSON format matching this schema:
{{
  "main_topic": "string (Core subject + entity, 2-4 words)",
  "sub_topics": ["string (2-5 meaningful phrases)"],
  "search_query": "string (combined query)"
}}
"""

        response_text = await client.generate_response(
            user_prompt=prompt,
            system_prompt=QUESTION_PARSER_SYSTEM_PROMPT,
            response_schema=ParsedQuestion, # GeminiClient handles Pydantic schema
            temperature=0.0,
        )
        
        # The response should already be validated JSON string
        try:
            parsed_dict = json.loads(response_text)
            
            # Additional safety check
            if not isinstance(parsed_dict, dict):
                 raise ValueError("Response is not a dictionary")
        except json.JSONDecodeError:
             logger.warning("Gemini returned invalid JSON, attempting cleanup")
             # Try simple cleanup if markdown blocks exist
             clean_text = response_text.replace("```json", "").replace("```", "").strip()
             parsed_dict = json.loads(clean_text)

        parsed_result = {
            "main_topic": parsed_dict.get("main_topic", ""),
            "sub_topics": parsed_dict.get("sub_topics", []),
            "search_query": parsed_dict.get("search_query", "")
        }
        
        logger.info(f"✅ Parsed question with Structured Output:")
        logger.info(f"   • Main topic: {parsed_result['main_topic']}")
        logger.info(f"   • Sub topics: {parsed_result['sub_topics']}")
        logger.info(f"   • Search query: {parsed_result['search_query']}")
        
        # Cache the result (7 days TTL)
        if CACHE_AVAILABLE:
            try:
                if cache.enabled:
                    cache.redis.set(
                        cache_key,
                        json.dumps(parsed_result),
                        ex=604800  # 7 days in seconds
                    )
                    logger.info(f"💾 Cached parsed question for 7 days")
            except Exception as e:
                logger.warning(f"⚠️ Cache write failed: {e}")
        
        return parsed_result
        
    except Exception as e:
        logger.error(f"❌ Question parsing failed: {e}", exc_info=True)
        
        # Fallback: use simple extraction
        return _fallback_parse(question)


def _fallback_parse(question: str) -> dict:
    """
    Simple fallback parser when LLM fails.
    Removes common filler words and returns cleaned query.
    """
    # Common filler words to remove
    filler_words = {
        "discuss", "explain", "examine", "critically", "analyze", "analyse",
        "elaborate", "elucidate", "comment", "evaluate", "assess", "describe",
        "what", "how", "why", "when", "where", "which", "who",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "must", "shall", "can", "to", "of", "in", "for", "on", "with",
        "at", "by", "from", "as", "into", "through", "during", "before", "after",
        "above", "below", "between", "under", "again", "further", "then", "once",
        "and", "or", "but", "if", "because", "until", "while", "although",
        "this", "that", "these", "those", "it", "its", "their", "your",
        "extent", "regarding", "respect", "context", "light", "view"
    }
    
    # Clean and tokenize
    words = question.lower().replace("?", "").replace(".", "").replace(",", "").split()
    
    # Filter out filler words
    meaningful_words = [w for w in words if w not in filler_words and len(w) > 2]
    
    # Take first 10 meaningful words
    search_words = meaningful_words[:10]
    search_query = " ".join(search_words)
    
    # Try to identify main topic (first 2-3 meaningful words)
    main_topic = " ".join(search_words[:3]) if search_words else ""
    
    # Sub topics are remaining words
    sub_topics = search_words[3:7] if len(search_words) > 3 else []
    
    logger.info(f"⚠️ Using fallback parser:")
    logger.info(f"   • Main topic: {main_topic}")
    logger.info(f"   • Sub topics: {sub_topics}")
    logger.info(f"   • Search query: {search_query}")
    
    return {
        "main_topic": main_topic,
        "sub_topics": sub_topics,
        "search_query": search_query
    }


# Synchronous wrapper for non-async contexts
def parse_question_sync(question: str) -> dict:
    """
    Synchronous fallback parser (no LLM, uses simple extraction).
    Use this when async is not available or for quick parsing.
    """
    return _fallback_parse(question)

