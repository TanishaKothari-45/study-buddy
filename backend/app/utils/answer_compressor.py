"""
answer_compressor.py
Utility to compress overlong answers while preserving key facts and structure.
Can be dropped or modified without affecting main answer generation logic.
"""

import re
import logging
from typing import Optional, Any

logger = logging.getLogger("answer_compressor")

COMPRESSION_PROMPT = """You are an expert editor. Condense the following answer to at most {max_words} words while preserving:
- All key facts and evidence (reports, data, examples)
- The original tone and voice (formal/analytical)
- The IBC structure (intro, body with sub-headings, conclusion)
- All Mermaid diagrams and maps EXACTLY as they appear

Rules:
1. Prefer concise rephrasing and combining sentences over deleting content.
2. Shorten examples first, then remove least important supporting sentences.
3. Keep all sub-headings (### format) and maintain bullet format with dash (-).
4. PRESERVE bold formatting (**text**) in bullet point headings - the main idea of each bullet must stay bold.
5. Copy all ```mermaid code blocks EXACTLY as they appear, character-for-character.
6. CRITICAL: Copy all map images EXACTLY as they appear. Maps look like: ![Map Title](data:image/svg+xml;base64,LONG_STRING). Copy the ENTIRE markdown image including the full base64 string without any modifications, truncation, or replacement.
7. Do NOT convert map images back to JSON or any other format. Keep them as markdown images.
8. Return only the final condensed answer, no commentary or explanation.

Original answer (word count = {actual_words}):

{original_answer}
"""


def count_words_excluding_visuals(text: str) -> int:
    """
    Count words excluding Mermaid diagrams, code blocks, and images.
    """
    cleaned_text = text
    cleaned_text = re.sub(r'```mermaid[\s\S]*?```', '', cleaned_text)
    cleaned_text = re.sub(r'```map-json[\s\S]*?```', '', cleaned_text)
    cleaned_text = re.sub(r'```[\s\S]*?```', '', cleaned_text)
    cleaned_text = re.sub(r'!\[[^\]]*\]\(data:image[^\)]+\)', '', cleaned_text)
    cleaned_text = re.sub(r'data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+', '', cleaned_text)
    return len(cleaned_text.split())


async def compress_answer(
    original_answer: str,
    target_word_count: int,
    gemini_client: Any,
    threshold_ratio: float = 1.4
) -> Optional[str]:
    """
    Compress an answer if it exceeds the threshold ratio of target word count.
    
    Args:
        original_answer: The original generated answer
        target_word_count: The user's target word count
        gemini_client: GeminiClient instance for LLM calls
        threshold_ratio: Only compress if answer exceeds target * threshold_ratio (default 1.4 = 140%)
    
    Returns:
        Compressed answer string if compression was applied, None if no compression needed
    """
    actual_words = count_words_excluding_visuals(original_answer)
    max_acceptable = int(target_word_count * threshold_ratio)
    
    # Check if compression is needed
    if actual_words <= max_acceptable:
        logger.info(f"📝 No compression needed: {actual_words} words <= {max_acceptable} max acceptable")
        return None
    
    logger.info(f"🗜️ Compressing answer: {actual_words} words -> target ~{target_word_count} words")
    
    # Calculate max words for compression (target + 20% buffer)
    max_words = int(target_word_count * 1.2)
    
    # Build compression prompt
    prompt = COMPRESSION_PROMPT.format(
        max_words=max_words,
        actual_words=actual_words,
        original_answer=original_answer
    )
    
    try:
        compressed = await gemini_client.generate_response(
            user_prompt=prompt,
            system_prompt="You are a concise editor. Return only the compressed answer.",
            temperature=0.1,  # Low temperature for consistent compression
            max_retries=2
        )
        
        compressed = compressed.strip()
        compressed_words = count_words_excluding_visuals(compressed)
        
        logger.info(f"✅ Compression complete: {actual_words} -> {compressed_words} words ({round(compressed_words/actual_words*100)}% of original)")
        
        return compressed
        
    except Exception as e:
        logger.error(f"❌ Compression failed: {e}")
        return None
