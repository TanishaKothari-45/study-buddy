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


def _build_batch_prompt(article_leads: list, editorial_extract: str) -> str:
    """
    Build a structured prompt for batch summarization.
    """
    content = {
        "articles": article_leads,
        "editorial": editorial_extract
    }
    return BATCH_SUMMARY_PROMPT + "\n\nINPUT:\n" + json.dumps(content, ensure_ascii=False)


def summarize_articles_and_editorial_sync(
    article_leads: list, 
    editorial_extract: str
) -> tuple:
    """
    Synchronous batch summarization.
    
    Args:
        article_leads: List of article text extracts
        editorial_extract: Editorial text extract or None
    
    Returns:
        (article_summaries: list[str], editorial_summary: str or None)
    """
    if not article_leads and not editorial_extract:
        return [], None
    
    client = _get_openai_client()
    prompt = _build_batch_prompt(article_leads, editorial_extract)

    # Call OpenAI
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,  # Increased for longer summaries
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

    # Extract JSON from response
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Summarizer did not return valid JSON: {text[:300]}")

    json_text = text[start:end+1]
    parsed = json.loads(json_text)

    article_summaries = parsed.get("article_summaries", [])
    editorial_summary = parsed.get("editorial_summary", None)

    # Pad if needed
    if len(article_summaries) < len(article_leads):
        article_summaries += ["Summary unavailable"] * (len(article_leads) - len(article_summaries))

    return article_summaries, editorial_summary
