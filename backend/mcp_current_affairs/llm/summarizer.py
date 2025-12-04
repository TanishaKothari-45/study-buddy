# llm/summarizer.py
"""
LLM-based summarization for articles and editorials.
Uses batch API call for efficiency.
"""

import json
from .prompts import BATCH_SUMMARY_PROMPT

# Lazy-loaded client
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


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


def summarize_articles_only(article_leads: list) -> list:
    """
    Synchronous batch summarization for articles only.
    
    Args:
        article_leads: List of article text extracts
    
    Returns:
        List of article summaries
    """
    if not article_leads:
        return []
    
    client = _get_openai_client()
    prompt = _build_articles_prompt(article_leads)

    # Call OpenAI
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,  # Sufficient for 3-4 articles
        temperature=0.3   # Lower for more factual output
    )

    # Parse response
    text = None
    try:
        choice = resp.choices[0]
        if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
            text = choice.message.content
        elif isinstance(choice, dict) and "message" in choice:
            text = choice["message"]["content"]
        else:
            text = str(choice)
    except Exception as e:
        raise RuntimeError(f"Unexpected OpenAI response: {e}")

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
