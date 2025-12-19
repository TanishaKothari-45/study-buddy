"""
answer_compressor.py
Utility to compress overlong answers while preserving key facts and structure.
Can be dropped or modified without affecting main answer generation logic.
"""

import re
import logging
import asyncio
from typing import Optional, Any
from .text_processing import count_words_excluding_visuals

logger = logging.getLogger("answer_compressor")


COMPRESSION_PROMPT = """You are an expert editor. Condense the following answer to at most {max_words} words while preserving:
- All key facts and evidence (reports, data, examples)
- The original tone and voice (formal/analytical)
- The IBC structure (intro, body with sub-headings, conclusion)
- Try to Keep intro and conclusion impactful even if concise
- All placeholder markers (<<MERMAID_X>>, <<IMAGE_X>>, <<MAP_JSON_X>>, <<CODE_X>>) EXACTLY as they appear at their original positions

Impact Rules for INTRO & CONCLUSION:
- INTRO must retain its core framing element (definition OR data point/report OR relevant current context OR richness of the definition). Do NOT weaken the opening idea. Do NOT compress it into a dry factual note. Retain the opening idea as it is.
- CONCLUSION must remain a meaningful 1–2 line synthesis with an optimistic governance-aligned or significance-oriented tone. Do NOT compress it into a dry factual note. Do NOT weaken the closing idea.Retain the closing idea paragraph as it is.
Rules:
1. Prefer concise rephrasing and combining sentences over deleting content.
2. Shorten examples first, then remove least important supporting sentences.
3. Keep all sub-headings (### format) and maintain bullet format with dash (-).
4. PRESERVE bold formatting (**text**) in bullet point headings - the main idea of each bullet must stay bold.
5. KEEP all <<PLACEHOLDERS>> exactly where they are. Do not remove or move them.
6. Keep table structure as it is.
7. Return only the final condensed answer, no commentary or explanation.
8. NEVER DROP QUALIFYING KEYWORDS: The specific qualifiers and domain terms in each bullet are scoring keywords. NEVER remove them to save words.
   Examples of keywords that MUST be kept exactly:
   - "skilled and unskilled workers" (NOT just "workers")
   - "mining and manufacturing" (NOT dropped entirely)
   - "raw materials" (NOT just "materials")
   - "labour-intensive processing" (NOT just "processing")
   
8. WHAT TO SHORTEN INSTEAD: Only shorten proper nouns and filler words, NOT domain keywords.
   - Shorten: "Uttar Pradesh" → "UP", "Madhya Pradesh" → "MP", "National Institution for Transforming India" → "NITI Aayog"
   - Remove filler: "It is important to note that" → remove entirely
   - Combine: Two sentences with same idea → one sentence
   
   GOOD: "Labour-intensive processing of raw materials creates direct jobs for skilled and unskilled workers, like sugar industry in UP."
   BAD: "Labour-intensive processing creates jobs in the sugar industry in Uttar Pradesh and Maharashtra."
   → BAD loses: "raw materials", "direct", "skilled and unskilled workers"
   
   GOOD: "Industries generate significant employment in mining and manufacturing sectors."
   BAD: "Industries generate significant employment."
   → BAD loses: "in mining and manufacturing sectors"


Original answer (word count = {actual_words}):

{original_answer}
"""


