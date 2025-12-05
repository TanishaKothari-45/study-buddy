"""
question_parser.py

LLM-powered question parser that extracts search-friendly terms from UPSC questions.
Converts verbose questions into optimized search queries for vector embedding retrieval.

Usage:
    from question_parser import parse_question_for_search
    
    result = await parse_question_for_search(
        question="Discuss climate change and its impact on agriculture and latest initiatives to mitigate it",
        gemini_client=client
    )
    # Returns: {
    #     "main_topic": "climate change",
    #     "sub_topics": ["impact on agriculture", "mitigation initiatives"],
    #     "search_query": "climate change impact agriculture mitigation initiatives"
    # }
"""

import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)

# System prompt for question parsing
QUESTION_PARSER_SYSTEM_PROMPT = """You are an expert at extracting key search terms from UPSC Geography questions.

Your task is to analyze a question and extract the core concepts that would be best for vector embedding search.

RULES:
1. Extract the MAIN TOPIC - the central subject of the question (1-3 words)
2. Extract SUB TOPICS - specific aspects, dimensions, or related concepts mentioned (2-5 items, each 1-4 words)
3. Remove filler words like "discuss", "explain", "examine", "critically", "analyze", "elaborate", "to what extent", etc.
4. Focus on NOUNS and KEY CONCEPTS that would appear in relevant documents
5. Combine into a search_query that is optimized for vector similarity search

OUTPUT FORMAT (JSON only, no markdown):
{
    "main_topic": "climate change",
    "sub_topics": ["impact on agriculture", "mitigation initiatives", "adaptation strategies"],
    "search_query": "climate change impact agriculture mitigation initiatives adaptation"
}

EXAMPLES:

Question: "Discuss the causes and impacts of increasing forest fires in India and suggest mitigation measures."
Output: {"main_topic": "forest fires India", "sub_topics": ["causes", "impacts", "mitigation measures"], "search_query": "forest fires India causes impacts mitigation measures"}

Question: "Critically examine the role of monsoons in shaping Indian agriculture. What are the recent trends?"
Output: {"main_topic": "monsoons Indian agriculture", "sub_topics": ["role", "recent trends", "impact"], "search_query": "monsoons Indian agriculture role trends impact"}

Question: "To what extent has urbanization affected the groundwater resources in India? Suggest remedial measures."
Output: {"main_topic": "urbanization groundwater India", "sub_topics": ["effects", "remedial measures", "depletion"], "search_query": "urbanization groundwater India effects depletion remedial measures"}
"""


from .langsmith_tracer import trace_gemini

@trace_gemini("question_parser")
async def parse_question_for_search(
    question: str,
    gemini_client,
    model_name: str = "gemini-2.5-pro"
) -> dict:
    """
    Parse a UPSC question to extract search-friendly terms for vector retrieval.
    
    Args:
        question: The full question text
        gemini_client: GeminiClient instance
        model_name: Gemini model to use (default: gemini-2.5-pro)
    
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
    
    user_prompt = f"""Extract search terms from this UPSC question:

Question: {question}

Return ONLY valid JSON with main_topic, sub_topics, and search_query fields. No markdown, no explanation."""

    try:
        logger.info(f"🔍 Parsing question for search terms: {question[:80]}...")
        
        # Store original model and temporarily switch if needed
        original_model = gemini_client.model_name
        gemini_client.model_name = model_name
        
        response = await gemini_client.generate_response(
            user_prompt=user_prompt,
            system_prompt=QUESTION_PARSER_SYSTEM_PROMPT,
            temperature=0.0,  # Deterministic output
            max_retries=2
        )
        
        # Restore original model
        gemini_client.model_name = original_model
        
        # Clean response - remove markdown code blocks if present
        response_text = response.strip()
        if response_text.startswith("```"):
            # Remove markdown code block
            lines = response_text.split("\n")
            # Remove first line (```json) and last line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
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

