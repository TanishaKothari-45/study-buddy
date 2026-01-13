# llm/keyword_parser.py
"""
LLM-based keyword extraction from UPSC-style topics.
Extracts 3-5 searchable keywords for news queries.
Now uses OpenAI Structured Output with Pydantic for guaranteed schema compliance.
"""

import json
import asyncio
from pydantic import BaseModel, Field
from typing import List

from backend.app.core.deps import get_redis_client
from ..config import KEYWORD_CACHE_TTL, REDIS_PREFIX
from .prompts import KEYWORD_EXTRACTION_PROMPT

# Pydantic model for structured output
class KeywordExtraction(BaseModel):
    """Structured output schema for keyword extraction."""
    keywords: List[str] = Field(
        min_items=3,
        max_items=5,
        description="3-5 searchable keywords for news queries"
    )

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
        _redis_client = get_redis_client()
    return _redis_client


def _cache_key(topic: str) -> str:
    return f"{REDIS_PREFIX}:keywords:{topic.lower().strip()}"


try:
    from app.utils.langsmith_tracer import trace_llm
except ImportError:
    # Fallback if app module not found (e.g. running standalone)
    def trace_llm(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

@trace_llm("mcp_keyword_extraction")
def get_keywords_sync(topic: str) -> list:
    """
    Synchronous keyword extraction with OpenAI Structured Output and caching.
    
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

    # Call OpenAI with Structured Output
    try:
        # Try structured output first (OpenAI beta API)
        print(f"🔍 Extracting keywords with Structured Output...")
        res = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": KEYWORD_EXTRACTION_PROMPT + topic}],
            response_format=KeywordExtraction,
            temperature=0.2
        )
        
        # Extract parsed keywords directly
        parsed_obj = res.choices[0].message.parsed
        parsed = parsed_obj.keywords
        print(f"✅ Extracted {len(parsed)} keywords via Structured Output")
        
    except AttributeError:
        # Fallback: beta API not available, use regular completion
        print(f"⚠️ Structured Output API not available, using legacy JSON parsing")
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": KEYWORD_EXTRACTION_PROMPT + topic}],
            max_tokens=100,
            temperature=0.2
        )
        
        # Extract content (backward compatible)
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

        # Parse JSON array (legacy fallback)
        try:
            parsed = json.loads(content)
        except:
            # Try to extract JSON substring
            start = content.find("[")
            end = content.rfind("]")
            if start == -1 or end == -1:
                # Ultimate fallback: split topic into words
                parsed = topic.lower().split()[:5]
                print(f"⚠️ Using fallback: split topic into words")
            else:
                parsed = json.loads(content[start:end+1])
        
        print(f"✅ Extracted {len(parsed)} keywords via legacy parsing")
    
    except Exception as e:
        # Ultimate fallback on any error
        print(f"❌ Keyword extraction failed: {e}")
        print(f"⚠️ Using ultimate fallback: topic word split")
        parsed = topic.lower().split()[:5]

    # Ensure we have 3-5 keywords
    if len(parsed) < 3:
        # Pad with topic words if needed
        topic_words = topic.lower().split()
        parsed.extend([w for w in topic_words if w not in parsed])
        parsed = parsed[:5]  # Limit to 5
    elif len(parsed) > 5:
        parsed = parsed[:5]  # Truncate to 5

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
        keywords: Keyword PHRASES from question parser (e.g., ["tribal agriculture drought", "Odisha", "rural livelihoods"])
                 Each keyword is already a meaningful phrase, not individual words
        topic: Original topic for fallback
    
    Returns:
        4 search queries for different angles
    """
    if not keywords:
        # Fallback: split topic into words
        keywords = [" ".join(topic.split()[:3])]
    
    # Keywords are already combined phrases from question parser
    # e.g., ["tribal agriculture drought", "Odisha", "rural livelihoods", "food security"]
    
    # Use first keyword phrase as primary (e.g., "tribal agriculture drought")
    primary = keywords[0] if len(keywords) > 0 else topic
    
    # Combine first 2 keyword phrases for core query (e.g., "tribal agriculture drought Odisha")
    core = " ".join(keywords[:2]) if len(keywords) >= 2 else primary
    
    # Diversified queries optimized for news APIs
    queries = [
        f"{core} India latest",                                    # India-specific (first 2 phrases)
        f"{primary} global report study data",                     # Global research (first phrase)
        f"{core} government scheme policy OR local initiatives",   # Policy angle (first 2 phrases)
        f"{primary} global solution measures",                     # Best practices (first phrase)
    ]
    
    return queries


async def get_keywords(topic: str) -> list:
    """Async wrapper for keyword extraction."""
    return await asyncio.to_thread(get_keywords_sync, topic)
