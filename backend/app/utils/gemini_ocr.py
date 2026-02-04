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


async def process_pages_with_gemini_ocr_with_reconstruction(
    pages_data: List[Dict[str, Any]], 
    gemini_api_key: str,
    max_workers: int = 1
) -> List[Dict[str, Any]]:
    """
    Process multiple pages using Gemini OCR WITH RECONSTRUCTION (for PDF uploads to Pinecone).
    
    This function performs OCR and reconstructs fragmented text into clear, readable prose.
    Use this for uploading study materials to Pinecone where quality matters.
    
    Args:
        pages_data: List of dicts, each with:
            - page_number: int
            - roi_image_preprocessed: np.ndarray (RGB image of the ROI)
        gemini_api_key: Gemini API key
        max_workers: Not used for Gemini (batch processing), kept for compatibility
    
    Returns:
        List of dicts, each with:
            - page_number: int
            - text: str (reconstructed text)
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
    
    logger.info(f"🤖 Starting Gemini OCR processing for {len(pages_data)} page(s) in a single batch")
    
    # Initialize Gemini client with Pro model and extended timeout for OCR
    # OCR + Reconstruction can take 30-60 seconds per page, so allow 5 minutes for batches
    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model_name="gemini-2.5-pro",
        timeout=300.0  # 5 minutes for batch OCR + reconstruction
    )
    
    # Extract all page images and save to temp files
    import tempfile
    temp_files = []
    page_dimensions = []
    
    try:
        for page_data in pages_data:
            page_number = page_data.get("page_number", 1)
            roi_image = page_data.get("roi_image_preprocessed")
            
            if roi_image is None:
                logger.warning(f"⚠️  Page {page_number}: No ROI image provided, skipping")
                continue
            
            # Convert numpy array to PIL Image
            if roi_image.ndim == 2:
                pil_image = Image.fromarray(roi_image).convert('RGB')
            elif roi_image.ndim == 3:
                pil_image = Image.fromarray(roi_image)
            else:
                logger.warning(f"⚠️  Page {page_number}: Unexpected image dimensions: {roi_image.ndim}")
                continue
            
            # Save to temp file
            tmp_file = tempfile.NamedTemporaryFile(suffix=f'_page{page_number}.png', delete=False)
            temp_path = tmp_file.name
            pil_image.save(temp_path, format='PNG')
            tmp_file.close()
            
            temp_files.append(temp_path)
            page_dimensions.append((roi_image.shape[1], roi_image.shape[0]))  # width, height
            
            logger.info(f"   📄 Prepared page {page_number} ({roi_image.shape})")
        
        if not temp_files:
            logger.error("❌ No valid pages to process")
            return []
        
        # Create batch OCR prompt with reconstruction
        ocr_prompt = f"""Extract and reconstruct text from these {len(temp_files)} handwritten or printed images.

Your task:
1. Read the handwritten/printed text carefully from each image
2. RECONSTRUCT the text into clear, readable prose:
   - Fix incomplete words (e.g., "numb" → "number", "administrat" → "administration")
   - Fix OCR artifacts and fragmented sentences
   - Infer missing letters/words from context
   - Maintain the original meaning - do NOT add new information
3. IGNORE margins, headers, footers, page numbers, watermarks
4. Focus ONLY on the main content area
5. Preserve paragraph structure and logical flow
6. Output clean, complete sentences that make sense

For each image, output the RECONSTRUCTED text in this format:
=== PAGE 1 ===
[reconstructed text for page 1 - clean, readable prose]

=== PAGE 2 ===
[reconstructed text for page 2 - clean, readable prose]

...and so on for all {len(temp_files)} pages.

