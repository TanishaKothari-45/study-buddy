"""
Setup script for Llama 3
Downloads and configures Llama 3 model for local use
"""

import os
import sys
import requests
from pathlib import Path
import hashlib
from tqdm import tqdm

# Configuration
MODELS_DIR = Path("models")
LLAMA_MODEL = {
    "name": "llama-2-7b-chat.Q4_K_M.gguf",  # 4-bit quantized version for efficiency
    "url": "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf",
    "size": 3791650816  # ~3.8GB
}

def download_file(url: str, destination: Path, expected_size: int) -> bool:
    """Download a file with progress bar"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Show progress bar
        progress = tqdm(
            total=expected_size,
            unit='iB',
            unit_scale=True,
            desc=f"Downloading {destination.name}"
        )
        
        # Download chunks
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                size = f.write(chunk)
                progress.update(size)
                
        progress.close()
        return True
        
    except Exception as e:
        print(f"Error downloading file: {e}")
        if destination.exists():
            destination.unlink()
        return False

def setup_llama():
    """Download and set up Llama model"""
    
    print("🦙 Setting up Llama 3...")
    
    # Create models directory
    MODELS_DIR.mkdir(exist_ok=True)
    
    # Check if model already exists
    model_path = MODELS_DIR / LLAMA_MODEL["name"]
    if model_path.exists():
        print(f"✅ Model already exists at {model_path}")
        return str(model_path.absolute())
        
    # Download model
    print(f"📥 Downloading {LLAMA_MODEL['name']}...")
    success = download_file(
        LLAMA_MODEL["url"],
        model_path,
        LLAMA_MODEL["size"]
    )
    
    if not success:
        print("❌ Failed to download model")
        return None
        
    print(f"✅ Model downloaded to {model_path}")
    
    # Set environment variable
    os.environ["LLAMA_MODEL_PATH"] = str(model_path.absolute())
    print(f"✅ Set LLAMA_MODEL_PATH={os.environ['LLAMA_MODEL_PATH']}")
    
    # Add to .env file
    env_path = Path(".env")
    env_content = f"LLAMA_MODEL_PATH={os.environ['LLAMA_MODEL_PATH']}\n"
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            current_env = f.read()
        if "LLAMA_MODEL_PATH" not in current_env:
            with open(env_path, 'a') as f:
                f.write(env_content)
    else:
        with open(env_path, 'w') as f:
            f.write(env_content)
            
    print("✅ Updated .env file")
    
    return str(model_path.absolute())

def test_llama():
    """Test Llama model"""
    try:
        from llama_cpp import Llama
        
        model_path = os.getenv("LLAMA_MODEL_PATH")
        if not model_path:
            print("❌ LLAMA_MODEL_PATH not set")
            return False
            
        print("🧪 Testing Llama model...")
        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_batch=512
        )
        
        # Simple test prompt
        response = llm("What is the capital of India?", max_tokens=50)
        print(f"Test response: {response['choices'][0]['text']}")
        
        print("✅ Llama test successful!")
        return True
        
    except Exception as e:
        print(f"❌ Llama test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Setting up Llama 3 for Study Buddy...")
    
    # Setup Llama
    model_path = setup_llama()
    if not model_path:
        print("❌ Setup failed")
        sys.exit(1)
        
    # Test Llama
    if not test_llama():
        print("❌ Tests failed")
        sys.exit(1)
        
    print("\n🎉 Llama 3 setup complete!")
    print("\nNext steps:")
    print("1. Make sure LLAMA_MODEL_PATH is in your environment")
    print("2. Restart the backend server")
    print("3. Try the Geography agent with Llama")
