"""
Centralized OpenAI client management
"""
import os
import logging
from openai import OpenAI
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_openai_client(api_key: str = None) -> OpenAI:
    """
    Get a singleton OpenAI client instance.
    Uses environment variable if api_key not provided.
    """
    try:
        # Set API key in environment
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif "OPENAI_API_KEY" not in os.environ:
            raise ValueError("OpenAI API key not provided")

        # Create client with minimal config
        client = OpenAI()
        
        # Test the client
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=["test"],
            encoding_format="float"
        )
        if not response or not response.data:
            raise ValueError("Failed to validate OpenAI client")
            
        logger.info("✅ OpenAI client initialized successfully")
        return client
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI client: {e}")
        return None