Reconstructed text:"""
        
        logger.info(f"   📸 Sending {len(temp_files)} pages to Gemini for OCR + Reconstruction...")
        
        # Send all images in one API call - Gemini will OCR and reconstruct
        response = await gemini_client.generate_response(
            user_prompt=ocr_prompt,
            image_path=temp_files,  # Pass list of image paths
            temperature=0.1
        )
        
        logger.info(f"   ✅ Gemini OCR + Reconstruction complete ({len(response)} characters)")
        
        # Parse the response to extract text for each page
        results = parse_batch_ocr_response(response, len(pages_data), page_dimensions)
        
        logger.info(f"✅ Gemini OCR + Reconstruction processing complete: {len(results)} page(s) processed")
        return results
        
    finally:
        # Clean up temp files
        for temp_path in temp_files:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


async def process_pages_with_gemini_ocr(
    pages_data: List[Dict[str, Any]], 
    gemini_api_key: str,
    max_workers: int = 1
) -> List[Dict[str, Any]]:
    """
    Process multiple pages using Gemini OCR WITHOUT RECONSTRUCTION (for student answer uploads).
    
    This function performs OCR only - extracts text as-is without reconstruction.
    Use this for student answer evaluation where you want the raw OCR text.
    
    Args:
        pages_data: List of dicts, each with:
            - page_number: int
            - roi_image_preprocessed: np.ndarray (RGB image of the ROI)
        gemini_api_key: Gemini API key
        max_workers: Not used for Gemini (batch processing), kept for compatibility
    
    Returns:
        List of dicts, each with:
            - page_number: int
            - text: str (raw OCR text, no reconstruction)
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
    
    logger.info(f"🤖 Starting Gemini OCR (simple, no reconstruction) for {len(pages_data)} page(s) in a single batch")
    
    # Initialize Gemini client - shorter timeout since no reconstruction
    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model_name="gemini-2.5-pro",
        timeout=120.0  # 2 minutes for simple OCR
    )
    
    # Extract all page images and save to temp files
    import tempfile
    temp_files = []
    page_dimensions = []
    
    try:
        for page_data in pages_data:
            page_number = page_data.get("page_number", 1)
            roi_image = page_data.get("roi_image_preprocessed")
            
            if roi_image is None:
                logger.warning(f"⚠️  Page {page_number}: No ROI image provided, skipping")
                continue
            
            # Convert numpy array to PIL Image
            if roi_image.ndim == 2:
                pil_image = Image.fromarray(roi_image).convert('RGB')
            elif roi_image.ndim == 3:
                pil_image = Image.fromarray(roi_image)
            else:
                logger.warning(f"⚠️  Page {page_number}: Unexpected image dimensions: {roi_image.ndim}")
                continue
            
            # Save to temp file
            tmp_file = tempfile.NamedTemporaryFile(suffix=f'_page{page_number}.png', delete=False)
            temp_path = tmp_file.name
            pil_image.save(temp_path, format='PNG')
            tmp_file.close()
            
            temp_files.append(temp_path)
            page_dimensions.append((roi_image.shape[1], roi_image.shape[0]))  # width, height
            
            logger.info(f"   📄 Prepared page {page_number} ({roi_image.shape})")
        
        if not temp_files:
            logger.error("❌ No valid pages to process")
            return []
        
        # Create batch OCR prompt WITHOUT reconstruction - just extract text as-is
        ocr_prompt = f"""Extract text from these {len(temp_files)} handwritten or printed images.

Your task:
1. Read the handwritten/printed text carefully from each image
2. Extract the text EXACTLY as it appears - do NOT reconstruct or fix words
3. Preserve the original text structure and spacing
4. IGNORE margins, headers, footers, page numbers, watermarks
5. Focus ONLY on the main content area

For each image, output the extracted text in this format:
=== PAGE 1 ===
[raw extracted text for page 1 - as-is, no reconstruction]

=== PAGE 2 ===
[raw extracted text for page 2 - as-is, no reconstruction]

...and so on for all {len(temp_files)} pages.

Extracted text:"""
        
        logger.info(f"   📸 Sending {len(temp_files)} pages to Gemini for OCR (simple, no reconstruction)...")
        
        # Send all images in one API call - Gemini will OCR without reconstruction
        response = await gemini_client.generate_response(
            user_prompt=ocr_prompt,
            image_path=temp_files,  # Pass list of image paths
            temperature=0.1
        )
        
        logger.info(f"   ✅ Gemini OCR (simple) complete ({len(response)} characters)")
        
        # Parse the response to extract text for each page
        results = parse_batch_ocr_response(response, len(pages_data), page_dimensions)
        
        logger.info(f"✅ Gemini OCR (simple) processing complete: {len(results)} page(s) processed")
        return results
        
    finally:
        # Clean up temp files
        for temp_path in temp_files:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# Backward compatibility alias - defaults to WITH reconstruction for PDF uploads
async def process_pages_with_gemini_ocr(
    pages_data: List[Dict[str, Any]], 
    gemini_api_key: str,
    max_workers: int = 1,
    with_reconstruction: bool = True
) -> List[Dict[str, Any]]:
    """
    Process multiple pages using Gemini OCR.
    
    This is a wrapper that calls either:
    - process_pages_with_gemini_ocr_with_reconstruction (default, for PDF uploads)
    - process_pages_with_gemini_ocr (for student answers)
    
    Args:
        pages_data: List of dicts with page data
        gemini_api_key: Gemini API key
        max_workers: Not used, kept for compatibility
        with_reconstruction: If True, use reconstruction (for PDF uploads). If False, simple OCR (for student answers)
    
    Returns:
        List of page result dicts
    """
    if with_reconstruction:
        return await process_pages_with_gemini_ocr_with_reconstruction(pages_data, gemini_api_key, max_workers)
    else:
        return await process_pages_with_gemini_ocr(pages_data, gemini_api_key, max_workers)


