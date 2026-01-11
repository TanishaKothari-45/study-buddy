"""
ROI Processing Module
Handles ROI extraction and Google Vision API OCR (lazy-loaded)
"""
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['USE_NNPACK'] = '0'

import cv2
import numpy as np
import logging
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from PIL import Image
from pathlib import Path

# Load environment variables
from ..core.env import load_env_vars
load_env_vars()

logger = logging.getLogger(__name__)

# Google Vision client (lazy-loaded when needed)
_vision_client: Optional[Any] = None


def _get_vision_client():
    """
    Lazy-load Google Vision API client only when actually needed.
    This avoids startup overhead if Gemini OCR is used instead.
    """
    global _vision_client
    
    if _vision_client is not None:
        return _vision_client
    
    try:
        # Import only when needed
        from google.cloud import vision
        
        # Get Google Vision credentials path from environment or use default
        GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not GOOGLE_CREDENTIALS_PATH:
            # Try to find JSON file in project root
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            default_cred_path = project_root / "upsc-answer-6cc707343a4d.json"
            if default_cred_path.exists():
                GOOGLE_CREDENTIALS_PATH = str(default_cred_path)
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CREDENTIALS_PATH
                logger.info(f"✅ Found Google credentials at: {GOOGLE_CREDENTIALS_PATH}")
            else:
                logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS not set and default file not found")
                logger.warning(f"   Looking for: {default_cred_path}")
        else:
            logger.info(f"✅ Google credentials path from env: {GOOGLE_CREDENTIALS_PATH}")
        
        # Initialize Google Vision client
        _vision_client = vision.ImageAnnotatorClient()
        logger.info("✅ Google Vision API client initialized successfully (lazy-loaded)")
        return _vision_client
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Google Vision client: {e}")
        logger.error("   Make sure GOOGLE_APPLICATION_CREDENTIALS is set to your JSON file path")
        raise Exception(f"Google Vision client initialization failed: {e}")


def vision_blocks_and_fulltext(roi_np: np.ndarray) -> Dict[str, Any]:
    """
    Extract text blocks AND full text from ROI using Google Vision API with spatial information
    
    Returns both blocks (for spatial structure) and full_text (for context).
    NOTE: Do not reconstruct answer here - LLM will handle reconstruction.
    
    Args:
        roi_np: Full ROI image as numpy array (BGR or grayscale) - ONE PAGE, NOT SEGMENTED
    
    Returns:
        Dictionary with:
        {
            "blocks": [
                {"text": str, "bbox": [(x,y),(x,y),(x,y),(x,y)], "conf": float},
                ...
            ],
            "full_text": "...raw text...",
            "width": W,
            "height": H
        }
    """
    # Lazy-load vision client only when this function is called
    vision_client = _get_vision_client()
    
    try:
        logger.info(f"      📸 Sending FULL ROI image to Google Vision")
        logger.info(f"         • Shape: {roi_np.shape}")
        logger.info(f"         • Dtype: {roi_np.dtype}")
        logger.info(f"         • Min/Max values: {roi_np.min()}/{roi_np.max()}")
        logger.info(f"         • ⚠️  NO preprocessing - sending RAW RGB ROI image")
        logger.info(f"         • ⚠️  NO line segmentation - sending entire page ROI")
        
        # Convert numpy array to PIL Image
        # ROI is already RGB (from ROI extraction), no preprocessing applied
        # Handle different image formats
        if roi_np.ndim == 2:
            # Grayscale (shouldn't happen, but handle it)
            logger.warning(f"      ⚠️  Grayscale image detected (ndim=2) - converting to RGB")
            pil = Image.fromarray(roi_np).convert('RGB')
        elif roi_np.ndim == 3:
            # RGB image (already RGB from ROI extraction, no conversion needed)
            if roi_np.shape[2] == 3:
                # Already RGB, use directly
                pil = Image.fromarray(roi_np)
                logger.info(f"         • ✅ RGB image confirmed (3 channels)")
            else:
                logger.warning(f"      ⚠️  Unexpected channel count: {roi_np.shape[2]}")
                pil = Image.fromarray(roi_np)
        else:
            logger.error(f"      ❌ Unexpected image dimensions: {roi_np.ndim}")
            pil = Image.fromarray(roi_np)
        
        # Convert PIL Image → PNG bytes in memory
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        content = buf.getvalue()
        
        logger.info(f"      📤 Sending {len(content)} bytes ({len(content)/1024:.2f} KB) to Google Vision API")
        
        # Send FULL ROI image to Google Vision API (no segmentation)
        image = vision.Image(content=content)
        resp = vision_client.document_text_detection(image=image)
        
        if resp.error.message:
            raise RuntimeError(resp.error.message)
        
        W, H = pil.size
        blocks = []
        full_text = resp.full_text_annotation.text or ""
        
        logger.info(f"      ✅ Google Vision API response received")
        logger.info(f"         • Image dimensions: {W}x{H} pixels")
        logger.info(f"         • Full text length: {len(full_text)} chars")
        logger.info(f"         • Number of pages in response: {len(resp.full_text_annotation.pages)}")
        
        # Extract blocks: page → block → paragraph → words
        # Build blocks with confidence scores
        for page in resp.full_text_annotation.pages:
            for block in page.blocks:
                for para in block.paragraphs:
                    words = []
                    confs = []
                    
                    for w in para.words:
                        text_word = "".join([s.text for s in w.symbols])
                        conf = float(getattr(w, "confidence", 0.99))
                        words.append(text_word)
                        confs.append(conf)
                    
                    t = " ".join(words).strip()
                    if not t:
                        continue
                    
                    # Paragraph bounding box normalized to image coordinates
                    bbox = [(v.x, v.y) for v in para.bounding_box.vertices]
                    avg_conf = float(np.mean(confs)) if confs else 0.0
                    
                    blocks.append({
                        "text": t,
                        "bbox": bbox,
                        "conf": avg_conf
                    })
        
        # Sort primarily by Y then X (reading order)
        blocks.sort(key=lambda b: (b["bbox"][0][1], b["bbox"][0][0]))
        
        logger.info(f"         • Total blocks extracted: {len(blocks)} (before filtering)")
        
        # Optional: Filter very small noise blocks (len > 2)
        # DO NOT merge/reconstruct - preserve spatial structure
        blocks = [b for b in blocks if len(b["text"]) > 2]
        
        logger.info(f"         • Blocks after filtering (len > 2): {len(blocks)}")
        if blocks:
            logger.info(f"         • Sample blocks:")
            for i, block in enumerate(blocks[:3], 1):
                logger.info(f"            {i}. '{block['text'][:50]}...' (conf={block['conf']:.2f})")
        
        logger.debug(f"      ✅ Extracted {len(blocks)} text blocks from Google Vision")
        logger.debug(f"      📏 Image dimensions: {W}x{H} pixels")
        logger.debug(f"      📝 Full text length: {len(full_text)} chars")
        
        return {
            "blocks": blocks,
            "full_text": full_text.strip(),
            "width": W,
            "height": H,
        }
        
    except Exception as e:
        logger.error(f"   ❌ Google Vision API error: {str(e)}")
        raise


