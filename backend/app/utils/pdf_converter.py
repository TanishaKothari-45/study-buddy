"""
PDF to image conversion utilities
Supports configurable DPI for quality control

NOTE: Temporarily disabled - pdf2image requires poppler installation
Will be enabled once poppler is installed
"""
import logging
import fitz  # PyMuPDF
from typing import List
from PIL import Image
import io

logger = logging.getLogger(__name__)

def convert_pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """
    Convert PDF pages to images with specified DPI using fitz (PyMuPDF).
    This removes the dependency on poppler.
    
    Args:
        pdf_path: Path to PDF file
        dpi: DPI resolution (300 recommended for clear text)
    
    Returns:
        List of PIL Image objects, one per page
    """
    try:
        logger.info(f"📄 Converting PDF to images using fitz: {pdf_path} (DPI: {dpi})")
        
        doc = fitz.open(pdf_path)
        images = []
        
        for i in range(len(doc)):
            page = doc.load_page(i)
            # Matrix for scaling (DPI / 72 since fitz default is 72 DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
            
        doc.close()
        logger.info(f"   ✅ Converted {len(images)} pages to images at {dpi} DPI")
        
        return images
        
    except Exception as e:
        logger.error(f"❌ Error converting PDF to images with fitz: {e}")
        # Try to provide more helpful error info
        if "no such file" in str(e).lower():
            logger.error(f"   The file was not found at {pdf_path}")
        raise

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

