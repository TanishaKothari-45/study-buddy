"""
PDF to image conversion utilities
Supports configurable DPI for quality control

NOTE: Temporarily disabled - pdf2image requires poppler installation
Will be enabled once poppler is installed
"""
import logging
from typing import List
from PIL import Image
# Temporarily commented out until poppler is installed
# from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

def convert_pdf_to_images(pdf_path: str, dpi: int = 600) -> List[Image.Image]:
    """
    Convert PDF pages to images with specified DPI
    
    Args:
        pdf_path: Path to PDF file
        dpi: DPI resolution (300 or 600 recommended, 600 for better clarity)
    
    Returns:
        List of PIL Image objects, one per page
    
    NOTE: Temporarily disabled - requires poppler installation
    """
    logger.error("❌ PDF to image conversion is temporarily disabled")
    logger.error("   Reason: pdf2image requires poppler system dependency")
    logger.error("   Status: Waiting for poppler installation to complete")
    logger.error("   Workaround: Use image files (JPG, PNG, WEBP) directly for now")
    raise ImportError(
        "PDF conversion temporarily disabled. "
        "Please install poppler first: brew install poppler (or wait for installation to complete). "
        "For now, you can upload image files directly (JPG, PNG, WEBP)."
    )
    
    # Code below will be enabled once poppler is installed
    # try:
    #     logger.info(f"📄 Converting PDF to images: {pdf_path} (DPI: {dpi})")
    #     
    #     # Convert PDF pages to images
    #     images = convert_from_path(pdf_path, dpi=dpi, fmt='png')
    #     
    #     logger.info(f"   ✅ Converted {len(images)} pages to images at {dpi} DPI")
    #     
    #     return images
    #     
    # except Exception as e:
    #     logger.error(f"❌ Error converting PDF to images: {e}")
    #     raise

def save_images_for_preview(images: List[Image.Image], output_dir: str, prefix: str = "page") -> List[str]:
    """
    Save images to disk for preview/debugging
    
    Args:
        images: List of PIL Image objects
        output_dir: Directory to save images
        prefix: Filename prefix
    
    Returns:
        List of saved file paths
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    saved_paths = []
    for i, image in enumerate(images):
        file_path = os.path.join(output_dir, f"{prefix}_{i+1}.png")
        image.save(file_path, 'PNG')
        saved_paths.append(file_path)
        logger.debug(f"   💾 Saved preview image: {file_path}")
    
    return saved_paths

