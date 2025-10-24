"""
Text embedding utilities
"""
import os
import logging
import time
from typing import List
from openai import OpenAI, RateLimitError
from sentence_transformers import SentenceTransformer
from ..core.config import settings
from ..core.env import load_env_vars

# Ensure environment variables are loaded
load_env_vars()

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self):
        """Initialize embedding models"""
        self.openai_client = None
        self.sbert_model = None
        
        # Try OpenAI first
        api_key = os.getenv("OPENAI_API_KEY")
        print(f"api_key: {api_key}")
        if api_key:
            try:
                self.openai_client = OpenAI(api_key=api_key)
                print("\nTesting OpenAI connection:")
                print(f"- Using API key: {api_key}")
                print(f"- Model: {settings.EMBEDDING_MODEL}")
                
                # Test the connection
                response = self.openai_client.embeddings.create(
                    model=settings.EMBEDDING_MODEL,
                    input=["test"],
                    encoding_format="float"
                )
                if response and response.data:
                    logger.info("✅ OpenAI embeddings initialized")
                    return
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"⚠️ OpenAI initialization failed: {error_msg}")
                print("\nOpenAI Error Details:")
                print(f"- Error type: {type(e).__name__}")
                print(f"- Error message: {error_msg}")
                if "quota" in error_msg.lower():
                    print("⚠️ This appears to be a quota issue. Please check:")
                    print("1. Your API key is correct")
                    print("2. You have sufficient quota in your OpenAI account")
                    print("3. You're using the correct OpenAI account")
                self.openai_client = None
        
        # Initialize Sentence Transformers as fallback
        try:
            self.sbert_model = SentenceTransformer(settings.FALLBACK_MODEL)
            logger.info("✅ Using Sentence Transformers as fallback")
        except Exception as e:
            logger.error(f"❌ Sentence Transformers initialization failed: {e}")
            raise RuntimeError("No embedding model available")

    def get_embeddings(self, texts: List[str], max_retries: int = 3, initial_wait: float = 1.0) -> List[List[float]]:
        """Generate embeddings with automatic fallback and rate limit handling"""
        if not texts:
            return []

        # Try OpenAI first
        if self.openai_client:
            wait_time = initial_wait
            for attempt in range(max_retries):
                try:
                    response = self.openai_client.embeddings.create(
                        model=settings.EMBEDDING_MODEL,
                        input=texts,
                        encoding_format="float"
                    )
                    embeddings = [d.embedding for d in response.data]
                    logger.info(f"✅ Generated {len(embeddings)} OpenAI embeddings")
                    return embeddings
                except RateLimitError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        wait_time *= 2  # Exponential backoff
                    else:
                        logger.warning(f"⚠️ Rate limit persists after {max_retries} retries, falling back...")
                        break
                except Exception as e:
                    logger.warning(f"⚠️ OpenAI embeddings failed: {e}")
                    if not self.sbert_model:
                        raise RuntimeError("OpenAI failed and no fallback available")
                    break

        # Use Sentence Transformers
        if self.sbert_model:
            try:
                embeddings = self.sbert_model.encode(texts)
                if hasattr(embeddings, "tolist"):
                    embeddings = embeddings.tolist()
                logger.info(f"✅ Generated {len(embeddings)} Sentence Transformer embeddings")
                return embeddings
            except Exception as e:
                logger.error(f"❌ Sentence Transformer embeddings failed: {e}")
                raise

        raise RuntimeError("No embedding model available")