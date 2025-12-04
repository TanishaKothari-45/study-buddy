# llm/keyword_parser.py
"""
LLM-based keyword extraction from UPSC-style topics.
Extracts 3-5 searchable keywords for news queries.
"""

import json
import asyncio
from ..config import KEYWORD_CACHE_TTL, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, REDIS_PREFIX
from .prompts import KEYWORD_EXTRACTION_PROMPT

# Lazy-loaded clients
_openai_client = None
_redis_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client

def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST, 
            port=REDIS_PORT, 
            db=REDIS_DB, 
            password=REDIS_PASSWORD, 
            decode_responses=True
        )
    return _redis_client


def _cache_key(topic: str) -> str:
    return f"{REDIS_PREFIX}:keywords:{topic.lower().strip()}"


def get_keywords_sync(topic: str) -> list:
    """
    Synchronous keyword extraction with caching.
    
    Args:
        topic: User's UPSC-style question/topic
    
    Returns:
        List of 3-5 keywords for search queries
    """
    key = _cache_key(topic)
    r = _get_redis_client()
    client = _get_openai_client()
    
    # Check cache
    try:
        cached = r.get(key)
        if cached:
            print(f"📦 Keywords from cache: {key}")
            return json.loads(cached)
    except Exception as e:
        print(f"⚠️ Redis get error: {e}")

    # Call OpenAI
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": KEYWORD_EXTRACTION_PROMPT + topic}],
        max_tokens=100,
        temperature=0.2
    )

    # Extract content
    try:
        choice = res.choices[0]
        if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
            content = choice.message.content
        elif isinstance(choice, dict) and "message" in choice:
            content = choice["message"]["content"]
        else:
            content = str(choice)
    except Exception as e:
        raise RuntimeError(f"Unexpected OpenAI response: {e}")

    # Parse JSON array
    try:
        parsed = json.loads(content)
    except:
        # Try to extract JSON substring
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1:
            # Fallback: split topic into words
            parsed = topic.lower().split()[:5]
        else:
            parsed = json.loads(content[start:end+1])

    # Cache result
    try:
        r.setex(key, KEYWORD_CACHE_TTL, json.dumps(parsed))
    except Exception as e:
        print(f"⚠️ Redis set error: {e}")

    return parsed


def build_search_queries(keywords: list, topic: str) -> list:
    """
    Build 4 diversified search queries from keywords.
    
    Args:
        keywords: Extracted keywords (3-5)
        topic: Original topic for fallback
    
    Returns:
        4 search queries for different angles
    """
    # Use first 2 keywords as core query
    core = " ".join(keywords[:2]) if keywords else topic
    # Use first keyword alone for broader matches
    primary = keywords[0] if keywords else topic.split()[0]
    
    # Broader queries for better coverage
    queries = [
        f"{core} India latest",                                                  # India-specific current
        f"{primary} global report study data",                                   # Research/data angle
        f"{core} government scheme policy OR local initiatives",                 # Policy angle  
        f"{primary} global solution measures",                                   # Best practices
    ]
    
    return queries


async def get_keywords(topic: str) -> list:
    """Async wrapper for keyword extraction."""
    return await asyncio.to_thread(get_keywords_sync, topic)
