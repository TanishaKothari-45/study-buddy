"""
Gemini Search Dimension Pipeline

A high-performance current affairs enrichment pipeline that uses 
Gemini's native Google Search tool to research, break down, and 
summarize contemporary answer dimensions for UPSC questions.
"""

import logging
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from ...gemini_core.gemini_client import GeminiClient
from ...core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class DimensionWithBullets(BaseModel):
    """A single answer dimension with research-backed bullets."""
    dimension: str = Field(
        description="Name of the answer dimension (e.g., 'Economic Impact', 'Legislative Framework')"
    )
    bullets: List[str] = Field(
        min_length=2,
        max_length=3,
        description="2-3 factual, UPSC-ready bullets (30-40 words each) based on search results"
    )

class GeminiSearchDimensionResult(BaseModel):
    """Complete dimension-based research result."""
    topic: str = Field(description="The original topic or question")
    dimensions: List[DimensionWithBullets] = Field(
        min_length=3,
        max_length=5,
        description="3-5 core dimensions with enrichment"
    )

# ============================================================================
# System Prompt
# ============================================================================

GEMINI_SEARCH_PIPELINE_PROMPT = """You are a UPSC Mains Research Assistant with access to live Google Search.

Your task is to analyze a given UPSC topic or question, conduct thorough research via Google Search, and provide a structured enrichment plan.

INSTRUCTIONS:
1. RESEARCH: Use Google Search to identify the most recent and relevant data, policies, reports, committees, or events related to the topic.
2. DIMENSIONS: Break the topic into 3–5 high-impact "Answer Dimensions". These should represent distinct sections of a high-quality UPSC answer.
3. BULLETS: For each dimension, generate 2–3 factual, high-signal bullets that enrich a student's answer.

BULLET QUALITY RULES:
- Signal-to-Noise: Every bullet must contain at least one hard fact (statistic, year, name of a report, data, committee, government bill, policy, or global event/body).
- Language: Use neutral, administrative, or journalistic UPSC-style language.
- Length: Each bullet MUST be between 20-30 words.
- Contemporariness: Prioritize events or data from the last 1–2 years. Focus on data from reports.

OUTPUT RULES:
- Return the results strictly according to the provided JSON schema.
- Do NOT provide meta-commentary or chat-style responses.
- Ensure dimensions are mutually exclusive and collectively exhaustive (MECE) for the given topic."""

# ============================================================================
# Main Pipeline Function
# ============================================================================

async def run_gemini_search_dimension_pipeline(
    topic: str,
    gemini_api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-pro"
) -> GeminiSearchDimensionResult:
    """
    Runs the Gemini Search-based dimension pipeline.
    
    Args:
        topic: The UPSC question or topic to research.
        gemini_api_key: User's API key.
        model_name: The Gemini model to use (default 1.5 Pro).
        
    Returns:
        GeminiSearchDimensionResult containing dimensions and bullets.
    """
    api_key = gemini_api_key or settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("No Gemini API key available for search pipeline")

    logger.info(f"🌐 Starting Gemini Search Pipeline for: {topic[:60]}...")
    
    # Initialize client (Pro is recommended for complex tool-use and research)
    client = GeminiClient(
        api_key=api_key,
        model_name=model_name,
        timeout=180.0 # Long timeout for research + generation
    )
    
    user_prompt = f"Conduct research and generate a dimension-based enrichment for this topic: {topic}"
    
    try:
        # Prompt-based JSON enforcement since tools + response_schema is unsupported
        json_instruction = "\n\nCRITICAL: You must output ONLY valid JSON that matches this structure:\n"
        json_instruction += '{"topic": "...", "dimensions": [{"dimension": "...", "bullets": ["...", "..."]}]}'
        
        response_text = await client.generate_response(
            user_prompt=user_prompt + json_instruction,
            system_prompt=GEMINI_SEARCH_PIPELINE_PROMPT,
            # response_schema=GeminiSearchDimensionResult, # Removed due to API limitation
            use_google_search=True,
            temperature=0.0
        )
        
        # Parse result
        import re
        clean_response = response_text.strip()
        # Find JSON block
        json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
        if json_match:
            clean_response = json_match.group(0)
        elif clean_response.startswith("```"):
            lines = clean_response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_response = "\n".join(lines)
            
        data = json.loads(clean_response)
        result = GeminiSearchDimensionResult(**data)
        
        total_bullets = sum(len(d.bullets) for d in result.dimensions)
        logger.info(f"✅ Gemini Search Pipeline complete: {len(result.dimensions)} dimensions, {total_bullets} bullets.")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Gemini Search Pipeline failed: {e}", exc_info=True)
        # Fallback empty result or re-raise based on policy
        return GeminiSearchDimensionResult(topic=topic, dimensions=[])

async def fetch_gemini_search_current_affairs_structured(
    topic: str,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Standardized wrapper for API/Frontend consumption.
    Formats the pipeline output into the standard current affairs structure.
    """
    result = await run_gemini_search_dimension_pipeline(topic, gemini_api_key=gemini_api_key)
    
    standardized_ca = []
    for dim in result.dimensions:
        for bullet in dim.bullets:
            standardized_ca.append({
                "summary": bullet,
                "type": "article",
                "dimension": dim.dimension
            })
            
    return {
        "current_affairs": standardized_ca,
        "metadata": {
            "topic": topic,
            "pipeline": "gemini_google_search_v1",
            "dimension_count": len(result.dimensions),
            "bullet_count": len(standardized_ca)
        }
    }
