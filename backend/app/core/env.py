"""
Environment variable handling
"""
import os
from pathlib import Path
from dotenv import load_dotenv

def load_env_vars():
    """Load environment variables from .env file"""
    # Get the project root directory (2 levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    env_path = project_root / ".env"
    
    # Load .env file
    load_dotenv(env_path)
    
    # Debug output
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"\nEnvironment Loading:")
    print(f"- .env path: {env_path}")
    print(f"- .env file exists: {env_path.exists()}")
    print(f"- OpenAI API Key found: {bool(api_key)}")
    if api_key:
        print(f"- API Key: {api_key}")  # Print full key for debugging
        if api_key.startswith('sk-'):
            print("- API Key format looks valid (starts with 'sk-')")
        else:
            print("⚠️ Warning: API Key doesn't start with 'sk-', might be invalid")
