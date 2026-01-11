"""
Dimension-based Article Relevance Judge & Summarizer

Evaluates if an article is "strong" for UPSC and generates a focused bullet.
Replaces simple summarization with a more rigorous relevance check.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from ...gemini_core.gemini_client import GeminiClient
from ...core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models
# ============================================================================

class ArticleRelevance(BaseModel):
    """Judgment for a single article."""
    is_strong: bool = Field(description="Strong for UPSC enrichment")
    relevance_score: float = Field(description="Score 0.0 to 1.0")
    signal_type: Literal["data", "policy", "report", "case_study", "causal", "none"]
    summary_bullet: Optional[str] = Field(description="30-40 word bullet")

class BatchArticleRelevance(BaseModel):
    """Batch output for multiple articles."""
    results: List[ArticleRelevance] = Field(description="List of judgments in same order as input")


# ============================================================================
# System Prompt (Batch Version)
# ============================================================================

BATCH_SUMMARIZER_PROMPT = """You are a UPSC mains answer relevance judge.

Your task is to evaluate a LIST of news articles and decide which ones materially
strengthen a UPSC mains answer under their respective dimensions.

DEFINITION OF A STRONG ARTICLE:
An article is strong if it contains:
- Concrete data/statistics, Official reports/committees, Govt schemes/policies,
  Regional case studies, or Clear causal explanations.

INSTRUCTIONS:
1. Process each article in the provided list.
2. For each, judge if it is "strong" for its specific dimension.
3. If strong: generate a 30-40 word UPSC-ready factual bullet.
4. If NOT strong: mark is_strong=false, summary_bullet=null.

OUTPUT RULES:
- Return a JSON array of results in the EXACT same order as the input list.
- Keep bullets factual, neutral, and directly usable.
- Length: 30-40 words strictly."""


# ============================================================================
# Batch Processing Function
# ============================================================================

async def generate_dimension_bullets(
    articles: List[Dict[str, Any]],
    gemini_api_key: Optional[str] = None
) -> List[str]:
    """
    Process all articles in a single batch API call.
    Returns a flat list of summary bullets for articles judged as "STRONG".
    """
    # 1. Filter for articles with sufficient content signal
    # Only judge articles that were successfully scraped or have long snippets
    MIN_SIGNAL_LENGTH = 200
    valid_articles = []
    for a in articles:
        content = a.get("content") or a.get("description") or a.get("title") or ""
        if len(content) >= MIN_SIGNAL_LENGTH:
            valid_articles.append(a)
    
    if not valid_articles:
        logger.info("⚠️ No articles with sufficient content for batch judging")
        return []

    logger.info(f"✨ Sending BATCH relevance check for {len(valid_articles)} high-signal articles (1 API call)")

    input_text = "LIST OF ARTICLES TO JUDGE:\n\n"
    for i, a in enumerate(valid_articles, 1):
        dim = a.get("_dimension", "General")
        desc = a.get("_dimension_description", "")
        content = a.get("content") or a.get("description") or a.get("title") or ""
        
        input_text += f"--- ARTICLE {i} ---\n"
        input_text += f"DIMENSION: {dim}\n"
        input_text += f"DIMENSION DESC: {desc}\n"
        input_text += f"CONTENT: {content[:2000]}\n\n"

    # 2. Call Gemini (One Single Call)
    api_key = gemini_api_key or settings.GEMINI_API_KEY
    client = GeminiClient(api_key=api_key, model_name=settings.GEMINI_MODEL_FLASH)
    
    try:
        response_text = await client.generate_response(
            user_prompt=input_text,
            system_prompt=BATCH_SUMMARIZER_PROMPT,
            response_schema=BatchArticleRelevance,
            temperature=0.2
        )
        
        # 3. Parse and Extract Bullets
        import json
        clean_response = response_text.strip()
        if clean_response.startswith("```"):
            clean_response = "\n".join(clean_response.split("\n")[1:-1])
            
        batch_data = json.loads(clean_response)
        batch_result = BatchArticleRelevance(**batch_data)
        
        bullets = []
        for i, res in enumerate(batch_result.results):
            if res.is_strong and res.summary_bullet:
                bullets.append(res.summary_bullet)
                # Keep track for telemetry if needed
                if i < len(valid_articles):
                    valid_articles[i]["_is_strong"] = True
                    valid_articles[i]["_summary"] = res.summary_bullet
        
        logger.info(f"✅ Batch complete: {len(bullets)}/{len(valid_articles)} articles judged STRONG")
        return bullets
        
    except Exception as e:
        logger.error(f"❌ Batch summarization failed: {e}")
        return []
