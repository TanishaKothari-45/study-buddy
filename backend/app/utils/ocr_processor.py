"""
OCR processing utilities for handwritten English text
Supports multiple image formats and PDFs with images
"""
import logging
import os
from typing import List, Dict, Any, Optional
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import easyocr
from pdf2image import convert_from_path
import cv2

logger = logging.getLogger(__name__)

# Initialize EasyOCR reader (lazy loading)
_ocr_reader = None

def get_ocr_reader():
    """Initialize and return EasyOCR reader (singleton pattern)"""
    global _ocr_reader
    if _ocr_reader is None:
        logger.info("🔧 Initializing EasyOCR reader for English...")
        # Initialize EasyOCR with English language support
        # gpu=False uses CPU (set to True if you have CUDA GPU)
        _ocr_reader = easyocr.Reader(['en'], gpu=False)
        logger.info("✅ EasyOCR reader initialized")
    return _ocr_reader

def preprocess_image(image: Image.Image, enhance_contrast: bool = True, 
                     denoise: bool = True, deskew: bool = True) -> Image.Image:
    """
    Preprocess image to improve OCR accuracy
    
    Args:
        image: PIL Image object
        enhance_contrast: Enhance contrast for better text visibility
        denoise: Remove noise from image
        deskew: Correct image skew/rotation
    
    Returns:
        Preprocessed PIL Image
    """
    # Convert to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Convert PIL to numpy array for OpenCV processing
    img_array = np.array(image)
    
    # Convert RGB to BGR for OpenCV
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # Denoise
    if denoise:
        # Apply bilateral filter to reduce noise while keeping edges sharp
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        # Alternative: Non-local means denoising (slower but better)
        # gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    
    # Enhance contrast
    if enhance_contrast:
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    
    # Deskew (correct rotation)
    if deskew:
        # Detect skew angle
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            
            # Only correct if angle is significant (> 1 degree)
            if abs(angle) > 1:
                (h, w) = gray.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h), 
                                     flags=cv2.INTER_CUBIC, 
                                     borderMode=cv2.BORDER_REPLICATE)
    
    # Convert back to PIL Image
    processed_image = Image.fromarray(gray)
    
    return processed_image

