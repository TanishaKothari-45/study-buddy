"""
EasyOCR processor for handwritten and printed text recognition
Lightweight, fast, and CPU-friendly alternative to DeepSeek-OCR
"""
import logging
from typing import Dict, Any, Optional
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Global EasyOCR reader instance
_ocr_reader = None

def get_easyocr_reader():
    """Get or initialize EasyOCR reader"""
    global _ocr_reader
    
    if _ocr_reader is None:
        try:
            import easyocr
            # Initialize reader with English support (can add more languages)
            _ocr_reader = easyocr.Reader(['en'], gpu=False)  # CPU mode
            logger.info("✅ EasyOCR initialized successfully (CPU mode)")
        except ImportError:
            logger.error("❌ EasyOCR not installed. Install with: pip install easyocr")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize EasyOCR: {e}")
            return None
    
    return _ocr_reader

def process_image_with_easyocr(image: Image.Image, filename: str = "image") -> Dict[str, Any]:
    """
    Process image with EasyOCR for text extraction
    Works great for handwritten text and is CPU-friendly
    """
    try:
        reader = get_easyocr_reader()
        if reader is None:
            return {
                "success": False,
                "text": "",
                "error": "EasyOCR not available. Install with: pip install easyocr",
                "filename": filename
            }
        
        logger.info(f"📄 Processing image with EasyOCR: {filename} ({image.size})")
        
        # Convert PIL image to numpy array for EasyOCR
        import numpy as np
        image_array = np.array(image)
        
        # Run OCR
        results = reader.readtext(image_array)
        
        # Extract text from results
        extracted_text = ""
        confidence_scores = []
        
        for (bbox, text, confidence) in results:
            if confidence > 0.3:  # Filter low-confidence detections
                extracted_text += text + " "
                confidence_scores.append(confidence)
        
        extracted_text = extracted_text.strip()
        
        if not extracted_text:
            logger.warning("⚠️ No text extracted from image")
            return {
                "success": False,
                "text": "",
                "error": "No text could be extracted from the image. Try improving image quality or lighting.",
                "filename": filename
            }
        
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        logger.info(f"✅ Extracted {len(extracted_text)} characters (avg confidence: {avg_confidence:.2f})")
        
        return {
            "success": True,
            "text": extracted_text,
            "word_count": len(extracted_text.split()),
            "filename": filename,
            "image_size": image.size,
            "confidence": avg_confidence,
            "detections": len(results)
        }
        
    except Exception as e:
        logger.error(f"❌ EasyOCR processing failed: {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "filename": filename
        }
