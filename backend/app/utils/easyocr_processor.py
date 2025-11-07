"""
EasyOCR processor for handwritten and printed text recognition
Lightweight, fast, and CPU-friendly alternative to DeepSeek-OCR
Optimized with preprocessing and faster OCR settings
"""
import os
import logging
from typing import Dict, Any, Optional
from PIL import Image
import io
import numpy as np

# Suppress NNPACK warnings from PyTorch (not supported on all hardware)
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
os.environ['TORCH_NNPACK_DISABLE'] = '1'

# Suppress warnings before importing torch-dependent libraries
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='nnpack')

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
            # Try to use quantize for faster inference (if supported)
            try:
                _ocr_reader = easyocr.Reader(['en'], gpu=False, quantize=True)  # CPU mode with quantization
                logger.info("✅ EasyOCR initialized successfully (CPU mode, optimized with quantization)")
            except TypeError:
                # quantize parameter not available in this version, use default
                _ocr_reader = easyocr.Reader(['en'], gpu=False)  # CPU mode
                logger.info("✅ EasyOCR initialized successfully (CPU mode)")
        except ImportError:
            logger.error("❌ EasyOCR not installed. Install with: pip install easyocr")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize EasyOCR: {e}")
            return None
    
    return _ocr_reader

def preprocess_image_for_ocr(image: Image.Image, max_size: int = 1200) -> Image.Image:
    """
    Fast preprocessing pipeline for OCR:
    1. Convert to grayscale
    2. Resize if too large (maintains aspect ratio)
    3. Denoise
    4. Enhance contrast
    
    Args:
        image: PIL Image in RGB format
        max_size: Maximum dimension for resizing (default 1600px for speed)
    
    Returns:
        Preprocessed PIL Image ready for OCR
    """
    try:
        import cv2
        
        # Convert PIL to OpenCV format
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        original_size = cv_image.shape[:2]
        
        # Step 1: Resize if image is too large (speed optimization)
        h, w = cv_image.shape[:2]
        max_dim = max(h, w)
        
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            cv_image = cv2.resize(cv_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.info(f"📐 Resized image from {original_size} to {(new_h, new_w)}")
        
        # Step 2: Convert to grayscale
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        # Step 3: Fast denoising (bilateral filter - preserves edges)
        denoised = cv2.bilateralFilter(gray, 5, 50, 50)
        
        # Step 4: Enhance contrast using CLAHE (fast and effective)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Convert back to PIL Image (as RGB for EasyOCR compatibility)
        # EasyOCR works better with grayscale but expects 3-channel, so convert
        processed_pil = Image.fromarray(enhanced).convert("RGB")
        
        logger.info("✅ Image preprocessing completed (grayscale, denoise, contrast)")
        return processed_pil
        
    except ImportError:
        logger.warning("⚠️ OpenCV not available, skipping preprocessing")
        # If OpenCV not available, just resize if too large
        w, h = image.size
        max_dim = max(w, h)
        if max_dim > max_size:
            scale = max_size / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            return image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        return image
    except Exception as e:
        logger.warning(f"⚠️ Preprocessing failed: {e}, using original image")
        return image

def process_image_with_easyocr(
    image: Image.Image, 
    filename: str = "image",
    preprocess: bool = True,
    max_image_size: int = 1200
) -> Dict[str, Any]:
    """
    Process image with EasyOCR for text extraction
    Optimized for speed with preprocessing and faster OCR parameters
    
    Args:
        image: PIL Image to process
        filename: Name of the file for logging
        preprocess: Whether to apply preprocessing (default: True)
        max_image_size: Maximum dimension for resizing (default: 1600px)
    
    Returns:
        Dictionary with extraction results
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
        
        original_size = image.size
        logger.info(f"📄 Processing image with EasyOCR: {filename} ({original_size})")
        
        # Preprocess image for better OCR accuracy and speed
        if preprocess:
            processed_image = preprocess_image_for_ocr(image, max_size=max_image_size)
            logger.info(f"📐 Preprocessed image: {original_size} -> {processed_image.size}")
        else:
            processed_image = image
        
        # Convert PIL image to numpy array for EasyOCR
        image_array = np.array(processed_image)
        
        # Run OCR with optimized parameters for speed
        # detail=1: Get bbox, text, confidence (needed for confidence filtering)
        # paragraph=False: Don't group into paragraphs (faster)
        # Optimized thresholds for better text detection
        results = reader.readtext(
            image_array,
            detail=1,  # Get detailed results for confidence filtering
            paragraph=False,  # Faster: don't group into paragraphs
            width_ths=0.7,  # Threshold for merging text boxes
            height_ths=0.7,
            slope_ths=0.1,  # Allow slight slopes for handwritten text
            ycenter_ths=0.5,
            allowlist=None,  # Allow all characters
            blocklist=None
        )
        
        # Extract text from results
        # Results are (bbox, text, confidence) tuples
        extracted_text = ""
        confidence_scores = []
        
        for result in results:
            if len(result) == 3:
                # Standard format: (bbox, text, confidence)
                bbox, text, confidence = result
            elif len(result) == 2:
                # Fallback: (bbox, text) - no confidence provided
                bbox, text = result
                confidence = 0.5  # Default confidence if not provided
            else:
                # Fallback: just text
                text = str(result)
                confidence = 0.5
            
            # Filter low-confidence detections but keep threshold lower for handwritten
            if confidence > 0.25:  # Lower threshold for handwritten text
                extracted_text += text + " "
                confidence_scores.append(confidence)
        
        extracted_text = extracted_text.strip()
        
        if not extracted_text:
            logger.warning("⚠️ No text extracted from image")
            return {
                "success": False,
                "text": "",
                "error": "No text could be extracted from the image. Try improving image quality or lighting.",
                "filename": filename,
                "preprocessing_applied": preprocess
            }
        
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        logger.info(f"✅ Extracted {len(extracted_text)} characters (avg confidence: {avg_confidence:.2f})")
        
        return {
            "success": True,
            "text": extracted_text,
            "word_count": len(extracted_text.split()),
            "filename": filename,
            "original_image_size": original_size,
            "processed_image_size": processed_image.size if preprocess else original_size,
            "confidence": avg_confidence,
            "detections": len(results),
            "preprocessing_applied": preprocess
        }
        
    except Exception as e:
        logger.error(f"❌ EasyOCR processing failed: {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "filename": filename,
            "preprocessing_applied": preprocess
        }