def extract_visuals(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace visual blocks with placeholders to save tokens.
    Extracts: Mermaid diagrams, map-json blocks, base64 images (any mime type), and regular code blocks.
    Returns: (cleaned_text, replacements_dict)
    """
    replacements = {}
    counter = 0
    
    # 1. Mermaid blocks (diagrams are visual, not text)
    def replace_mermaid(match):
        nonlocal counter
        placeholder = f"<<MERMAID_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"
        
    text = re.sub(r'```mermaid[\s\S]*?```', replace_mermaid, text)
    
    # 2. Map blocks (json spec - not useful for compression)
    def replace_map_json(match):
        nonlocal counter
        placeholder = f"<<MAP_JSON_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"

    text = re.sub(r'```map-json[\s\S]*?```', replace_map_json, text)

    # 3. Base64 Images (Maps/Diagrams) - handle ALL image mime types
    # Matches: ![alt](data:image/png;base64,...), ![alt](data:image/svg+xml;base64,...), etc.
    def replace_image(match):
        nonlocal counter
        placeholder = f"<<IMAGE_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"

    # Match markdown images with data URI (any image mime type: png, svg+xml, jpeg, webp, etc.)
    text = re.sub(r'!\[[^\]]*\]\(data:image/[^;]+;base64,[A-Za-z0-9+/=]+\)', replace_image, text)
    
    # 4. Regular code blocks (not mermaid/map-json) - also save tokens
    # Example: ```python, ```javascript, ```json, etc.
    def replace_code(match):
        nonlocal counter
        placeholder = f"<<CODE_{counter}>>"
        replacements[placeholder] = match.group(0)
        counter += 1
        return f"\n\n{placeholder}\n\n"
    
    # Match any remaining code blocks that weren't caught above
    text = re.sub(r'```[\s\S]*?```', replace_code, text)

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




async def compress_answer(
    original_answer: str,
    target_word_count: int,
    gemini_client: Any,
    threshold_ratio: float = 1.5,
    compression_target_ratio: float = 1.3
) -> Optional[str]:
    """
    Compress an answer if it exceeds the threshold ratio of target word count.
    Uses two-tier strategy: trigger at threshold_ratio, compress to compression_target_ratio.
    
    Args:
        original_answer: The original generated answer
        target_word_count: The user's target word count
        gemini_client: GeminiClient instance for LLM calls
        threshold_ratio: Only compress if answer exceeds target * threshold_ratio (default 1.5 = 150%)
        compression_target_ratio: Compress down to target * compression_target_ratio (default 1.3 = 130%)
    
    Returns:
        Compressed answer string if compression was applied, None if no compression needed
    """
    actual_words = count_words_excluding_visuals(original_answer)
    max_acceptable = int(target_word_count * threshold_ratio)
    
    # Check if compression is needed
    if actual_words <= max_acceptable:
        logger.info(f"📝 No compression needed: {actual_words} words <= {max_acceptable} max acceptable ({threshold_ratio}x target)")
        return None
    
    # Calculate compression target (lower than trigger threshold)
    compression_target = int(target_word_count * compression_target_ratio)
    
    logger.info(f"🗜️ Compressing answer: {actual_words} words -> target ~{compression_target} words ({compression_target_ratio}x)")
    logger.info(f"   • Trigger threshold: {max_acceptable} words ({threshold_ratio}x)")
    logger.info(f"   • Compression target: {compression_target} words ({compression_target_ratio}x)")
    
    # Extract visuals to save tokens
    text_to_compress, replacements = extract_visuals(original_answer)
    
    # Calculate and log token savings from visual extraction
    original_size = len(original_answer)
    cleaned_size = len(text_to_compress)
    bytes_saved = original_size - cleaned_size
    
    # Count different types of visuals extracted
    mermaid_count = sum(1 for k in replacements.keys() if k.startswith("<<MERMAID_"))
    image_count = sum(1 for k in replacements.keys() if k.startswith("<<IMAGE_"))
    map_json_count = sum(1 for k in replacements.keys() if k.startswith("<<MAP_JSON_"))
    code_count = sum(1 for k in replacements.keys() if k.startswith("<<CODE_"))
    
    logger.info(
        f"🎨 [VISUAL EXTRACTION] Extracted {len(replacements)} visual elements:\n"
        f"   • Mermaid diagrams: {mermaid_count}\n"
        f"   • Map JSON blocks: {map_json_count}\n"
        f"   • Base64 images: {image_count}\n"
        f"   • Code blocks: {code_count}\n"
    )
    logger.info(f"📊 [TOKEN OPTIMIZATION]:")
    logger.info(f"   • Original size: {original_size:,} chars (~{original_size//4:,} tokens)")
    logger.info(f"   • Cleaned size: {cleaned_size:,} chars (~{cleaned_size//4:,} tokens)")
    logger.info(f"   • ⚡ Saved: {bytes_saved:,} chars (~{bytes_saved//4:,} tokens, {bytes_saved*100//original_size if original_size > 0 else 0}% reduction)")
    logger.info(f"🔎 [TEXT TO COMPRESS] First 500 chars:\n{text_to_compress[:500]}...")
    
    # Build compression prompt
    prompt = COMPRESSION_PROMPT.format(
        max_words=compression_target,  # Use compression target (1.3x)
        actual_words=actual_words,
        original_answer=text_to_compress
    )
    
    try:
        # Add timeout protection for compression
        try:
            compressed_text = await asyncio.wait_for(
                gemini_client.generate_response(
                    user_prompt=prompt,
                    system_prompt="You are a concise editor. Return only the compressed answer.",
                    temperature=0.1,  # Low temperature for consistent compression
                    max_retries=1
                ),
                timeout=60.0  # 60 second timeout
            )
        except asyncio.TimeoutError:
            logger.error("❌ Compression timed out after 60 seconds")
            return None  # Return None to skip compression
        
        compressed_text = compressed_text.strip()
        
        # Restore visuals
        final_answer = restore_visuals(compressed_text, replacements)
        
        compressed_words = count_words_excluding_visuals(final_answer)
        
        logger.info(f"✅ Compression complete: {actual_words} -> {compressed_words} words ({round(compressed_words/actual_words*100)}% of original)")
        
        return final_answer
        
    except Exception as e:
        logger.error(f"❌ Compression failed: {e}")
        return None

