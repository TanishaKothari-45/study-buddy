"""
Gemini OCR Utility
Handles OCR processing using Gemini 2.5 Pro for handwritten PDFs and images
"""
import os
import logging
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)


def process_pages_with_gemini_ocr(
    pages_data: List[Dict[str, Any]], 
    gemini_api_key: str,
    max_workers: int = 1
) -> List[Dict[str, Any]]:
    """
    Process multiple pages using Gemini OCR.
    Compatible with the data structure expected by upload route.
    
    Args:
        pages_data: List of dicts, each with:
            - page_number: int
            - roi_image_preprocessed: np.ndarray (RGB image of the ROI)
        gemini_api_key: Gemini API key
        max_workers: Not used for Gemini (sequential processing), kept for compatibility
    
    Returns:
        List of dicts, each with:
            - page_number: int
            - text: str (merged text for backward compatibility)
            - full_text: str (same as text)
            - blocks: List[Dict] (text blocks with structure)
            - width: int
            - height: int
    """
    try:
        from ..gemini_core.gemini_client import GeminiClient
    except ImportError as e:
        logger.error(f"Failed to import GeminiClient: {e}")
        raise Exception("GeminiClient not available")
    
    logger.info(f"🤖 Starting Gemini OCR processing for {len(pages_data)} page(s)")
    
    # Initialize Gemini client with Pro model
    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model_name="gemini-2.5-pro"
    )
    
    results = []
    
    for page_data in pages_data:
        page_number = page_data.get("page_number", 1)
        roi_image = page_data.get("roi_image_preprocessed")
        
        if roi_image is None:
            logger.warning(f"⚠️  Page {page_number}: No ROI image provided, skipping")
            results.append({
                "page_number": page_number,
                "text": "",
                "full_text": "",
                "blocks": [],
                "width": 0,
                "height": 0,
                "error": "No ROI image provided"
            })
            continue
        
        logger.info(f"📄 Processing page {page_number} with Gemini OCR")
        logger.info(f"   • ROI shape: {roi_image.shape}")
        
        try:
            # Extract text using Gemini's multimodal capabilities
            extracted_text = extract_text_from_image_gemini(
                roi_image, 
                gemini_client,
                page_number
            )
            
            # Get image dimensions
            height, width = roi_image.shape[:2]
            
            # Create blocks structure (simplified since Gemini doesn't provide bbox)
            # Split by paragraphs for basic structure
            paragraphs = [p.strip() for p in extracted_text.split('\n\n') if p.strip()]
            blocks = []
            
            for i, para in enumerate(paragraphs):
                if para:
                    blocks.append({
                        "text": para,
                        "bbox": None,  # Gemini doesn't provide bounding boxes
                        "conf": 0.95,  # High confidence estimate for Gemini
                        "block_num": i
                    })
            
            logger.info(f"   ✅ Page {page_number}: Extracted {len(extracted_text)} chars, {len(blocks)} blocks")
            
            results.append({
                "page_number": page_number,
                "text": extracted_text,
                "full_text": extracted_text,
                "blocks": blocks,
                "width": width,
                "height": height
            })
            
        except Exception as e:
            logger.error(f"   ❌ Page {page_number}: Gemini OCR failed: {e}")
            results.append({
                "page_number": page_number,
                "text": f"OCR failed: {str(e)}",
                "full_text": "",
                "blocks": [],
                "width": roi_image.shape[1] if roi_image is not None else 0,
                "height": roi_image.shape[0] if roi_image is not None else 0,
                "error": str(e)
            })
    
    logger.info(f"✅ Gemini OCR processing complete: {len(results)} page(s) processed")
    return results


def extract_text_from_image_gemini(
    image_np: np.ndarray,
    gemini_client,
    page_number: int = 1
) -> str:
    """
    Extract text from a numpy array image using Gemini OCR.
    
    Args:
        image_np: Image as numpy array (RGB)
        gemini_client: Initialized GeminiClient instance
        page_number: Page number for logging
    
    Returns:
        Extracted text as string
    """
    import asyncio
    
    try:
        # Convert numpy array to PIL Image
        if image_np.ndim == 2:
            # Grayscale
            pil_image = Image.fromarray(image_np).convert('RGB')
        elif image_np.ndim == 3:
            # RGB
            pil_image = Image.fromarray(image_np)
        else:
            raise ValueError(f"Unexpected image dimensions: {image_np.ndim}")
        
        # Save PIL Image to temporary file (Gemini API requires file path)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            temp_path = tmp_file.name
            pil_image.save(temp_path, format='PNG')
        
        try:
            # Create prompt for OCR
            ocr_prompt = """Extract ALL text from this handwritten image.

Instructions:
1. Read the handwritten text carefully
2. Preserve the original structure (paragraphs, line breaks, bullet points)
3. If text is unclear, make your best interpretation
4. Return ONLY the extracted text, no commentary or formatting markers

Extracted text:"""
            
            logger.info(f"   📸 Sending page {page_number} to Gemini for OCR...")
            
            # Use Gemini's image understanding for OCR (async call)
            response = asyncio.run(
                gemini_client.generate_response(
                    user_prompt=ocr_prompt,
                    image_path=temp_path,
                    temperature=0.1  # Low temperature for accurate OCR
                )
            )
            
            extracted_text = response.strip()
            
            logger.info(f"   ✅ Gemini extracted {len(extracted_text)} characters")
            
            return extracted_text
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        logger.error(f"   ❌ Gemini OCR extraction failed: {e}")
        raise


def process_roi_image_with_gemini(
    roi_image_path: str,
    gemini_api_key: str
) -> str:
    """
    Process a single ROI image file with Gemini OCR.
    Convenience function for single-file processing.
    
    Args:
        roi_image_path: Path to ROI image file
        gemini_api_key: Gemini API key
    
    Returns:
        Extracted text
    """
    try:
        from ..gemini_core.gemini_client import GeminiClient
    except ImportError as e:
        logger.error(f"Failed to import GeminiClient: {e}")
        raise Exception("GeminiClient not available")
    
    # Load image
    pil_image = Image.open(roi_image_path)
    image_np = np.array(pil_image)
    
    # Initialize Gemini client
    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model_name="gemini-2.5-pro"
    )
    
    # Extract text
    return extract_text_from_image_gemini(image_np, gemini_client, page_number=1)
