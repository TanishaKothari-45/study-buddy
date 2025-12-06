"""
question_parser.py

LLM-powered question parser that extracts search-friendly terms from UPSC questions.
Converts verbose questions into optimized search queries for vector embedding retrieval.
Now uses GPT-4o-mini with Redis caching for better performance.

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

logger = logging.getLogger(__name__)

# Redis cache for parsed questions
try:
    from .cache_manager import get_cache_manager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    logger.warning("⚠️ Cache manager not available for question parser")

# System prompt for question parsing
QUESTION_PARSER_SYSTEM_PROMPT = """
You extract search-focused keywords from UPSC questions.

TASK:
- MAIN TOPIC: 1–3 word core subject.
- SUB TOPICS: 2–5 short aspects (1–4 words each).
- Remove filler verbs (discuss, examine, critically, etc.).
- Keep only nouns/concepts useful for vector search.
- SEARCH_QUERY = main_topic + sub_topics (space-separated).

Return ONLY JSON:
{
 "main_topic": "...",
 "sub_topics": ["...", "..."],
 "search_query": "..."
}

Examples:
Q: "Causes and impacts of forest fires in India; suggest mitigation measures."
→ {"main_topic":"forest fires India","sub_topics":["causes","impacts","mitigation"],"search_query":"forest fires India causes impacts mitigation"}

Q: "Role of monsoons in shaping Indian agriculture; recent trends."
→ {"main_topic":"monsoons Indian agriculture","sub_topics":["role","recent trends","impact"],"search_query":"monsoons Indian agriculture role recent trends impact"}

Q: "Urbanization affecting groundwater in India; remedial measures."
→ {"main_topic":"urbanization groundwater India","sub_topics":["effects","depletion","remedial measures"],"search_query":"urbanization groundwater India effects depletion remedial measures"}
"""



from .langsmith_tracer import trace_llm

@trace_llm("question_parser")
async def parse_question_for_search(
    question: str,
    openai_api_key: Optional[str] = None
) -> dict:
    """
    Parse a UPSC question to extract search-friendly terms for vector retrieval.
    Uses GPT-4o-mini with Redis caching for speed.
    
    Args:
        question: The full question text
        openai_api_key: OpenAI API key (optional, will use env var if not provided)
    
    Returns:
        dict with keys:
            - main_topic: str - central subject (1-3 words)
            - sub_topics: list[str] - specific aspects (2-5 items)
            - search_query: str - combined query optimized for embedding
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
    
    user_prompt = f"""Extract search terms from this UPSC question:

Question: {question}

Return ONLY valid JSON with main_topic, sub_topics, and search_query fields. No markdown, no explanation."""

    try:
        logger.info(f"🔍 [CACHE MISS] Parsing question with GPT-4o-mini: {question[:80]}...")
        
        # Use GPT-4o-mini for faster parsing
        client = AsyncOpenAI(api_key=openai_api_key)
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": QUESTION_PARSER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,  # Deterministic output
            top_p=0.0,  # No nucleus sampling - fully deterministic
            max_tokens=200  # Short response expected
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean response - remove markdown code blocks if present
        if response_text.startswith("```"):
            # Remove markdown code block
            lines = response_text.split("\n")
            # Remove first line (```json) and last line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response_text = "\n".join(lines)
            response_text = "\n".join(lines)
        
        # Parse JSON response
        result = json.loads(response_text)
        
        # Validate required fields
        main_topic = result.get("main_topic", "")
        sub_topics = result.get("sub_topics", [])
        search_query = result.get("search_query", "")
        
        # If search_query is empty, construct it from main_topic and sub_topics
        if not search_query and (main_topic or sub_topics):
            search_query = f"{main_topic} {' '.join(sub_topics)}".strip()
        
        parsed_result = {
            "main_topic": main_topic,
            "sub_topics": sub_topics if isinstance(sub_topics, list) else [sub_topics],
            "search_query": search_query
        }
        
        logger.info(f"✅ Parsed question:")
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
        
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Failed to parse JSON response: {e}")
        logger.warning(f"   Raw response: {response[:200]}...")
        
        # Fallback: use simple extraction
        return _fallback_parse(question)
        
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

