"""
Test OpenAI API key and embeddings
"""
import os
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

def test_openai():
    # Load environment variables (go up 2 levels to project root)
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    print(f"\nLoading .env from: {env_path}")
    load_dotenv(env_path)
    
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"API Key found: {bool(api_key)}")
    if api_key:
        print(f"API Key: ")
    
    try:
        print("\nTesting OpenAI connection...")
        client = OpenAI(api_key=api_key)
        
        print("Making API call...")
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=["Hello world"]
        )
        
        print("\nSuccess! Here's the first 10 dimensions of the embedding:")
        print(resp.data[0].embedding[:10])
        
    except Exception as e:
        print(f"\nError occurred: {type(e).__name__}")
        print(f"Error message: {str(e)}")

if __name__ == "__main__":
    test_openai()
