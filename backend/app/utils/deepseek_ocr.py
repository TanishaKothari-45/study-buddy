"""
DeepSeek-OCR integration for handwritten text recognition
"""
import torch
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import torchvision.transforms as T
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DeepSeekOCR:
    def __init__(self, model_name: str = "deepseek-ai/DeepSeek-OCR", device: str = None):
        """Initialize DeepSeek-OCR model"""
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Initializing DeepSeek-OCR on device: {self.device}")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True).to(self.device)
            self.model.eval()
            logger.info("✅ DeepSeek-OCR model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load DeepSeek-OCR model: {e}")
            raise

        # Define transforms (resize, normalize, etc)
        self.transform = T.Compose([
            T.Resize((1024, 1024)),
            T.ToTensor(),
            # normalization if needed
        ])

    def image_to_text(self, image: Image.Image) -> str:
        """Extract text from PIL image via DeepSeek-OCR model"""
        try:
            # Preprocess
            inp = self.transform(image).unsqueeze(0).to(self.device)
            # Prepare prompt prefix if needed
            prompt = "<image>\n<|grounding|>Convert the document to text."
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

            # Forward pass
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs.input_ids,
                    images=inp,
                    max_new_tokens=512
                )
            result = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Clean up the result (remove prompt prefix)
            if "<|grounding|>Convert the document to text." in result:
                result = result.split("<|grounding|>Convert the document to text.")[-1].strip()
            
            logger.info(f"✅ OCR extracted {len(result)} characters")
            return result
            
        except Exception as e:
            logger.error(f"❌ OCR processing failed: {e}")
            return ""

    def pdf_page_to_text(self, image_path: str) -> str:
        """Open page image and convert to text."""
        try:
            img = Image.open(image_path).convert("RGB")
            return self.image_to_text(img)
        except Exception as e:
            logger.error(f"❌ Failed to process image {image_path}: {e}")
            return ""

    def process_handwritten_answer(self, image_path: str, preprocess: bool = True) -> dict:
        """Process handwritten answer with optional preprocessing"""
        try:
            # Load image
            image = Image.open(image_path).convert("RGB")
            
            # Preprocess image if requested
            preprocessing_info = {}
            if preprocess:
                from .image_preprocessor import get_image_preprocessor
                preprocessor = get_image_preprocessor()
                if preprocessor:
                    preprocess_result = preprocessor.preprocess_image(image)
                    if preprocess_result["success"]:
                        image = preprocess_result["processed_image"]
                        preprocessing_info = preprocess_result["preprocessing_steps"]
                        logger.info("✅ Image preprocessing completed")
                    else:
                        logger.warning("⚠️ Image preprocessing failed, using original image")
                else:
                    logger.warning("⚠️ Image preprocessor not available, using original image")
            
            # Extract text using DeepSeek-OCR
            text = self.image_to_text(image)
            
            if not text.strip():
                return {
                    "success": False,
                    "text": "",
                    "error": "No text could be extracted from the image",
                    "preprocessing_info": preprocessing_info
                }
            
            # Basic text cleaning for handwritten content
            cleaned_text = self._clean_handwritten_text(text)
            
            return {
                "success": True,
                "text": cleaned_text,
                "original_text": text,
                "word_count": len(cleaned_text.split()),
                "confidence": "high" if len(cleaned_text) > 50 else "medium",
                "preprocessing_info": preprocessing_info
            }
            
        except Exception as e:
            logger.error(f"❌ Handwritten answer processing failed: {e}")
            return {
                "success": False,
                "text": "",
                "error": str(e),
                "preprocessing_info": preprocessing_info
            }

    def _clean_handwritten_text(self, text: str) -> str:
        """Clean and format handwritten text"""
        # Remove common OCR artifacts
        text = text.replace("|", "I")  # Common OCR mistake
        text = text.replace("0", "O")  # In context where it should be O
        text = text.replace("1", "l")  # In context where it should be l
        
        # Remove extra whitespace
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and len(line) > 2:  # Filter out very short lines
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

# Global instance for reuse
_ocr_instance = None

def get_deepseek_ocr() -> Optional[DeepSeekOCR]:
    """Get or create DeepSeek-OCR instance with lazy loading"""
    global _ocr_instance
    
    if _ocr_instance is None:
        try:
            # Check if we have the required dependencies
            import torch
            import transformers
            import addict
            import matplotlib
            import einops
            import easydict
            
            logger.info("🔄 Initializing DeepSeek-OCR (this may take a moment)...")
            _ocr_instance = DeepSeekOCR()
            logger.info("✅ DeepSeek-OCR initialized successfully")
        except ImportError as e:
            logger.warning(f"⚠️ DeepSeek-OCR dependencies not available: {e}")
            logger.info("To enable handwritten answer processing, install: pip install torch transformers torchvision addict matplotlib einops easydict")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize DeepSeek-OCR: {e}")
            logger.info("DeepSeek-OCR model loading failed. Handwritten answer processing will be disabled.")
            return None
    
    return _ocr_instance