def process_pages_parallel_google_vision(pages_data: List[Dict[str, Any]], max_workers: int = 4) -> List[Dict[str, Any]]:
    """
    Process multiple pages in parallel using Google Vision API OCR with block extraction
    
    CRUCIAL: Returns blocks with spatial information (bbox), NOT merged text.
    This preserves structure: columns, vertical lists, side notes.
    
    Args:
        pages_data: List of page dictionaries with ROI images
            [
                {
                    "page_number": 1,
                    "roi_image_preprocessed": <np.ndarray>
                },
                ...
            ]
        max_workers: Maximum number of parallel workers
    
    Returns:
        List of results with blocks per page:
        [
            {
                "page_number": 1,
                "blocks": [
                    {"text": "...", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]},
                    ...
                ],
                "text": "merged text..."  # For backward compatibility
            },
            ...
        ]
    """
    logger.info("")
    logger.info("   " + "="*70)
    logger.info("   🚀 Starting parallel Google Vision API OCR processing")
    logger.info("   " + "="*70)
    logger.info(f"   📋 Total pages to process: {len(pages_data)}")
    logger.info(f"   ⚙️  Max workers: {max_workers}")
    logger.info(f"   " + "="*70)
    logger.info("")
    
    results = []

    def run_single(page: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single page ROI with Google Vision API
        
        IMPORTANT: Sends the FULL ROI image (one page) to Google Vision.
        NO line segmentation - Google Vision handles text detection internally.
        """
        page_no = page.get("page_number")
        logger.info(f"   📄 Processing page {page_no} with Google Vision API...")
        logger.info(f"      📸 Sending FULL ROI image (no line segmentation)")
        
        roi = page.get("roi_image_preprocessed")
        if roi is None:
            logger.warning(f"   ⚠️ Page {page_no}: No ROI found")
            return {
                "page_number": page_no,
                "text": "",
                "error": "no roi"
            }
        
        logger.debug(f"      • ROI shape: {roi.shape}")
        logger.debug(f"      • ROI size: {roi.shape[1]}x{roi.shape[0]} pixels")
        
        # Save ROI for debugging (raw ROI, no preprocessing, no segmentation)
        debug_path = f"/tmp/roi_debug_page_{page_no}.png"
        cv2.imwrite(debug_path, roi)
        logger.debug(f"      💾 Saved FULL ROI for debugging: {debug_path}")
        logger.debug(f"      ⚠️  This is the EXACT image sent to Google Vision (full page ROI)")
        
        try:
            # Run Google Vision API OCR on FULL ROI image - extract blocks AND full_text
            # NO preprocessing, NO line segmentation - just the raw ROI
            ocr_result = vision_blocks_and_fulltext(roi)
            
            blocks = ocr_result["blocks"]
            full_text = ocr_result["full_text"]
            width = ocr_result["width"]
            height = ocr_result["height"]
            
            logger.info(f"   ✅ Page {page_no}: OCR complete - extracted {len(blocks)} blocks")
            logger.info(f"      📏 Dimensions: {width}x{height} pixels")
            logger.info(f"      📝 Full text length: {len(full_text)} chars")
            
            # Optional: Clean full_text if needed (only if garbage chars detected)
            # DO NOT clean blocks - preserve spatial structure
            cleaned_full_text = clean_raw_text(full_text) if full_text else ""
            
            # For backward compatibility: create merged text from blocks
            # But blocks + full_text are the primary data
            merged_text = "\n".join([b["text"] for b in blocks])
            
            # Save full_text and blocks to files for inspection
            import json
            full_text_path = f"/tmp/roi_debug_page_{page_no}_full_text.txt"
            with open(full_text_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            logger.debug(f"      💾 Saved full_text to: {full_text_path}")
            
            blocks_json_path = f"/tmp/roi_debug_page_{page_no}_blocks.json"
            with open(blocks_json_path, 'w', encoding='utf-8') as f:
                json.dump(ocr_result, f, indent=2, ensure_ascii=False)
            logger.debug(f"      💾 Saved blocks + metadata to: {blocks_json_path}")
            
            return {
                "page_number": page_no,
                "blocks": blocks,  # Blocks with text, bbox, conf
                "full_text": cleaned_full_text or full_text,  # Full text (cleaned if needed)
                "width": width,
                "height": height,
                "text": merged_text.strip()  # Merged text from blocks (for backward compatibility)
            }
        except Exception as e:
            logger.error(f"   ❌ Page {page_no}: OCR failed - {str(e)}")
            return {
                "page_number": page_no,
                "text": "",
                "error": str(e)
            }

    logger.info(f"   🔧 Submitting {len(pages_data)} pages to thread pool...")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(run_single, p) for p in pages_data]
        
        completed = 0
        for f in as_completed(futures):
            completed += 1
            result = f.result()
            results.append(result)
            logger.info(f"   📊 Progress: {completed}/{len(pages_data)} pages completed")

    logger.info(f"   🔧 Sorting results by page number...")
    results.sort(key=lambda x: x["page_number"])
    
    logger.info("")
    logger.info("   " + "="*70)
    logger.info("   ✅ Parallel Google Vision API OCR processing complete!")
    logger.info("   " + "="*70)
    logger.info("   📊 Summary:")
    for r in results:
        text_len = len(r.get("text", ""))
        logger.info(f"      • Page {r['page_number']}: text length={text_len} chars")
    logger.info("   " + "="*70)
    logger.info("")
    
    return results


def clean_raw_text(text: str) -> str:
    """
    Minimal cleanup for raw OCR text (optional - use only if you see garbage chars)
    
    Only removes obvious noise characters - preserves structure.
    Use on full_text only, NOT on blocks.
    
    Args:
        text: Raw OCR text
    
    Returns:
        Cleaned text
    """
    import re
    
    if not text:
        return ""
    
    # Remove weird unicode blocks / symbols (■□▪▫●•)
    text = re.sub(r'[■□▪▫●•]', '', text)
    
    # Normalize whitespace (multiple spaces to single space)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def clean_ocr_text_google(text: str) -> str:
    """
    Minimal cleaning for OCR-extracted text from Google Vision API
    
    IMPORTANT: This is for backward compatibility only (merged text display).
    The primary data is blocks with spatial info - DO NOT do heavy post-processing
    that destroys spatial structure. Blocks are already filtered (len > 2).
    
    Args:
        text: Merged text from blocks (for display/legacy use only)
    
    Returns:
        Minimally cleaned text (preserves structure)
    """
    import re
    
    if not text:
        return ""
    
    logger.debug(f"   🧹 Starting minimal text cleaning (for display only)...")
    logger.debug(f"      • Input text length: {len(text)} chars")
    
    original_length = len(text)
    
    # Only remove obvious noise - preserve spatial structure
    # Remove weird unicode blocks / symbols (■□▪▫●) - these are definitely noise
    text = re.sub(r'[■□▪▫●]', '', text)
    
    # Strip leading/trailing whitespace only - preserve internal structure
    final_text = text.strip()
    
    logger.debug(f"   ✅ Minimal cleaning complete: {original_length} → {len(final_text)} chars")
    logger.debug(f"      ⚠️  No heavy post-processing - spatial structure preserved")
    
    return final_text


def clean_ocr_text(text: str) -> str:
    """
    Clean OCR-extracted text to remove common artifacts and noise
    (Legacy function - now uses clean_ocr_text_google for Google Vision results)
    
    Args:
        text: Raw OCR text
    
    Returns:
        Cleaned text
    """
    # Use Google Vision specific cleaning
    return clean_ocr_text_google(text)
