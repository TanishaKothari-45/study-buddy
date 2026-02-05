"""
Text embedding utilities using OpenAI's text-embedding-3-small with Sentence Transformers fallback (lazy-loaded)
"""
import logging
import os
from typing import List, Optional
import time
from openai import OpenAI, RateLimitError
from ..core.config import settings

logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self):
        """Initialize embedders (SentenceTransformer lazy-loaded only when needed)"""
        self.openai_client = None
        self._sbert_model: Optional[any] = None  # Lazy-loaded
        
        # Try to initialize OpenAI first
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI initialization failed: {e}")
        
        # SentenceTransformer is now lazy-loaded (see _get_sbert_model())
        logger.info("ℹ️  SentenceTransformer will be loaded only when needed (lazy-loaded)")
    
    def _get_sbert_model(self):
        """
        Lazy-load SentenceTransformer model only when actually needed.
        This avoids startup overhead when OpenAI embeddings are used.
        """
        if self._sbert_model is not None:
            return self._sbert_model
        
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"🔧 Loading SentenceTransformer model: {settings.FALLBACK_MODEL} (lazy-loaded)...")
            self._sbert_model = SentenceTransformer(settings.FALLBACK_MODEL)
            logger.info(f"✅ SentenceTransformer initialized with model: {settings.FALLBACK_MODEL}")
            return self._sbert_model
        except Exception as e:
            logger.error(f"❌ Failed to initialize SentenceTransformer: {e}")
            if not self.openai_client:
                raise RuntimeError("No embedding models available")
            raise

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
        MAX_WORDS = settings.MAX_CHAPTER_CHUNK_WORDS
        
        # Conservative character limit (8192 tokens * ~3 chars/token = ~24.5k chars)
        # We use 20k to be extremely safe against base64/dense text
        MAX_CHARS = 24000
        
        def split_text_by_sentences(text: str, max_words: int, overlap_words: int = 200) -> List[str]:
            """Split long text by sentences with overlap, enforcing char limits"""
            import re
            
            words = text.split()
            word_count = len(words)
            char_count = len(text)
            
            # If within limits, return original
            if word_count <= max_words and char_count <= MAX_CHARS:
                return [text]
                
            # SPECIAL CASE: Low word count but high char count (e.g., base64, long URL, biological sequence)
            # Force hard split by characters
            if char_count > MAX_CHARS and word_count < (max_words // 2):
                logger.warning(f"⚠️ Dense text detected (len={char_count}, words={word_count}). Force splitting by chars.")
                chunk_size = 20000
                chunks = []
                for i in range(0, char_count, chunk_size):
                    chunks.append(text[i:i + chunk_size])
                return chunks
            
            # Normal splitting by sentences
            sentences = re.split(r'([.!?]+\s+)', text)
            sentence_list = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    sentence_list.append(sentences[i] + sentences[i + 1])
                else:
                    sentence_list.append(sentences[i])
            
            # Fallback to word-based if no sentences found (or only 1 huge sentence)
            if len(sentence_list) <= 1:
                # Check if even word splitting is viable
                if word_count <= max_words: 
                    # If words are few but chars are many (caught above ideally, but safety net)
                     if len(text) > MAX_CHARS:
                        return [text[i:i+MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]
                     return [text]
                     
                chunks = []
                # Word-based splitting
                for i in range(0, word_count, max_words - overlap_words):
                    chunk_words = words[i:i + max_words]
                    chunk = " ".join(chunk_words)
                    
                    # Check if resulted chunk is still too big (huge words)
                    if len(chunk) > MAX_CHARS:
                         # Sub-split this chunk by chars
                         chunks.extend([chunk[k:k+MAX_CHARS] for k in range(0, len(chunk), MAX_CHARS)])
                    else:
                         if chunk.strip():
                            chunks.append(chunk)
                return chunks
            
            # Build chunks from sentences
            chunks = []
            current_chunk = []
            current_word_count = 0
            current_char_count = 0
            
            for sentence in sentence_list:
                sentence_words = sentence.split()
                sentence_word_count = len(sentence_words)
                sentence_char_count = len(sentence)
                
                # Check limits (both word and char)
                word_limit_exceeded = (current_word_count + sentence_word_count > max_words)
                char_limit_exceeded = (current_char_count + sentence_char_count > MAX_CHARS)
                
                if (word_limit_exceeded or char_limit_exceeded) and current_chunk:
                    chunk_text = "".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    
                    # Manage Overlap logic
                    # For simplicity in this robust version, we just reset or take last sentence
                    # (Implementing complex word-overlap with Sentence lists is error prone)
                    overlap_text = current_chunk[-1] if current_chunk else ""
                    current_chunk = [overlap_text] if overlap_text else []
                    current_word_count = len(overlap_text.split())
                    current_char_count = len(overlap_text)
                
                if len(sentence) > MAX_CHARS:
                    # Single sentence is massive; force character split for it
                    sub_chunks = [sentence[k:k+MAX_CHARS] for k in range(0, len(sentence), MAX_CHARS)]
                    if current_chunk: # Flush current
                        chunks.append("".join(current_chunk).strip())
                        current_chunk = []
                        current_word_count = 0
                        current_char_count = 0
                    chunks.extend(sub_chunks)
                else: 
                    current_chunk.append(sentence)
                    current_word_count += sentence_word_count
                    current_char_count += sentence_char_count
            
            if current_chunk:
                chunk_text = "".join(current_chunk).strip()
                if chunk_text:
                    chunks.append(chunk_text)
            
            return chunks if chunks else [text]
        
        # Track which original texts were split (for metadata handling by caller)
        text_split_map = {}  # Maps original index -> list of split indices
        
        for i, text in enumerate(texts):
            if isinstance(text, str) and text.strip():
                # Clean invalid tokens before length check
                clean_text = text.replace('\x00', '')
                
                words = clean_text.split()
                word_count = len(words)
                char_count = len(clean_text)
                
                # Split if word count high OR char count high (dense text)
                if word_count > MAX_WORDS or char_count > MAX_CHARS:
                    logger.warning(f"⚠️ Text {i+1} huge (words={word_count}, chars={char_count}), splitting...")
                    split_chunks = split_text_by_sentences(clean_text, MAX_WORDS, overlap_words=settings.CHAPTER_CHUNK_OVERLAP_WORDS)
                    logger.info(f"   ✅ Split into {len(split_chunks)} chunks")
                    # Store split info for caller
                    start_idx = len(cleaned_texts)
                    cleaned_texts.extend([chunk.strip() for chunk in split_chunks if chunk.strip()])
                    end_idx = len(cleaned_texts)
                    text_split_map[i] = list(range(start_idx, end_idx))
                else:
                    cleaned_texts.append(clean_text.strip())
            elif text:  # Non-empty but not string - convert to string
                text_str = str(text).strip()
                words = text_str.split()
                word_count = len(words)
                if word_count > MAX_WORDS:
                    logger.warning(f"⚠️ Text {i+1} too long ({word_count} words), splitting into smaller chunks...")
                    split_chunks = split_text_by_sentences(text_str, MAX_WORDS, overlap_words=settings.CHAPTER_CHUNK_OVERLAP_WORDS)
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
        """Generate embeddings using Sentence Transformers (lazy-loaded)"""
        try:
            # Lazy-load model only when this method is called
            sbert_model = self._get_sbert_model()
            embeddings = sbert_model.encode(texts)
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