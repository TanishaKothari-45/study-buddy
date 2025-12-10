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
- All placeholder markers like <<MERMAID_0>>, <<MAP_0>> EXACTLY as they appear at their original positions

Rules:
1. Prefer concise rephrasing and combining sentences over deleting content.
2. Shorten examples first, then remove least important supporting sentences.
3. Keep all sub-headings (### format) and maintain bullet format with dash (-).
4. PRESERVE bold formatting (**text**) in bullet point headings - the main idea of each bullet must stay bold.
5. KEEP all <<PLACEHOLDERS>> exactly where they are. Do not remove or move them.
6. Return only the final condensed answer, no commentary or explanation.

Original answer (word count = {actual_words}):

{original_answer}
"""


def extract_visuals(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace visual blocks with placeholders to save tokens.
    Returns: (cleaned_text, replacements_dict)
    """
    replacements = {}
    counter = 0
    
    # 1. Mermaid blocks
    def replace_mermaid(match):
        nonlocal counter
        placeholder = f"<<MERMAID_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"
        
    text = re.sub(r'```mermaid[\s\S]*?```', replace_mermaid, text)
    
    # 2. Map blocks (json)
    def replace_map_json(match):
        nonlocal counter
        placeholder = f"<<MAP_JSON_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"

    text = re.sub(r'```map-json[\s\S]*?```', replace_map_json, text)

    # 3. Base64 Images (Maps)
    def replace_image(match):
        nonlocal counter
        placeholder = f"<<IMAGE_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"

    # Match markdown images with data URI
    text = re.sub(r'!\[[^\]]*\]\(data:image[^\)]+\)', replace_image, text)
    
    return text, replacements


def restore_visuals(text: str, replacements: dict[str, str]) -> str:
    """
    Restore original visual blocks from placeholders.
    """
    for placeholder, content in replacements.items():
        # Replace placeholder with original content
        # Use regex to ensure we catch it even if slightly malformed by LLM
        text = text.replace(placeholder, content)
        
    return text


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
    
    # Extract visuals to save tokens
    text_to_compress, replacements = extract_visuals(original_answer)
    
    # Build compression prompt
    prompt = COMPRESSION_PROMPT.format(
        max_words=max_words,
        actual_words=actual_words,
        original_answer=text_to_compress
    )
    
    try:
        compressed_text = await gemini_client.generate_response(
            user_prompt=prompt,
            system_prompt="You are a concise editor. Return only the compressed answer.",
            temperature=0.1,  # Low temperature for consistent compression
            max_retries=2
        )
        
        compressed_text = compressed_text.strip()
        
        # Restore visuals
        final_answer = restore_visuals(compressed_text, replacements)
        
        compressed_words = count_words_excluding_visuals(final_answer)
        
        logger.info(f"✅ Compression complete: {actual_words} -> {compressed_words} words ({round(compressed_words/actual_words*100)}% of original)")
        
        return final_answer
        
    except Exception as e:
        logger.error(f"❌ Compression failed: {e}")
        return None

