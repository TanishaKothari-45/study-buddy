"""
Dimension Query Planner

LLM-based question analysis that breaks UPSC questions into
answer-oriented dimensions with news-style search queries.

Uses GeminiClient for structured output generation.
"""

import logging
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

from ...gemini_core.gemini_client import GeminiClient
from ...core.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class DimensionQuery(BaseModel):
    """A single answer dimension with search queries and priority."""
    dimension: str = Field(
        description="Name of the answer dimension (e.g., 'Constitutional Framework')"
    )
    dimension_description: str = Field(
        description="Brief description of what this dimension covers"
    )
    priority: Literal["high", "medium", "low"] = Field(
        description="Priority level for current affairs enrichment (high/medium/low)"
    )
    search_queries: List[str] = Field(
        min_length=2,
        max_length=3,
        description="2-3 news-style search queries for this dimension"
    )


class DimensionQueryPlan(BaseModel):
    """Complete dimension plan for a UPSC question."""
    question: str = Field(
        description="The original UPSC question"
    )
    dimensions: List[DimensionQuery] = Field(
        min_length=4,
        max_length=7,
        description="4-7 answer-oriented dimensions"
    )


# ============================================================================
# System Prompt
# ============================================================================

DIMENSION_PLANNER_PROMPT = """You are a UPSC retrieval planner.

Your task is to analyze a UPSC question and break it into
answer-oriented static dimensions.

Each dimension must represent a distinct section or paragraph
that would appear in a high-quality UPSC answer.
Dimensions must be syllabus-aligned, mutually distinct, and
together fully address the demand of the question.

For each dimension, generate 2–3 search queries written in
journalistic or news-reporting language.
Search queries must reflect how the topic is discussed in news,
reports, or policy articles — not exam-oriented phrasing.

For each dimension, assign a priority level based on how essential
current affairs enrichment is for a high-quality UPSC mains answer.

Priority rules:
- high: Contemporary data, reports, policies, or events are strongly expected.
- medium: Contemporary examples are useful but optional.
- low: Static syllabus explanation is generally sufficient.

Priority reflects answer-writing value, not real-world importance.

Rules:
- Identify 4–7 core answer dimensions only.
- Each dimension must be independently discussable.
- Do NOT include question words (e.g., discuss, assess, examine).
- Do NOT summarize or explain beyond the required fields.
- Do NOT generate current affairs content.
- Output MUST strictly follow the provided JSON schema.
- No extra text, no markdown, no explanations."""


# ============================================================================
# Main Function
# ============================================================================

async def generate_dimension_plan(
    question: str,
    gemini_api_key: Optional[str] = None,
    use_pro_model: bool = False
) -> DimensionQueryPlan:
    """
    Generate a dimension-based query plan for a UPSC question.
    
    Args:
        question: The UPSC question to analyze
        gemini_api_key: User's Gemini API key (falls back to system key)
        use_pro_model: If True, use Gemini Pro; else use Flash (default)
    
    Returns:
        DimensionQueryPlan with dimensions and search queries
    
    Example:
        plan = await generate_dimension_plan(
            "Discuss the impact of climate change on tribal agriculture in India."
        )
        for dim in plan.dimensions:
            print(f"Dimension: {dim.dimension}")
            print(f"Queries: {dim.search_queries}")
    """
    # Select API key (user key preferred)
    api_key = gemini_api_key or settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("No Gemini API key available")
    
    # Select model (Flash is cheaper, Pro is better for complex reasoning)
    # Flash should handle this well since it's structured output
    model_name = settings.GEMINI_MODEL_PRO if use_pro_model else settings.GEMINI_MODEL_FLASH
    if not model_name:
        model_name = "gemini-2.0-flash" if not use_pro_model else "gemini-2.5-pro"
    
    logger.info(f"📐 Generating dimension plan using {model_name}")
    logger.info(f"   Question: {question[:80]}...")
    
    # Initialize Gemini client
    client = GeminiClient(
        api_key=api_key,
        model_name=model_name,
        timeout=60.0  # Shorter timeout for this simple task
    )
    
    # Build user prompt
    user_prompt = f"Analyze this UPSC question and generate dimension plan:\n\n{question}"
    
    try:
        # Call Gemini with structured output schema
        response = await client.generate_response(
            user_prompt=user_prompt,
            system_prompt=DIMENSION_PLANNER_PROMPT,
            response_schema=DimensionQueryPlan,
            temperature=0.2  # Low temperature for consistent, structured output
        )
        
        # Parse JSON response into Pydantic model
        import json
        
        # Clean response (remove markdown code blocks if present)
        clean_response = response.strip()
        if clean_response.startswith("```"):
            # Remove markdown code block
            lines = clean_response.split("\n")
            clean_response = "\n".join(lines[1:-1])
        
        plan_data = json.loads(clean_response)
        plan = DimensionQueryPlan(**plan_data)
        
        logger.info(f"✅ Generated {len(plan.dimensions)} dimensions")
        for i, dim in enumerate(plan.dimensions, 1):
            logger.info(f"   {i}. {dim.dimension} [{dim.priority}] ({len(dim.search_queries)} queries)")
        
        return plan
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse dimension plan JSON: {e}")
        logger.error(f"   Response: {response[:500]}")
        raise ValueError(f"Invalid JSON response from Gemini: {e}")
    except Exception as e:
        logger.error(f"❌ Dimension plan generation failed: {e}")
        raise


# ============================================================================
# Utility Functions
# ============================================================================

def get_all_search_queries(plan: DimensionQueryPlan) -> List[str]:
    """
    Extract all search queries from a dimension plan.
    
    Args:
        plan: DimensionQueryPlan object
    
    Returns:
        Flat list of all search queries
    """
    queries = []
    for dim in plan.dimensions:
        queries.extend(dim.search_queries)
    return queries


def get_dimension_names(plan: DimensionQueryPlan) -> List[str]:
    """
    Extract just the dimension names from a plan.
    
    Args:
        plan: DimensionQueryPlan object
    
    Returns:
        List of dimension names
    """
    return [dim.dimension for dim in plan.dimensions]