def extract_text_from_image(image_path: str, preprocess: bool = True, 
                           sample_reference: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract text from a single image using OCR
    
    Args:
        image_path: Path to image file
        preprocess: Whether to preprocess image before OCR
        sample_reference: Optional reference text from sample sheet (for future use)
    
    Returns:
        Dictionary with extracted text and metadata
    """
    try:
        # Load image
        image = Image.open(image_path)
        logger.info(f"📷 Processing image: {image_path} ({image.size[0]}x{image.size[1]})")
        
        # Preprocess if requested
        if preprocess:
            logger.info("🔧 Preprocessing image (contrast, denoise, deskew)...")
            image = preprocess_image(image)
        
        # Get OCR reader
        reader = get_ocr_reader()
        
        # Perform OCR
        logger.info("🔍 Running OCR on image...")
        results = reader.readtext(np.array(image))
        
        # Extract text and confidence scores
        extracted_text = []
        confidences = []
        bounding_boxes = []
        
        for (bbox, text, confidence) in results:
            # Filter out low-confidence results (threshold: 0.3)
            if confidence > 0.3:
                extracted_text.append(text)
                confidences.append(confidence)
                bounding_boxes.append(bbox)
        
        # Combine all text
        full_text = " ".join(extracted_text)
        
        # Calculate average confidence
        avg_confidence = np.mean(confidences) if confidences else 0.0
        
        logger.info(f"✅ OCR completed: {len(extracted_text)} text regions found")
        logger.info(f"   • Average confidence: {avg_confidence:.2%}")
        logger.info(f"   • Extracted text length: {len(full_text)} characters")
        
        return {
            "text": full_text,
            "confidence": avg_confidence,
            "num_regions": len(extracted_text),
            "raw_results": results,
            "preprocessed": preprocess
        }
        
    except Exception as e:
        logger.error(f"❌ Error extracting text from image {image_path}: {e}")
        raise

def extract_text_from_pdf_images(pdf_path: str, preprocess: bool = True,
                                 sample_reference: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract text from PDF by converting pages to images and running OCR
    
    Args:
        pdf_path: Path to PDF file
        preprocess: Whether to preprocess images before OCR
        sample_reference: Optional reference text from sample sheet
    
    Returns:
        List of dictionaries, one per page, with extracted text and metadata
    """
    pages_content = []
    
    try:
        logger.info(f"📄 Converting PDF to images: {pdf_path}")
        # Convert PDF pages to images (300 DPI for good quality)
        images = convert_from_path(pdf_path, dpi=300, fmt='png')
        logger.info(f"   • Converted {len(images)} pages to images")
        
        for i, image in enumerate(images):
            logger.info(f"   • Processing page {i + 1}/{len(images)}...")
            
            # Save temporary image
            temp_image_path = f"/tmp/pdf_page_{i}.png"
            image.save(temp_image_path, 'PNG')
            
            try:
                # Extract text from image
                result = extract_text_from_image(temp_image_path, preprocess, sample_reference)
                
                pages_content.append({
                    "page_number": i + 1,
                    "text": result["text"],
                    "confidence": result["confidence"],
                    "num_regions": result["num_regions"]
                })
                
            finally:
                # Clean up temporary image
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
        
        logger.info(f"✅ Successfully processed {len(pages_content)} pages")
        
    except Exception as e:
        logger.error(f"❌ Error processing PDF images {pdf_path}: {e}")
        raise
    
    return pages_content

def clean_ocr_text(text: str) -> str:
    """
    Clean OCR-extracted text to remove common artifacts and noise
    
    Args:
        text: Raw OCR text
    
    Returns:
        Cleaned text
    """
    import re
    
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove lines that are mostly special characters (likely noise)
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        # Skip lines that are mostly special characters
        alnum_count = sum(1 for c in line_stripped if c.isalnum())
        if len(line_stripped) > 0 and alnum_count / len(line_stripped) < 0.3:
            continue
        
        # Skip very short lines that are just symbols
        if len(line_stripped) < 3 and not any(c.isalnum() for c in line_stripped):
            continue
        
        cleaned_lines.append(line_stripped)
    
    # Join lines back
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Remove excessive repeated characters (but keep intentional ones)
    cleaned_text = re.sub(r'(.)\1{4,}', r'\1\1\1\1', cleaned_text)
    
    return cleaned_text.strip()

def process_handwritten_document(file_path: str, file_type: str, 
                                 preprocess: bool = True,
                                 sample_reference: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Main function to process handwritten documents (images or PDFs)
    
    Args:
        file_path: Path to file
        file_type: File extension (jpg, png, pdf, etc.)
        preprocess: Whether to preprocess images
        sample_reference: Optional reference text from sample sheet
    
    Returns:
        List of page dictionaries with extracted text
    """
    file_type_lower = file_type.lower()
    
    if file_type_lower in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif']:
        # Single image file
        result = extract_text_from_image(file_path, preprocess, sample_reference)
        cleaned_text = clean_ocr_text(result["text"])
        
        return [{
            "page_number": 1,
            "text": cleaned_text,
            "confidence": result["confidence"],
            "num_regions": result["num_regions"]
        }]
    
    elif file_type_lower == 'pdf':
        # PDF file - convert to images and OCR
        pages_content = extract_text_from_pdf_images(file_path, preprocess, sample_reference)
        
        # Clean text for each page
        for page in pages_content:
            page["text"] = clean_ocr_text(page["text"])
        
        return pages_content
    
    else:
        raise ValueError(f"Unsupported file type for OCR: {file_type}")


