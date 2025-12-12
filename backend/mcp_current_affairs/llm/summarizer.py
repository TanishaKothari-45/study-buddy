# llm/summarizer.py
"""
LLM-based summarization for articles and editorials.
Uses batch API call for efficiency.
"""

import json
from .prompts import BATCH_SUMMARY_PROMPT, ARTICLE_ONE_LINER_PROMPT

# Build a Gemini client (optionally with user API key)
def _get_gemini_client(api_key: str = None):
    # Import Gemini client and settings from backend app (shares user/system key logic)
    from app.gemini_core.gemini_client import GeminiClient
    from app.core.config import settings
    import logging
    
    key_to_use = api_key or settings.GEMINI_API_KEY
    # Use Gemini Flash for summaries; avoid OpenAI small model
    model_to_use = settings.GEMINI_MODEL_FLASH or "gemini-1.5-flash"
    logger = logging.getLogger(__name__)
    logger.info(f"[SUMMARIZER] Using Gemini model={model_to_use} key={'user-provided' if api_key else 'env/system'}")
    return GeminiClient(api_key=key_to_use, model_name=model_to_use)


def _build_articles_prompt(article_leads: list) -> str:
    """
    Build a structured prompt for article summarization only.
    """
    articles_json = json.dumps({"articles": article_leads}, ensure_ascii=False)
    return f"""{ARTICLE_ONE_LINER_PROMPT}

INPUT (multiple articles):
{articles_json}

OUTPUT: Return ONLY a JSON array of summaries (one per article):
["summary 1...", "summary 2...", ...]
"""


def summarize_articles_only(article_leads: list, api_key: str = None) -> list:
    """
    Synchronous batch summarization for articles only.
    
    Args:
        article_leads: List of article text extracts
    
    Returns:
        List of article summaries
    """
    if not article_leads:
        return []
    
    client = _get_gemini_client(api_key)
    prompt = _build_articles_prompt(article_leads)

    # Call Gemini Flash (deterministic, concise)
    # generate_response is async; run in event loop safely
    import asyncio
    text = asyncio.run(client.generate_response(
        user_prompt=prompt,
        system_prompt="You are a concise factual summarizer.1-2 sentences describing core of point for an UPSC Mains answer. Return JSON only. Keep each summary under ~60 words.",
        temperature=0.1,
    ))

    # Extract JSON array from response
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        # Fallback: try to extract JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_text = text[start:end+1]
            parsed = json.loads(json_text)
            article_summaries = parsed.get("article_summaries", [])
        else:
            raise ValueError(f"Summarizer did not return valid JSON: {text[:300]}")
    else:
        json_text = text[start:end+1]
        article_summaries = json.loads(json_text)

    # Pad if needed
    if len(article_summaries) < len(article_leads):
        article_summaries += ["Summary unavailable"] * (len(article_leads) - len(article_summaries))

    return article_summaries


# DEPRECATED: Keep for backward compatibility if needed
def summarize_articles_and_editorial_sync(
    article_leads: list, 
    editorial_extract: str
) -> tuple:
    """
    DEPRECATED: Use summarize_articles_only instead.
    Editorial functionality has been removed from the pipeline.
    """
    summaries = summarize_articles_only(article_leads)
    return summaries, None
