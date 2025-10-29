"""
Text embedding utilities using OpenAI's text-embedding-3-small with Sentence Transformers fallback
"""
import logging
import os
from typing import List
import time
from openai import OpenAI, RateLimitError
from sentence_transformers import SentenceTransformer
from ..core.config import settings

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self):
        """Initialize embedders"""
        self.openai_client = None
        self.sbert_model = None
        
        # Try to initialize OpenAI first
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI initialization failed: {e}")
        
        # Always initialize Sentence Transformers as fallback
        try:
            self.sbert_model = SentenceTransformer(settings.FALLBACK_MODEL)
            logger.info(f"✅ Sentence Transformers initialized with model: {settings.FALLBACK_MODEL}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Sentence Transformers: {e}")
            if not self.openai_client:
                raise RuntimeError("No embedding models available")

    def get_openai_embeddings(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """Generate embeddings using OpenAI with retry logic"""
        wait_time = 1.0
        
        # Ensure texts is a list of non-empty strings
        if not texts:
            return []
        
        # Filter out empty strings and ensure all are strings
        cleaned_texts = []
        for text in texts:
            if isinstance(text, str) and text.strip():
                cleaned_texts.append(text.strip())
            elif text:  # Non-empty but not string - convert to string
                cleaned_texts.append(str(text).strip())
        
        if not cleaned_texts:
            logger.warning("⚠️ No valid texts to embed")
            return []
        
        for attempt in range(max_retries):
            try:
                response = self.openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=cleaned_texts
                )
                embeddings = [data.embedding for data in response.data]
                logger.info(f"✅ Generated {len(embeddings)} embeddings using OpenAI")
                return embeddings
                
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    wait_time *= 2
                else:
                    logger.warning("⚠️ Rate limit persists, falling back to Sentence Transformers")
                    raise
            except Exception as e:
                logger.error(f"❌ OpenAI embedding failed: {e}")
                raise

    def get_sbert_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Sentence Transformers"""
        try:
            embeddings = self.sbert_model.encode(texts)
            if hasattr(embeddings, "tolist"):
                embeddings = embeddings.tolist()
            logger.info(f"✅ Generated {len(embeddings)} embeddings using Sentence Transformers")
            return embeddings
        except Exception as e:
            logger.error(f"❌ Sentence Transformers embedding failed: {e}")
            raise

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI first, falling back to Sentence Transformers"""
        if not texts:
            return []

        if self.openai_client:
            try:
                return self.get_openai_embeddings(texts)
            except Exception as e:
                logger.warning(f"⚠️ OpenAI embedding failed, falling back to Sentence Transformers: {e}")
                
        return self.get_sbert_embeddings(texts)