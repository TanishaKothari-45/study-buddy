"""
DeepSeek-OCR API endpoint
Robust OCR processing with proper error handling
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image
import io
import logging
from typing import Dict, Any
import tempfile
import os
import torch

from ..utils.deepseek_loader import load_deepseek_model, get_model_info
from ..utils.easyocr_processor import process_image_with_easyocr

logger = logging.getLogger(__name__)
router = APIRouter()

# Global model instance
_model = None
_tokenizer = None

def get_model():
    """Get or load the DeepSeek-OCR model"""
    global _model, _tokenizer
    
    if _model is None or _tokenizer is None:
        try:
            _model, _tokenizer = load_deepseek_model()
        except Exception as e:
            logger.error(f"❌ Failed to initialize DeepSeek-OCR model: {e}")
            raise RuntimeError(f"OCR model initialization failed: {str(e)}")
    
    return _model, _tokenizer

def process_image_ocr(image: Image.Image, filename: str = "image") -> Dict[str, Any]:
    """
    Direct OCR processing function (can be called without HTTP)
    """
    try:
        # Get model and tokenizer
        model, tokenizer = get_model()
        
        logger.info(f"📄 Processing image: {filename} ({image.size})")
        
        # DeepSeek prompt style for better text extraction
        prompt = "<image>\n<|grounding|>Extract handwritten or printed text clearly. Preserve the original formatting and structure."
        
        # Save to a temporary file and pass path to model (some builds expect a path)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_path = tmp.name
            image.save(temp_path, format="PNG")
        try:
            with torch.no_grad():
                outputs = model.infer(
                    tokenizer,
                    prompt=prompt,
                    image_file=temp_path,
                    base_size=1024,
                    image_size=640,
                    crop_mode=True,
                    save_results=False
                )
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        
        # Extract text from output
        if outputs and len(outputs) > 0:
            extracted_text = outputs[0].text.strip()
            logger.info(f"✅ Extracted {len(extracted_text)} characters")
            
            return {
                "success": True,
                "text": extracted_text,
                "word_count": len(extracted_text.split()),
                "filename": filename,
                "image_size": image.size
            }
        else:
            logger.warning("⚠️ No text extracted from image")
            return {
                "success": False,
                "text": "",
                "error": "No text could be extracted from the image",
                "filename": filename
            }
            
    except Exception as e:
        logger.error(f"❌ OCR processing failed: {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "filename": filename
        }

@router.post("/ocr")
async def deepseek_ocr(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Extract text from uploaded image using DeepSeek-OCR
    """
    try:
        # Get model and tokenizer
        model, tokenizer = get_model()
        
        # Read and process image
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        logger.info(f"📄 Processing image: {file.filename} ({image.size})")
        
        # DeepSeek prompt style for better text extraction
        prompt = "<image>\n<|grounding|>Extract handwritten or printed text clearly. Preserve the original formatting and structure."
        
        # Save to a temporary file and pass path to model (some builds expect a path)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_path = tmp.name
            image.save(temp_path, format="PNG")
        try:
            with torch.no_grad():
                outputs = model.infer(
                    tokenizer,
                    prompt=prompt,
                    image_file=temp_path,
                    base_size=1024,
                    image_size=640,
                    crop_mode=True,
                    save_results=False
                )
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        
        # Extract text from output
        if outputs and len(outputs) > 0:
            extracted_text = outputs[0].text.strip()
            logger.info(f"✅ Extracted {len(extracted_text)} characters")
            
            return {
                "success": True,
                "text": extracted_text,
                "word_count": len(extracted_text.split()),
                "filename": file.filename,
                "image_size": image.size
            }
        else:
            logger.warning("⚠️ No text extracted from image")
            return {
                "success": False,
                "text": "",
                "error": "No text could be extracted from the image",
                "filename": file.filename
            }
            
    except Exception as e:
        logger.error(f"❌ OCR processing failed: {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "filename": file.filename
        }

@router.post("/ocr-batch")
async def deepseek_ocr_batch(files: list[UploadFile] = File(...)) -> Dict[str, Any]:
    """
    Process multiple images in batch
    """
    results = []
    
    for file in files:
        try:
            result = await deepseek_ocr(file)
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "text": "",
                "error": str(e),
                "filename": file.filename
            })
    
    successful = sum(1 for r in results if r["success"])
    total_text = "\n\n".join(r["text"] for r in results if r["success"])
    
    return {
        "success": successful > 0,
        "results": results,
        "successful_count": successful,
        "total_count": len(files),
        "combined_text": total_text
    }

@router.get("/model-info")
async def get_model_info_endpoint() -> Dict[str, Any]:
    """Get model and system information"""
    try:
        return get_model_info()
    except Exception as e:
        return {"error": str(e)}

@router.post("/test-ocr")
async def test_ocr() -> Dict[str, Any]:
    """Test OCR functionality with a simple check"""
    try:
        model, tokenizer = get_model()
        return {
            "success": True,
            "message": "DeepSeek-OCR is ready",
            "model_loaded": model is not None,
            "tokenizer_loaded": tokenizer is not None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"DeepSeek-OCR test failed: {str(e)}"
        }

@router.post("/easyocr")
async def easyocr_endpoint(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    EasyOCR endpoint - CPU-friendly OCR for handwritten text
    Recommended for CPU environments
    """
    try:
        # Read and process image
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # Process with EasyOCR
        result = process_image_with_easyocr(image, file.filename)
        return result
        
    except Exception as e:
        logger.error(f"❌ EasyOCR processing failed: {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "filename": file.filename
        }