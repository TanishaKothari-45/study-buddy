"""
Complete workflow for processing handwritten answer sheets:
PDF → Images → ROI Detection → Preprocessed ROI Images
"""
import logging
import os
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

# Temporarily disabled - will be enabled once poppler is installed
# from .pdf_converter import convert_pdf_to_images
from .roi_detector import (
    extract_answer_roi, 
    detect_roi_from_sample, 
    apply_roi_to_image,
    preprocess_for_ocr
)

logger = logging.getLogger(__name__)

def process_pdf_with_roi(
    pdf_path: str, 
    dpi: int = 600,
    sample_sheet_path: Optional[str] = None,
    save_roi_previews: bool = True,
    preview_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process PDF: Convert to images, detect ROI once, apply to all pages
    
    Args:
        pdf_path: Path to PDF file
        dpi: DPI for PDF conversion (300 or 600)
        sample_sheet_path: Optional path to sample sheet for ROI detection
        save_roi_previews: Whether to save ROI images for preview
        preview_dir: Directory to save ROI preview images
    
    Returns:
        Dictionary with:
        - pages: List of page data with ROI images and metadata
        - roi_coordinates: Detected ROI coordinates
        - roi_method: Method used for ROI detection
    """
    # Step 1: Convert PDF to images
    logger.info(f"📄 Step 1: Converting PDF to images (DPI: {dpi})...")
    logger.error("❌ PDF processing temporarily disabled - poppler not installed")
    logger.error("   Please use image files (JPG, PNG, WEBP) directly for now")
    raise ImportError(
        "PDF processing temporarily disabled. "
        "Please install poppler: brew install poppler. "
        "For now, upload image files directly."
    )
    # Temporarily disabled - uncomment once poppler is installed
    # images = convert_pdf_to_images(pdf_path, dpi=dpi)
    # if not images:
    #     raise ValueError("No images extracted from PDF")
    
    # Step 2: Detect ROI (once, reuse for all pages)
    logger.info(f"🔍 Step 2: Detecting ROI...")
    roi_coords = None
    roi_method = None
    
    # Try to detect from sample sheet first
    if sample_sheet_path and os.path.exists(sample_sheet_path):
        logger.info(f"   📋 Using sample sheet for ROI detection: {sample_sheet_path}")
        roi_coords = detect_roi_from_sample(sample_sheet_path)
        if roi_coords:
            roi_method = "sample_sheet"
            logger.info(f"   ✅ ROI detected from sample sheet")
    
    # If sample sheet didn't work, detect from first page
    if roi_coords is None:
        logger.info(f"   📄 Detecting ROI from first page...")
        first_image = images[0]
        first_img_array = np.array(first_image.convert('RGB'))
        first_img_bgr = cv2.cvtColor(first_img_array, cv2.COLOR_RGB2BGR)
        
        try:
            _, metadata = extract_answer_roi(first_img_bgr, use_fallback=False)
            if metadata["success"]:
                roi_coords = metadata["coordinates"]
                roi_method = metadata["method"]
                logger.info(f"   ✅ ROI detected using {roi_method}")
            else:
                raise Exception("ROI detection failed")
        except Exception as e:
            logger.warning(f"   ⚠️ Hough Lines detection failed: {e}. Trying fallback...")
            _, metadata = extract_answer_roi(first_img_bgr, use_fallback=True)
            if metadata["success"]:
                roi_coords = metadata["coordinates"]
                roi_method = metadata["method"]
                logger.info(f"   ✅ ROI detected using fallback method")
    
    if roi_coords is None:
        raise ValueError("Failed to detect ROI from sample sheet or first page")
    
    # Step 3: Apply ROI to all pages
    logger.info(f"✂️ Step 3: Applying ROI to {len(images)} pages...")
    pages_data = []
    
    # Create preview directory if needed
    if save_roi_previews and preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
    
    for i, pil_image in enumerate(images):
        # Convert PIL to OpenCV format
        img_array = np.array(pil_image.convert('RGB'))
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Apply ROI (returns RGB crop, NO preprocessing)
        try:
            roi_rgb = apply_roi_to_image(img_bgr, roi_coords)
            page_method = roi_method
        except Exception as e:
            logger.warning(f"   ⚠️ Page {i+1}: ROI application failed, using per-page detection: {e}")
            # Fallback: detect ROI for this page individually
            _, metadata = extract_answer_roi(img_bgr, use_fallback=True)
            if metadata["success"]:
                roi_rgb, _ = extract_answer_roi(img_bgr, use_fallback=True)
                page_method = f"fallback_page_{i+1}"
            else:
                raise Exception(f"Failed to extract ROI for page {i+1}")
        
        # NO PREPROCESSING - Send original RGB ROI directly to Google Vision API
        # Google Vision handles preprocessing internally and works better with original images
        logger.info("📸 Using original RGB ROI (no preprocessing) for Google Vision API")
        logger.info("   💡 Google Vision handles preprocessing internally")
        
        # Use original RGB ROI directly (just cropped margins, no preprocessing)
        roi_image_preprocessed = roi_rgb  # Original RGB crop, no preprocessing
        
        # Convert original ROI to PIL Image for preview (RGB, no preprocessing)
        roi_preview_pil = Image.fromarray(roi_rgb)
        
        # Save ROI preview if requested (save original ROI crop, not binary)
        roi_preview_path = None
        if save_roi_previews and preview_dir:
            roi_preview_path = os.path.join(preview_dir, f"roi_page_{i+1}.png")
            roi_preview_pil.save(roi_preview_path, 'PNG')
            logger.info(f"   💾 Saved ROI preview (original crop): {roi_preview_path}")
            logger.info(f"      • Preview size: {roi_preview_pil.size[0]}x{roi_preview_pil.size[1]} pixels")
        
        pages_data.append({
            "page_number": i + 1,
            "roi_image_rgb": roi_rgb,  # Original RGB ROI (for preview)
            "roi_image_preprocessed": roi_image_preprocessed,  # Original RGB ROI (no preprocessing, for Google Vision)
            "roi_coordinates": roi_coords,
            "roi_method": page_method,
            "roi_preview_path": roi_preview_path
        })
    
    logger.info(f"✅ Successfully processed {len(pages_data)} pages with ROI extraction")
    
    return {
        "pages": pages_data,
        "roi_coordinates": roi_coords,
        "roi_method": roi_method,
        "total_pages": len(pages_data)
    }

def process_image_with_roi(
    image_path: str,
    sample_sheet_path: Optional[str] = None,
    save_roi_preview: bool = True,
    preview_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process single image: Detect ROI and extract
    
    Args:
        image_path: Path to image file
        sample_sheet_path: Optional path to sample sheet for ROI detection
        save_roi_preview: Whether to save ROI image for preview
        preview_dir: Directory to save ROI preview image
    
    Returns:
        Dictionary with ROI image and metadata
    """
    # Load image
    logger.info(f"📷 Loading image: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"❌ Failed to load image: {image_path}")
        raise ValueError(f"Failed to load image: {image_path}")
    
    logger.info(f"   ✅ Image loaded: shape={img.shape}, dtype={img.dtype}")
    
    # Detect ROI
    logger.info("🔍 Starting ROI detection...")
    roi_coords = None
    roi_method = None
    
    # Try sample sheet first
    if sample_sheet_path and os.path.exists(sample_sheet_path):
        logger.info(f"   📋 Attempting ROI detection from sample sheet: {sample_sheet_path}")
        roi_coords = detect_roi_from_sample(sample_sheet_path)
        if roi_coords:
            roi_method = "sample_sheet"
            logger.info(f"   ✅ ROI detected from sample sheet")
        else:
            logger.warning(f"   ⚠️ Failed to detect ROI from sample sheet, trying image detection")
    
    # If no sample sheet, detect from image
    if roi_coords is None:
        logger.info(f"   📄 Attempting ROI detection from image using Hough Lines...")
        try:
            _, metadata = extract_answer_roi(img, use_fallback=False)
            if metadata["success"]:
                roi_coords = metadata["coordinates"]
                roi_method = metadata["method"]
                logger.info(f"   ✅ ROI detected using {roi_method}")
            else:
                raise Exception("ROI detection failed")
        except Exception as e:
            logger.warning(f"   ⚠️ Hough Lines detection failed: {e}")
            logger.info(f"   📄 Attempting fallback ROI detection...")
            _, metadata = extract_answer_roi(img, use_fallback=True)
            if metadata["success"]:
                roi_coords = metadata["coordinates"]
                roi_method = metadata["method"]
                logger.info(f"   ✅ ROI detected using fallback method: {roi_method}")
    
    if roi_coords is None:
        logger.error("❌ Failed to detect ROI from both sample sheet and image")
        raise ValueError("Failed to detect ROI")
    
    logger.info(f"   📐 ROI coordinates: {roi_coords}")
    
    # Apply ROI (returns RGB crop, NO preprocessing)
    logger.info("✂️ Applying ROI extraction...")
    roi_rgb = apply_roi_to_image(img, roi_coords)
    logger.info(f"   ✅ ROI extracted (RGB): shape={roi_rgb.shape}")
    
    # NO PREPROCESSING - Send original RGB ROI directly to Google Vision API
    # Google Vision handles preprocessing internally and works better with original images
    logger.info("📸 Using original RGB ROI (no preprocessing) for Google Vision API")
    logger.info("   💡 Google Vision handles preprocessing internally")
    
    # Use original RGB ROI directly (just cropped margins, no preprocessing)
    roi_image_preprocessed = roi_rgb  # Original RGB crop, no preprocessing
    
    # Convert original ROI to PIL for preview (RGB, no preprocessing)
    roi_preview_pil = Image.fromarray(roi_rgb)
    
    # Save preview if requested (save original ROI, not binary thresholded)
    roi_preview_path = None
    if save_roi_preview and preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        filename = os.path.basename(image_path)
        name_without_ext = os.path.splitext(filename)[0]
        roi_preview_path = os.path.join(preview_dir, f"{name_without_ext}_roi.png")
        roi_preview_pil.save(roi_preview_path, 'PNG')
        logger.info(f"   💾 Saved ROI preview (original crop): {roi_preview_path}")
        logger.info(f"      • Preview size: {roi_preview_pil.size[0]}x{roi_preview_pil.size[1]} pixels")
    
    return {
        "roi_image_rgb": roi_rgb,  # Original RGB ROI (for preview)
        "roi_image_preprocessed": roi_image_preprocessed,  # Original RGB ROI (no preprocessing, for Google Vision)
        "roi_coordinates": roi_coords,
        "roi_method": roi_method,
        "roi_preview_path": roi_preview_path
    }

