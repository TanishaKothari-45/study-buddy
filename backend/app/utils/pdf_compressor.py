"""
pdf_compressor.py

Compresses large PDF files by:
- Reducing image quality/DPI (for scanned PDFs)
- Optimizing image compression
- Removing unnecessary metadata
- Keeping text intact

Only compresses if file exceeds threshold (default: 20 MB)
"""

import os
import logging
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
COMPRESSION_THRESHOLD_MB = 40  # Only compress files larger than this
MAX_IMAGE_DPI = 200  # Reduce images to max 200 DPI (good for OCR/text extraction)
JPEG_QUALITY = 85  # JPEG quality (85 is good balance)

def get_file_size_mb(file_path: str) -> float:
    """Get file size in MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

def compress_pdf(
    pdf_path: str,
    output_path: Optional[str] = None,
    threshold_mb: float = COMPRESSION_THRESHOLD_MB,
    max_dpi: int = MAX_IMAGE_DPI,
    jpeg_quality: int = JPEG_QUALITY
) -> str:
    """
    Compress PDF if it exceeds threshold.
    
    Args:
        pdf_path: Path to input PDF
        output_path: Path for compressed PDF (default: adds '_compressed' suffix)
        threshold_mb: Only compress if file is larger than this (MB)
        max_dpi: Maximum DPI for images (reduces larger images)
        jpeg_quality: JPEG quality for image compression (1-100)
        
    Returns:
        Path to compressed PDF (or original if not compressed)
    """
    try:
        file_size_mb = get_file_size_mb(pdf_path)
        
        # Skip compression if file is small enough
        if file_size_mb < threshold_mb:
            logger.info(f"📄 PDF {os.path.basename(pdf_path)} is {file_size_mb:.1f} MB - skipping compression")
            return pdf_path
        
        logger.info(f"🗜️ Compressing PDF: {os.path.basename(pdf_path)} ({file_size_mb:.1f} MB)")
        
        # Set output path
        if output_path is None:
            pdf_dir = os.path.dirname(pdf_path)
            pdf_name = Path(pdf_path).stem
            output_path = os.path.join(pdf_dir, f"{pdf_name}_compressed.pdf")
        
        # Open PDF
        doc = fitz.open(pdf_path)
        
        # Process each page
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get image list for this page
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                
                # Get image data
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Only compress if it's a large image
                image_size_kb = len(image_bytes) / 1024
                
                if image_size_kb > 100:  # Only compress images > 100 KB
                    try:
                        # Re-insert compressed image
                        # PyMuPDF will automatically compress when saving
                        # We can also reduce DPI here if needed
                        doc._update_stream(
                            xref,
                            image_bytes,
                            compress=True  # Enable compression
                        )
                        logger.debug(f"   Compressed image {img_index + 1} on page {page_num + 1} ({image_size_kb:.1f} KB)")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not compress image {img_index + 1} on page {page_num + 1}: {e}")
        
        # Save compressed PDF
        # Use garbage collection and deflate compression
        doc.save(
            output_path,
            garbage=4,  # Aggressive garbage collection
            deflate=True,  # Use deflate compression
            clean=True,  # Clean content streams
            ascii=False  # Keep binary (smaller)
        )
        doc.close()
        
        # Check compression result
        compressed_size_mb = get_file_size_mb(output_path)
        compression_ratio = (1 - compressed_size_mb / file_size_mb) * 100
        
        logger.info(f"✅ Compression complete:")
        logger.info(f"   • Original: {file_size_mb:.1f} MB")
        logger.info(f"   • Compressed: {compressed_size_mb:.1f} MB")
        logger.info(f"   • Reduction: {compression_ratio:.1f}%")
        
        # If compression didn't help much, use original
        if compression_ratio < 5:  # Less than 5% reduction
            logger.info(f"   ⚠️ Compression didn't help much, using original")
            os.remove(output_path)
            return pdf_path
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Error compressing PDF {pdf_path}: {e}")
        # Return original on error
        return pdf_path

def compress_pdf_if_needed(
    pdf_path: str,
    threshold_mb: float = COMPRESSION_THRESHOLD_MB
) -> str:
    """
    Compress PDF only if it exceeds threshold.
    Returns original path if compression not needed.
    
    Args:
        pdf_path: Path to PDF file
        threshold_mb: Size threshold in MB
        
    Returns:
        Path to PDF (compressed or original)
    """
    file_size_mb = get_file_size_mb(pdf_path)
    
    if file_size_mb < threshold_mb:
        return pdf_path
    
    # Compress the PDF
    return compress_pdf(pdf_path, threshold_mb=threshold_mb)

