"""
DeepSeek-OCR Model Loader
Robust model loading with proper error handling and version compatibility
"""
import torch
from transformers import AutoModel, AutoTokenizer
import logging

logger = logging.getLogger(__name__)

def load_deepseek_model(model_name="deepseek-ai/DeepSeek-OCR"):
    """
    Load DeepSeek-OCR model with proper configuration
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"🔄 Loading DeepSeek-OCR model on {device}")

    try:
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            trust_remote_code=True
        )
        logger.info("✅ Tokenizer loaded successfully")

        # Load model with specific configuration
        model = AutoModel.from_pretrained(
            model_name,
            trust_remote_code=True,
            use_safetensors=True,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        
        # Set to evaluation mode
        model.eval()
        
        # Move to device if not using device_map
        if device == "cpu":
            model = model.to(device)
        
        logger.info(f"✅ DeepSeek-OCR model loaded successfully on {device}")
        return model, tokenizer

    except Exception as e:
        logger.error(f"❌ Failed to load DeepSeek-OCR: {e}")
        raise RuntimeError(f"DeepSeek-OCR model loading failed: {e}")

def get_model_info():
    """Get model and system information"""
    return {
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "model_name": "deepseek-ai/DeepSeek-OCR"
    }