def parse_batch_ocr_response(response: str, num_pages: int, page_dimensions: List[tuple]) -> List[Dict[str, Any]]:
    """
    Parse Gemini's batch OCR response into individual page results.
    
    Args:
        response: Raw Gemini response with page markers
        num_pages: Expected number of pages
        page_dimensions: List of (width, height) tuples for each page
    
    Returns:
        List of page result dicts
    """
    import re
    
    results = []
    
    # Split by page markers
    page_pattern = r'===\s*PAGE\s+(\d+)\s*===\s*\n(.*?)(?====\s*PAGE\s+\d+\s*===|$)'
    matches = re.findall(page_pattern, response, re.DOTALL | re.IGNORECASE)
    
    if not matches:
        # Fallback: if no markers found, treat entire response as single page
        logger.warning("⚠️  No page markers found in Gemini response, treating as single page")
        matches = [("1", response.strip())]
    
    for page_num_str, text in matches:
        page_num = int(page_num_str)
        extracted_text = text.strip()
        
        # Get dimensions for this page
        if page_num - 1 < len(page_dimensions):
            width, height = page_dimensions[page_num - 1]
        else:
            width, height = 0, 0
        
        # Create blocks structure (simplified since Gemini doesn't provide bbox)
        paragraphs = [p.strip() for p in extracted_text.split('\n\n') if p.strip()]
        blocks = []
        
        for i, para in enumerate(paragraphs):
            if para:
                blocks.append({
                    "text": para,
                    "bbox": None,
                    "conf": 0.95,
                    "block_num": i
                })
        
        logger.info(f"   ✅ Page {page_num}: Extracted {len(extracted_text)} chars, {len(blocks)} blocks")
        
        results.append({
            "page_number": page_num,
            "text": extracted_text,
            "full_text": extracted_text,
            "blocks": blocks,
            "width": width,
            "height": height
        })
    
    # Fill in missing pages with errors
    for i in range(1, num_pages + 1):
        if not any(r["page_number"] == i for r in results):
            logger.warning(f"⚠️  Page {i} not found in Gemini response")
            width, height = page_dimensions[i - 1] if i - 1 < len(page_dimensions) else (0, 0)
            results.append({
                "page_number": i,
                "text": "",
                "full_text": "",
                "blocks": [],
                "width": width,
                "height": height,
                "error": "Page not found in Gemini response"
            })
    
    # Sort by page number
    results.sort(key=lambda x: x["page_number"])
    
    return results


async def extract_text_from_image_gemini(
    image_np: np.ndarray,
    gemini_client,
    page_number: int = 1,
    with_reconstruction: bool = True
) -> str:
    """
    Extract text from a numpy array image using Gemini OCR.
    
    Args:
        image_np: Image as numpy array (RGB)
        gemini_client: Initialized GeminiClient instance
        page_number: Page number for logging
        with_reconstruction: If True, reconstruct text (for PDF uploads). If False, simple OCR (for student answers)
    
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
            if with_reconstruction:
                # Create prompt for OCR WITH reconstruction (for PDF uploads)
                ocr_prompt = """Extract and reconstruct text from this handwritten or printed image.

Your task:
1. Read the handwritten/printed text carefully
2. RECONSTRUCT the text into clear, readable prose:
   - Fix incomplete words (e.g., "numb" → "number", "administrat" → "administration")
   - Fix OCR artifacts and fragmented sentences
   - Infer missing letters/words from context
   - Maintain the original meaning - do NOT add new information
3. IGNORE margins, headers, footers, page numbers, watermarks
4. Focus ONLY on the main content area
5. Preserve paragraph structure and logical flow
6. Return ONLY the reconstructed text, no commentary

Reconstructed text:"""
                logger.info(f"   📸 Sending page {page_number} to Gemini for OCR + Reconstruction...")
            else:
                # Create prompt for OCR WITHOUT reconstruction (for student answers)
                ocr_prompt = """Extract text from this handwritten or printed image.

Your task:
1. Read the handwritten/printed text carefully
2. Extract the text EXACTLY as it appears - do NOT reconstruct or fix words
3. Preserve the original text structure and spacing
4. IGNORE margins, headers, footers, page numbers, watermarks
5. Focus ONLY on the main content area
6. Return ONLY the extracted text, no commentary

Extracted text:"""
                logger.info(f"   📸 Sending page {page_number} to Gemini for OCR (simple, no reconstruction)...")
            
            # Use Gemini's image understanding for OCR (async call)
            response = await gemini_client.generate_response(
                user_prompt=ocr_prompt,
                image_path=temp_path,
                temperature=0.1  # Low temperature for accurate OCR
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
