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
        # Split texts that are too long (OpenAI limit: 8192 tokens ≈ 6000 words)
        # Use VERY conservative limit: 1500 words ≈ 1950 tokens (very safe)
        cleaned_texts = []
        MAX_WORDS = 1500  # Very conservative limit: ~1950 tokens (well under 8192)
        
        def split_text_by_sentences(text: str, max_words: int, overlap_words: int = 100) -> List[str]:
            """Split long text by sentences with overlap"""
            import re
            
            words = text.split()
            word_count = len(words)
            
            if word_count <= max_words:
                return [text]
            
            # Split by sentences
            sentences = re.split(r'([.!?]+\s+)', text)
            sentence_list = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    sentence_list.append(sentences[i] + sentences[i + 1])
                else:
                    sentence_list.append(sentences[i])
            
            # Fallback to word-based if no sentences
            if len(sentence_list) <= 1:
                chunks = []
                for i in range(0, word_count, max_words - overlap_words):
                    chunk = " ".join(words[i:i + max_words])
                    if chunk.strip():
                        chunks.append(chunk)
                return chunks
            
            # Build chunks from sentences
            chunks = []
            current_chunk = []
            current_word_count = 0
            
            for sentence in sentence_list:
                sentence_words = sentence.split()
                sentence_word_count = len(sentence_words)
                
                if current_word_count + sentence_word_count > max_words and current_chunk:
                    chunk_text = "".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    
                    # Overlap: last N words
                    overlap_text = " ".join(words[max(0, current_word_count - overlap_words):current_word_count])
                    current_chunk = [overlap_text + " "] if overlap_text else []
                    current_word_count = len(overlap_text.split()) if overlap_text else 0
                
                current_chunk.append(sentence)
                current_word_count += sentence_word_count
            
            if current_chunk:
                chunk_text = "".join(current_chunk).strip()
                if chunk_text:
                    chunks.append(chunk_text)
            
            return chunks if chunks else [text]
        
        # Track which original texts were split (for metadata handling by caller)
        text_split_map = {}  # Maps original index -> list of split indices
        
        for i, text in enumerate(texts):
            if isinstance(text, str) and text.strip():
                words = text.split()
                word_count = len(words)
                # If text is too long, split it instead of truncating
                if word_count > MAX_WORDS:
                    logger.warning(f"⚠️ Text {i+1} too long ({word_count} words), splitting into smaller chunks...")
                    split_chunks = split_text_by_sentences(text, MAX_WORDS, overlap_words=100)
                    logger.info(f"   ✅ Split into {len(split_chunks)} chunks")
                    # Store split info for caller
                    start_idx = len(cleaned_texts)
                    cleaned_texts.extend([chunk.strip() for chunk in split_chunks if chunk.strip()])
                    end_idx = len(cleaned_texts)
                    text_split_map[i] = list(range(start_idx, end_idx))
                else:
                    cleaned_texts.append(text.strip())
            elif text:  # Non-empty but not string - convert to string
                text_str = str(text).strip()
                words = text_str.split()
                word_count = len(words)
                if word_count > MAX_WORDS:
                    logger.warning(f"⚠️ Text {i+1} too long ({word_count} words), splitting into smaller chunks...")
                    split_chunks = split_text_by_sentences(text_str, MAX_WORDS, overlap_words=100)
                    logger.info(f"   ✅ Split into {len(split_chunks)} chunks")
                    start_idx = len(cleaned_texts)
                    cleaned_texts.extend([chunk.strip() for chunk in split_chunks if chunk.strip()])
                    end_idx = len(cleaned_texts)
                    text_split_map[i] = list(range(start_idx, end_idx))
                else:
                    cleaned_texts.append(text_str)
        
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
        """
        Generate embeddings using OpenAI first, falling back to Sentence Transformers.
        WARNING: Only use this if you don't care about dimension consistency.
        For collections with existing data, use get_openai_embeddings() or get_sbert_embeddings() directly.
        """
        if not texts:
            return []

        if self.openai_client:
            try:
                embeddings = self.get_openai_embeddings(texts)
                logger.info(f"✅ Using OpenAI embeddings (1536 dimensions)")
                return embeddings
            except Exception as e:
                logger.warning(f"⚠️ OpenAI embedding failed, falling back to Sentence Transformers: {e}")
                logger.warning(f"   ⚠️ WARNING: This will create 384-dim embeddings instead of 1536-dim!")
                logger.warning(f"   ⚠️ This may cause dimension mismatch if collection already has 1536-dim embeddings!")
                
        embeddings = self.get_sbert_embeddings(texts)
        logger.info(f"✅ Using Sentence Transformers embeddings (384 dimensions)")
        return embeddings