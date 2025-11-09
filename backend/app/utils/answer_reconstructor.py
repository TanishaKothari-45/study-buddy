"""
Answer Reconstruction Module
Reconstructs OCR blocks into clean prose using LLM
"""
import logging
import json
import os
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# System prompt for reconstruction
RECONSTRUCT_SYSTEM_PROMPT = """You are a faithful transcriber. Your ONLY task is to reconstruct the student's original UPSC handwritten answer using the raw OCR blocks and raw OCR full text provided.

RULES:

• Use only the provided OCR text. Do not add any new knowledge.

• Do not correct factual content.

• You may fix only spacing/case for readability.

• If multiple blocks imply comparison or side-by-side columns, convert them to a comparative list.

• If a diagram / flowchart / comparative table is visually implied by block positions or text, insert a placeholder in format:
  [diagram: short descriptor]

• If text is unclear / partially cut, use "[unclear]" exactly.

• Output must be a clean readable answer formatted with paragraphs/bullets.

Do NOT evaluate. Do NOT explain. Do NOT summarize. Only reconstruct."""


def reconstruct_answer_from_ocr_data(
    ocr_data: Dict[str, Any],
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> str:
    """
    Reconstruct OCR data (blocks + full_text) into clean prose using LLM
    
    Args:
        ocr_data: Dictionary with OCR data:
            {
                "blocks": [
                    {"text": "...", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "conf": 0.93},
                    ...
                ],
                "full_text": "...raw text...",
                "width": W,
                "height": H
            }
        llm_client: OpenAI client instance
        model: LLM model to use (default: gpt-4o-mini)
        max_retries: Maximum retry attempts
    
    Returns:
        Reconstructed clean prose text
    """
    blocks = ocr_data.get("blocks", [])
    full_text = ocr_data.get("full_text", "")
    width = ocr_data.get("width", 0)
    height = ocr_data.get("height", 0)
    
    if not blocks and not full_text:
        logger.warning("⚠️ No blocks or full_text provided for reconstruction")
        return ""
    
    # Format OCR data as JSON for LLM
    ocr_json = json.dumps(ocr_data, ensure_ascii=False, indent=2)
    
    # Log the data being sent to LLM (for debugging/inspection)
    logger.info(f"   📤 Sending OCR data to LLM:")
    logger.info(f"      • Blocks: {len(blocks)}")
    logger.info(f"      • Full text length: {len(full_text)} chars")
    logger.info(f"      • Image dimensions: {width}x{height} pixels")
    
    if blocks:
        logger.debug(f"   📋 Blocks data (first 3):")
        for i, block in enumerate(blocks[:3], 1):
            text_preview = block.get('text', '')[:50]
            conf = block.get('conf', 0.0)
            logger.debug(f"      Block {i}: text='{text_preview}...', conf={conf:.2f}, bbox={block.get('bbox', [])}")
        if len(blocks) > 3:
            logger.debug(f"      ... and {len(blocks) - 3} more blocks")
    
    # Save OCR data to temporary file for inspection
    import tempfile
    temp_dir = tempfile.gettempdir()
    ocr_file = os.path.join(temp_dir, f"ocr_data_for_llm_{int(time.time())}.json")
    try:
        with open(ocr_file, 'w', encoding='utf-8') as f:
            json.dump(ocr_data, f, indent=2, ensure_ascii=False)
        logger.info(f"   💾 Saved OCR data to: {ocr_file}")
    except Exception as e:
        logger.warning(f"   ⚠️ Failed to save OCR data file: {e}")
    
    user_message = f"""Reconstruct the student's handwritten answer from the following OCR data:

{ocr_json}

Remember:
- Use only the provided OCR text
- Do not add new knowledge
- Fix only spacing/case for readability
- Handle comparisons/columns logically
- Insert placeholders for diagrams/tables/flowcharts
- Use "[unclear]" for unclear text
- Do NOT evaluate, explain, or summarize"""
    
    for attempt in range(max_retries):
        try:
            logger.info(f"   🤖 Sending OCR data to LLM for reconstruction (attempt {attempt + 1}/{max_retries})...")
            
            completion = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": RECONSTRUCT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,  # Maximum accuracy - no hallucination
                top_p=0,  # Deterministic output
                max_tokens=2000
            )
            
            reconstructed_text = completion.choices[0].message.content
            
            if reconstructed_text:
                logger.info(f"   ✅ LLM reconstruction complete - output length: {len(reconstructed_text)} chars")
                return reconstructed_text.strip()
            else:
                raise ValueError("Empty response from LLM")
                
        except Exception as e:
            logger.error(f"   ❌ LLM reconstruction failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"   ⏳ Retrying...")
                continue
            else:
                logger.error(f"   ❌ All reconstruction attempts failed")
                # Return fallback: use full_text if available, otherwise merge blocks
                if full_text:
                    fallback_text = full_text
                    logger.warning(f"   ⚠️ Using fallback: full_text without LLM reconstruction")
                else:
                    fallback_text = "\n".join([b["text"] for b in blocks])
                    logger.warning(f"   ⚠️ Using fallback: merged blocks without LLM reconstruction")
                return fallback_text
    
    return ""


def reconstruct_pages_blocks(
    ocr_results: List[Dict[str, Any]],
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    combine_pages: bool = True
) -> List[Dict[str, Any]]:
    """
    Reconstruct OCR data for multiple pages
    
    Args:
        ocr_results: List of OCR results per page:
            [
                {
                    "page_number": 1,
                    "blocks": [...],
                    "full_text": "...",
                    "width": W,
                    "height": H,
                    "text": "..."
                },
                ...
            ]
        llm_client: OpenAI client instance
        model: LLM model to use
        combine_pages: If True, combine all pages into one reconstruction (default: True)
    
    Returns:
        List of results with reconstructed text:
            [
                {
                    "page_number": 1,
                    "blocks": [...],
                    "full_text": "...",
                    "width": W,
                    "height": H,
                    "text": "...",  # original merged text
                    "reconstructed_text": "..."  # LLM reconstructed prose
                },
                ...
            ]
    """
    logger.info("")
    logger.info("   " + "="*70)
    logger.info("   🔄 Starting LLM Reconstruction Phase")
    logger.info("   " + "="*70)
    logger.info(f"   📋 Total pages to reconstruct: {len(ocr_results)}")
    logger.info(f"   🔗 Combine pages: {combine_pages}")
    logger.info("   " + "="*70)
    logger.info("")
    
    reconstructed_results = []
    
    if combine_pages and len(ocr_results) > 1:
        # Combine all pages into one OCR data structure
        logger.info("   📄 Combining all pages for single reconstruction...")
        
        combined_blocks = []
        combined_full_texts = []
        total_width = 0
        total_height = 0
        
        for result in ocr_results:
            blocks = result.get("blocks", [])
            full_text = result.get("full_text", "")
            width = result.get("width", 0)
            height = result.get("height", 0)
            
            combined_blocks.extend(blocks)
            if full_text:
                combined_full_texts.append(full_text)
            total_width = max(total_width, width)
            total_height += height  # Sum heights for multi-page
        
        combined_full_text = "\n\n".join(combined_full_texts) if combined_full_texts else ""
        
        combined_ocr_data = {
            "blocks": combined_blocks,
            "full_text": combined_full_text,
            "width": total_width,
            "height": total_height
        }
        
        logger.info(f"   📊 Combined: {len(combined_blocks)} blocks, {len(combined_full_text)} chars")
        
        try:
            reconstructed_text = reconstruct_answer_from_ocr_data(
                ocr_data=combined_ocr_data,
                llm_client=llm_client,
                model=model
            )
            
            # Assign reconstructed text to all pages
            for result in ocr_results:
                reconstructed_results.append({
                    **result,
                    "reconstructed_text": reconstructed_text
                })
            
            logger.info("   ✅ Combined reconstruction complete")
            
        except Exception as e:
            logger.error(f"   ❌ Combined reconstruction failed - {e}")
            # Use original merged text as fallback for all pages
            for result in ocr_results:
                reconstructed_results.append({
                    **result,
                    "reconstructed_text": result.get("text", "")
                })
    else:
        # Reconstruct each page separately
        for result in ocr_results:
            page_no = result.get("page_number", 0)
            blocks = result.get("blocks", [])
            full_text = result.get("full_text", "")
            
            if not blocks and not full_text:
                logger.warning(f"   ⚠️ Page {page_no}: No blocks or full_text to reconstruct")
                reconstructed_results.append({
                    **result,
                    "reconstructed_text": result.get("text", "")
                })
                continue
            
            logger.info(f"   📄 Reconstructing page {page_no} ({len(blocks)} blocks, {len(full_text)} chars full_text)...")
            
            ocr_data = {
                "blocks": blocks,
                "full_text": full_text,
                "width": result.get("width", 0),
                "height": result.get("height", 0)
            }
            
            try:
                reconstructed_text = reconstruct_answer_from_ocr_data(
                    ocr_data=ocr_data,
                    llm_client=llm_client,
                    model=model
                )
                
                reconstructed_results.append({
                    **result,
                    "reconstructed_text": reconstructed_text
                })
                
                logger.info(f"   ✅ Page {page_no}: Reconstruction complete")
                
            except Exception as e:
                logger.error(f"   ❌ Page {page_no}: Reconstruction failed - {e}")
                # Use original merged text as fallback
                reconstructed_results.append({
                    **result,
                    "reconstructed_text": result.get("text", "")
                })
    
    logger.info("")
    logger.info("   " + "="*70)
    logger.info("   ✅ LLM Reconstruction Phase Complete!")
    logger.info("   " + "="*70)
    logger.info("")
    
    return reconstructed_results

