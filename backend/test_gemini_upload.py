import asyncio
import os
import sys
import time
import logging
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.gemini_core.gemini_client import GeminiClient
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_upload():
    api_key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment or settings")
        return

    client = GeminiClient(api_key=api_key, model_name=settings.GEMINI_MODEL_PRO)
    
    # Create a small dummy file
    dummy_file = Path("test_upload.jpg")
    with open(dummy_file, "wb") as f:
        f.write(b"\x00" * 1024 * 10) # 10KB
        
    print(f"🚀 Starting test upload with timeout {client.timeout}s...")
    start_time = time.time()
    
    try:
        # Use a real image mime type to avoid server-side rejection
        result = await client._upload_file_with_retry(str(dummy_file), "image/jpeg")
        elapsed = time.time() - start_time
        print(f"✅ Upload successful in {elapsed:.2f}s!")
        print(f"Result: {result['name']}")
        
        # Cleanup from Gemini
        await client._delete_file_async(result['name'])
        print("✅ Cleaned up from Gemini")
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Upload failed after {elapsed:.2f}s")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if dummy_file.exists():
            dummy_file.unlink()

if __name__ == "__main__":
    asyncio.run(test_upload())
