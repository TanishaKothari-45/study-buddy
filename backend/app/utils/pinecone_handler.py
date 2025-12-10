"""
Pinecone vector store handler with LangChain integration
"""
import logging
import os
from typing import List, Dict, Any, Optional, ClassVar
from fastapi import HTTPException

# Try to import Pydantic ConfigDict for v2 compatibility
try:
    from pydantic import ConfigDict
    PYDANTIC_V2_AVAILABLE = True
except ImportError:
    PYDANTIC_V2_AVAILABLE = False
    ConfigDict = None

# Initialize logger early so it's available for use in try blocks
logger = logging.getLogger(__name__)

# LangChain imports
try:
    from langchain_pinecone import PineconeVectorStore
    import langchain_pinecone.vectorstores as lc_pinecone
    from langchain_core.embeddings import Embeddings
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    try:
        from langchain.chains import RetrievalQA
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        RETRIEVALQA_AVAILABLE = True
    except ImportError:
        RETRIEVALQA_AVAILABLE = False
        RetrievalQA = None
        ChatOpenAI = None
        OpenAIEmbeddings = None
    LANGCHAIN_AVAILABLE = True
    
    # Note: No patching needed anymore - metadata now has 'text' field at source
    # All vectors have been updated via pinecone_metadata_safe_update.py
        
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    RETRIEVALQA_AVAILABLE = False
    # Create dummy classes if import fails (to prevent NameError)
    class Embeddings:
        pass
    class PineconeVectorStore:
        pass
    class Document:
        pass
    class BaseRetriever:
        pass
    RetrievalQA = None
    ChatOpenAI = None
    OpenAIEmbeddings = None
    lc_pinecone = None

try:
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

from ..core.config import settings
from .embedder import Embedder

# Log availability
if not LANGCHAIN_AVAILABLE:
    logger.warning("LangChain not available - some features will not work")
if not PINECONE_AVAILABLE:
    logger.warning("Pinecone not available - please install pinecone-client")


class PineconeEmbeddings(Embeddings):
    """Wrapper to make our embedder compatible with LangChain"""
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        # Determine dimensionality by actually generating a test embedding
        try:
            test_embedding = embedder.get_embeddings(["test"])[0]
            self.dimensionality = len(test_embedding)
            logger.debug(f"✅ Detected embedding dimensionality: {self.dimensionality}")
        except Exception as dim_error:
            logger.warning(f"⚠️ Could not detect dimensionality from test embedding: {dim_error}")
            if embedder.openai_client:
                self.dimensionality = 1536  # OpenAI text-embedding-3-small
            else:
                self.dimensionality = 384  # Sentence Transformers default
            logger.debug(f"   Using fallback dimensionality: {self.dimensionality}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents"""
        return self.embedder.get_embeddings(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query"""
        return self.embedder.get_embeddings([text])[0]


# Note: We no longer need PatchedPineconeVectorStore class because we're using
# global monkey-patch of langchain_pinecone._results_to_docs instead.
# This ensures ALL PineconeVectorStore instances use the patched logic.


class ContentStoreRetriever(BaseRetriever):
    """
    Custom retriever wrapper that enriches documents with full content from SQLite content store.
    
    Flow:
    1. Base retriever gets documents from Pinecone (with content_preview)
    2. Extract chunk_id and filename from metadata
    3. Lookup full content from SQLite content store
    4. Replace page_content with full content
    5. Return enriched documents
    """
    # Declare fields properly for Pydantic
    base_retriever: BaseRetriever
    use_content_store: bool = True
    content_store: Optional[Any] = None
    
    class Config:
        arbitrary_types_allowed = True  # Works for both Pydantic v1/v2
    
    def __init__(
        self,
        base_retriever: BaseRetriever,
        use_content_store: bool = True,
        **kwargs
    ):
        # Validate base_retriever before proceeding
        if base_retriever is None:
            raise ValueError("base_retriever cannot be None")
        
        if not isinstance(base_retriever, BaseRetriever):
            raise TypeError(f"base_retriever must be an instance of BaseRetriever, got {type(base_retriever)}")
        
        # ✅ Important: Initialize BaseRetriever (Pydantic) with required fields
        data = {
            "base_retriever": base_retriever,
            "use_content_store": use_content_store,
            "content_store": None
        }
        super().__init__(**data, **kwargs)
        
        # Lazy import for circular dependency safety
        if self.use_content_store:
            try:
                from .content_store import ContentStore
                self.content_store = ContentStore()
                logger.info("✅ Content store initialized for retriever enrichment")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize content store: {e}")
                self.use_content_store = False
                self.content_store = None
    
    def _get_relevant_documents(self, query: str) -> List[Document]:
        """
        Retrieve relevant docs from Pinecone and hydrate from local store.
        
        Flow:
        1. Get documents from base retriever (Pinecone) - these may have content_preview
        2. Fill page_content from content_preview if missing (safety fallback)
        3. Lookup full content from SQLite using chunk_id
        4. Replace preview with full text if available
        5. Return enriched documents
        
        Args:
            query: Query text
            
        Returns:
            List of Document objects with full content from content store
        """
        logger.info(f"🔍 [ContentStoreRetriever] Starting retrieval for query: '{query[:100]}...'")
        
        if not self.base_retriever:
            logger.error("❌ [ContentStoreRetriever] base_retriever missing")
            return []
        
        # STEP 1: Get documents from base retriever (Pinecone vector search)
        logger.info(f"📊 [ContentStoreRetriever] Step 1: Querying Pinecone vector store...")
        try:
            # Try using invoke() (LangChain 0.1.46+)
            if hasattr(self.base_retriever, 'invoke'):
                docs = self.base_retriever.invoke(query)
                logger.info(f"✅ [ContentStoreRetriever] Pinecone returned {len(docs)} documents via invoke()")
            else:
                # Fallback to deprecated method for older versions
                docs = self.base_retriever.get_relevant_documents(query)
                logger.info(f"✅ [ContentStoreRetriever] Pinecone returned {len(docs)} documents via get_relevant_documents()")
        except Exception as e:
            # If invoke fails, try deprecated method
            logger.warning(f"⚠️ [ContentStoreRetriever] invoke() failed, trying get_relevant_documents(): {e}")
            docs = self.base_retriever.get_relevant_documents(query)
            logger.info(f"✅ [ContentStoreRetriever] Pinecone returned {len(docs)} documents (fallback method)")
        
        if not docs:
            logger.warning("⚠️ [ContentStoreRetriever] No documents retrieved from Pinecone")
            return []
        
        # Log Pinecone results details
        logger.info(f"📋 [ContentStoreRetriever] Pinecone results summary:")
        for i, doc in enumerate(docs[:3], 1):  # Log first 3 docs
            meta = doc.metadata
            chunk_id = meta.get("chunk_id", "N/A")
            filename = meta.get("filename", "N/A")
            preview_len = len(doc.page_content) if doc.page_content else 0
            logger.info(f"   Doc {i}: chunk_id={chunk_id}, filename={filename}, preview_len={preview_len} chars")
        
        # Step 2: Fill page_content from preview if missing (safety fallback)
        # This ensures we never have empty documents even if patching failed
        filled_count = 0
        for doc in docs:
            if not getattr(doc, "page_content", None) or not doc.page_content.strip():
                content_preview = doc.metadata.get("content_preview", "")
                if content_preview:
                    doc.page_content = content_preview
                    filled_count += 1
                    logger.debug(f"✅ [ContentStoreRetriever] Filled empty page_content from content_preview ({len(content_preview)} chars)")
        
        if filled_count > 0:
            logger.info(f"📝 [ContentStoreRetriever] Filled {filled_count} empty page_content fields from preview")
        
        # If content store is not enabled, return docs with preview content
        if not self.use_content_store or not self.content_store:
            logger.warning("⚠️ [ContentStoreRetriever] Content store disabled - returning Pinecone preview content only")
            return docs
        
        # STEP 3: Enrich documents with full content from SQLite (PARALLEL for k=20 support)
        logger.info(f"💾 [ContentStoreRetriever] Step 2: Enriching {len(docs)} docs from SQLite (parallel reads)...")
        
        # Import concurrent.futures and time for parallel execution and metrics
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        # Start timing SQLite enrichment
        sqlite_start = time.perf_counter()
        
        # Helper function to fetch single chunk from SQLite
        def fetch_single_chunk(doc):
            """Fetch full content for a single document (runs in thread pool)"""
            chunk_start = time.perf_counter()
            meta = doc.metadata
            chunk_id = meta.get("chunk_id")
            filename = meta.get("filename")
            chapter = meta.get("chapter")
            
            full_content = None
            if chunk_id and filename:
                try:
                    # Try exact chunk_id first
                    full_content = self.content_store.get_chunk(
                        chunk_id=chunk_id, filename=filename, chapter=chapter
                    )
                    
                    # If not found and chunk_id has split suffix, try base chunk_id
                    if not full_content and '_split' in chunk_id:
                        base_chunk_id = chunk_id.rsplit('_split', 1)[0]
                        full_content = self.content_store.get_chunk(
                            chunk_id=base_chunk_id, filename=filename, chapter=chapter
                        )
                except Exception as e:
                    logger.warning(f"SQLite lookup failed for {chunk_id}: {e}")
            
            chunk_time = (time.perf_counter() - chunk_start) * 1000  # Convert to ms
            return full_content, chunk_time
        
        # Fetch all chunks in parallel using thread pool
        # WAL mode supports unlimited concurrent readers - no need to batch
        # For k=20: Sequential would be 20×20ms=400ms, Parallel is max(20ms)=20ms
        with ThreadPoolExecutor() as executor:
            # Submit all fetch tasks
            future_to_doc = {executor.submit(fetch_single_chunk, doc): doc for doc in docs}
            
            # Collect results in original order
            results = []
            for doc in docs:
                for future, future_doc in future_to_doc.items():
                    if future_doc is doc:
                        results.append(future.result())
                        break
        
        # Unpack results and timing
        full_contents = [content for content, _ in results]
        chunk_times = [chunk_time for _, chunk_time in results]
        
        # Calculate timing metrics
        sqlite_total_time = (time.perf_counter() - sqlite_start) * 1000  # ms
        avg_chunk_time = sum(chunk_times) / len(chunk_times) if chunk_times else 0
        max_chunk_time = max(chunk_times) if chunk_times else 0
        min_chunk_time = min(chunk_times) if chunk_times else 0
        
        # Sequential time would be sum of all chunk times
        sequential_time_estimate = sum(chunk_times)
        time_saved = sequential_time_estimate - sqlite_total_time
        
        # Now enrich documents with fetched content
        enriched_docs = []
        sqlite_success = 0
        sqlite_failed = 0
        preview_used = 0
        
        for i, (doc, full_content) in enumerate(zip(docs, full_contents), 1):
            meta = doc.metadata
            
            # Replace preview with full text if available
            preview_length = len(doc.page_content.strip()) if doc.page_content else 0
            if full_content and len(full_content.strip()) > preview_length:
                # Full content is longer than preview, replace it
                doc.page_content = full_content
                # Ensure document has text property for LangChain compatibility
                object.__setattr__(doc, 'text', full_content)
                meta["_content_source"] = "content_store"
                sqlite_success += 1
                logger.debug(f"[{i}/{len(docs)}] ✅ Enriched: {preview_length} → {len(full_content)} chars")
            else:
                # Use preview content (either no full content found, or preview is same/longer)
                meta["_content_source"] = "content_preview"
                preview_used += 1
                if full_content:
                    logger.debug(f"[{i}/{len(docs)}] ⚠️ Keeping preview (full {len(full_content)} <= preview {preview_length})")
                else:
                    logger.debug(f"[{i}/{len(docs)}] ⚠️ Using preview (not in SQLite)")
                    sqlite_failed += 1
            
            enriched_docs.append(doc)
        
        logger.info(f"✅ [ContentStoreRetriever] Enrichment complete:")
        logger.info(f"   • Total docs: {len(enriched_docs)}")
        logger.info(f"   • Enriched from SQLite: {sqlite_success}")
        logger.info(f"   • Using Pinecone preview: {preview_used}")
        logger.info(f"   • SQLite lookup failed: {sqlite_failed}")
        logger.info(f"⏱️  [PERFORMANCE METRICS - SQLite Reads]:")
        logger.info(f"   • Total time (parallel): {sqlite_total_time:.1f}ms")
        logger.info(f"   • Per-chunk time: avg={avg_chunk_time:.1f}ms, min={min_chunk_time:.1f}ms, max={max_chunk_time:.1f}ms")
        logger.info(f"   • Sequential would take: {sequential_time_estimate:.1f}ms")
        logger.info(f"   • ⚡ TIME SAVED: {time_saved:.1f}ms ({(time_saved/sequential_time_estimate*100) if sequential_time_estimate > 0 else 0:.0f}% faster)")
        
        return enriched_docs
    
    def get_relevant_documents(self, query: str, *, run_manager: Optional[Any] = None) -> List[Document]:
        """
        LangChain BaseRetriever method - retrieve relevant documents.
        This is the standard method that LangChain expects.
        
        Args:
            query: Query string
            run_manager: Optional callback manager
            
        Returns:
            List of Document objects with full content from content store
        """
        return self._get_relevant_documents(query)
    
    def invoke(self, input: str, config: Optional[Any] = None, **kwargs) -> List[Document]:
        """
        Modern LangChain API - use invoke() instead of get_relevant_documents().
        
        Args:
            input: Query string
            config: Optional runtime configuration
            **kwargs: Additional arguments
            
        Returns:
            List of Document objects with full content from content store
        """
        return self._get_relevant_documents(input)
    
    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        """Async version - delegates to sync version"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_relevant_documents, query
        )


class PineconeHandler:
    def __init__(self, index_name: str = None):
        """
        Initialize Pinecone client and vector store
        
        Args:
            index_name: Name of Pinecone index (default: from settings)
        """
        if not PINECONE_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="Pinecone is not available. Please install pinecone-client."
            )
        
        # Get Pinecone API key
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise HTTPException(
                status_code=500,
                detail="PINECONE_API_KEY not found in environment variables. Please set it in your .env file."
            )
        
        # Initialize Pinecone client
        self.pc = Pinecone(api_key=pinecone_api_key)
        
        # Initialize embedder
        self.embedder = Embedder()
        
        # Set index name
        self.index_name = index_name or settings.PINECONE_INDEX_NAME
        
        # Initialize LangChain embeddings wrapper
        self.langchain_embeddings = PineconeEmbeddings(self.embedder)
        
        # Initialize vector store (will be created on first use)
        self.vectorstore = None
        
        logger.info(f"✅ Initialized PineconeHandler with index: {self.index_name}")
        logger.info(f"   • Embedding dimension: {self.langchain_embeddings.dimensionality}")
    
    def _get_vectorstore(self) -> PineconeVectorStore:
        """Get or create PineconeVectorStore instance"""
        if self.vectorstore is None:
            if not LANGCHAIN_AVAILABLE:
                raise HTTPException(
                    status_code=500,
                    detail="LangChain is not available. Please install langchain-pinecone."
                )
            
            try:
                # Use standard PineconeVectorStore - the global monkey-patch ensures
                # all instances use content_preview → text mapping automatically
                self.vectorstore = PineconeVectorStore(
                    index_name=self.index_name,
                    embedding=self.langchain_embeddings,
                    pinecone_api_key=os.getenv("PINECONE_API_KEY")
                )
                logger.debug(f"✅ Created PineconeVectorStore for index: {self.index_name}")
            except Exception as e:
                logger.error(f"❌ Failed to create PineconeVectorStore: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to initialize Pinecone vector store: {str(e)}"
                )
        
        return self.vectorstore
    
    def add_documents(self, chunks_with_metadata: List[Dict[str, Any]], batch_size: int = 100) -> None:
        """
        Embed and store document chunks in Pinecone using direct API (not LangChain wrapper).
        
        Flow: Extract texts → Embedder.get_openai_embeddings() → Pinecone upsert
        
        Args:
            chunks_with_metadata: List of dicts with 'content' and 'metadata' keys
            batch_size: Number of chunks to process per batch (default: 100)
        """
        if not chunks_with_metadata:
            logger.warning("⚠️ No chunks to add")
            return
        
        try:
            from tqdm import tqdm
        except ImportError:
            # Fallback if tqdm not available
            def tqdm(iterable, **kwargs):
                return iterable
        
        # Extract text + metadata
        documents = [item["content"] for item in chunks_with_metadata]
        metadatas = [item["metadata"] for item in chunks_with_metadata]
        
        # Final cleanup function to remove null bytes and control characters
        def final_cleanup(text: str) -> str:
            """Final aggressive cleanup before storing"""
            if not isinstance(text, str):
                return str(text) if text else ""
            import re
            from ..utils.pdf_precleaner import garbage_patterns
            
            # Remove ALL null bytes (multiple passes)
            while '\x00' in text:
                text = text.replace('\x00', '')
            while '\u0000' in text:
                text = text.replace('\u0000', '')
            # Remove control characters
            text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
            # Fix thorn character
            text = text.replace('þ', 'th').replace('Þ', 'Th')
            
            # Apply garbage patterns one more time (final pass)
            for p in garbage_patterns:
                text = re.sub(p, "", text, flags=re.I)
            
            # Remove lines with garbage keywords
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                line_lower = line.lower()
                if any(garbage in line_lower for garbage in ['t.me', 'telegram', 'website', 'nttp', 'vs://', 'ÿth', 'upscpdf', 'ilttp']):
                    continue
                cleaned_lines.append(line)
            text = '\n'.join(cleaned_lines)
            
            return text.strip()
        
        # Helper function to split long chunks by sentences
        def split_long_chunk_by_sentences(text: str, max_words: int = 1500, overlap_words: int = 100) -> List[str]:
            """
            Split long text into smaller chunks by sentences.
            Preserves sentence boundaries and adds overlap.
            """
            import re
            
            words = text.split()
            word_count = len(words)
            
            if word_count <= max_words:
                return [text]
            
            # Split by sentences (simple regex-based approach)
            # Match sentence endings: . ! ? followed by space or newline
            sentences = re.split(r'([.!?]+\s+)', text)
            # Recombine sentences with their punctuation
            sentence_list = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    sentence_list.append(sentences[i] + sentences[i + 1])
                else:
                    sentence_list.append(sentences[i])
            
            # If no sentence boundaries found, fall back to word-based splitting
            if len(sentence_list) <= 1:
                logger.warning(f"⚠️ No sentence boundaries found, using word-based split")
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
                
                # If adding this sentence would exceed limit, save current chunk
                if current_word_count + sentence_word_count > max_words and current_chunk:
                    chunk_text = "".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    
                    # Start new chunk with overlap (last N words from previous chunk)
                    overlap_text = " ".join(words[max(0, current_word_count - overlap_words):current_word_count])
                    if overlap_text:
                        current_chunk = [overlap_text + " "]
                        current_word_count = len(overlap_text.split())
                    else:
                        current_chunk = []
                        current_word_count = 0
                
                current_chunk.append(sentence)
                current_word_count += sentence_word_count
            
            # Add final chunk
            if current_chunk:
                chunk_text = "".join(current_chunk).strip()
                if chunk_text:
                    chunks.append(chunk_text)
            
            return chunks if chunks else [text]
        
        # Filter out empty or invalid documents, apply final cleanup, and split long chunks
        valid_indices = []
        filtered_documents = []
        filtered_metadatas = []
        MAX_WORDS_PER_CHUNK = 1500  # Match embedder limit
        
        for i, doc in enumerate(documents):
            if isinstance(doc, str) and doc.strip() and len(doc.strip()) > 10:
                # Apply final cleanup before storing
                cleaned_doc = final_cleanup(doc)
                if not cleaned_doc or len(cleaned_doc.strip()) <= 10:
                    continue
                
                # Check if chunk is too long and split if needed
                word_count = len(cleaned_doc.split())
                if word_count > MAX_WORDS_PER_CHUNK:
                    logger.warning(f"⚠️ Chunk {i+1} is too long ({word_count} words), splitting into smaller chunks...")
                    split_chunks = split_long_chunk_by_sentences(cleaned_doc, MAX_WORDS_PER_CHUNK, overlap_words=100)
                    logger.info(f"   ✅ Split into {len(split_chunks)} chunks")
                    
                    # Add each split chunk with its metadata
                    for split_idx, split_chunk in enumerate(split_chunks):
                        if split_chunk.strip() and len(split_chunk.strip()) > 10:
                            # Create metadata copy for split chunk
                            split_meta = metadatas[i].copy()
                            # Add split indicator to chunk_id if it exists
                            if 'chunk_id' in split_meta:
                                split_meta['chunk_id'] = f"{split_meta['chunk_id']}_split{split_idx + 1}"
                            valid_indices.append(i)  # Keep original index for tracking
                            filtered_documents.append(split_chunk.strip())
                            filtered_metadatas.append(split_meta)
                else:
                    # Chunk is fine, add as-is
                    valid_indices.append(i)
                    filtered_documents.append(cleaned_doc.strip())
                    filtered_metadatas.append(metadatas[i])
        
        if not filtered_documents:
            logger.warning("⚠️ No valid documents to embed after filtering")
            return
        
        # ------------------------------------------------------------------
        # NEW: Store full content in local SQLite content store
        # This ensures we have the content even if Pinecone only creates vectors
        # ------------------------------------------------------------------
        try:
            from .content_store import ContentStore
            content_store = ContentStore()
            
            # Prepare chunks for content store (need to flatten structure)
            content_chunks_for_sqlite = []
            for i, (doc, meta) in enumerate(zip(filtered_documents, filtered_metadatas)):
                # Create a clean copy for SQLite
                chunk_data = meta.copy()
                chunk_data['content'] = doc
                # Ensure chunk_id exists
                if 'chunk_id' not in chunk_data:
                    chunk_data['chunk_id'] = f"doc_{i}"
                
                content_chunks_for_sqlite.append(chunk_data)
            
            # Batch store to SQLite
            logger.info(f"💾 Storing {len(content_chunks_for_sqlite)} chunks in local SQLite content store...")
            store_result = content_store.batch_store(content_chunks_for_sqlite)
            logger.info(f"   ✅ SQLite Storage: {store_result.get('success', 0)} success, {store_result.get('failed', 0)} failed")
            
        except Exception as e:
            logger.error(f"❌ Failed to store chunks in SQLite: {e}")
            # Don't fail the whole process, continue to Pinecone upload
            
        logger.info(f"💾 Preparing to store {len(filtered_documents)} chunks in Pinecone (batched)")
        logger.info(f"   • Batch size: {batch_size}")
        logger.info(f"   • Total batches: {(len(filtered_documents) + batch_size - 1) // batch_size}")
        
        # Get Pinecone index directly (not through LangChain)
        index = self.pc.Index(self.index_name)
        
        # Process in batches
        total_batches = (len(filtered_documents) + batch_size - 1) // batch_size
        for i in tqdm(range(0, len(filtered_documents), batch_size), desc="Uploading chunks"):
            batch_docs = filtered_documents[i:i + batch_size]
            batch_meta = filtered_metadatas[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            try:
                # Step 1: Generate embeddings using Embedder
                logger.debug(f"   📊 Batch {batch_num}/{total_batches}: Generating embeddings for {len(batch_docs)} chunks...")
                embeddings = self.embedder.get_openai_embeddings(batch_docs)
                
                # Handle case where embedder split some texts (shouldn't happen since we split in handler)
                # If embedder split, we'll have more embeddings than docs - need to duplicate metadata
                if len(embeddings) > len(batch_docs):
                    logger.warning(f"⚠️ Embedder split some texts: {len(embeddings)} embeddings for {len(batch_docs)} documents")
                    logger.warning(f"   This shouldn't happen (handler should split first). Handling mismatch...")
                    # This is a safety net - ideally shouldn't happen
                    # For now, use first N embeddings (better than crashing)
                    embeddings = embeddings[:len(batch_docs)]
                elif len(embeddings) < len(batch_docs):
                    logger.error(f"❌ Fewer embeddings than documents: {len(embeddings)} < {len(batch_docs)}")
                    # Skip this batch
                    continue
                
            except Exception as e:
                logger.error(f"❌ Embedding batch {batch_num} failed: {e}")
                import time
                time.sleep(5)
                continue
            
            # Step 2: Prepare vectors for Pinecone upsert
            # Pinecone expects: (id, vector, metadata) tuples
            vectors = []
            for idx, emb in enumerate(embeddings):
                doc_meta = batch_meta[idx].copy()
                doc_content = batch_docs[idx]  # Get the original content for preview (already cleaned)
                
                # Generate unique ID
                doc_id = doc_meta.get("chunk_id") or f"doc_{i + idx}"
                # Ensure ID is string and doesn't contain special chars
                doc_id = str(doc_id).replace(" ", "_").replace("/", "_")
                
                # Flatten metadata for Pinecone (no nested dicts, only primitives)
                flat_metadata = {}
                for key, value in doc_meta.items():
                    # Skip storing full content - we'll add a preview instead
                    if key == "content":
                        continue
                    if isinstance(value, (str, int, float, bool)):
                        flat_metadata[key] = value
                    elif value is None:
                        continue
                    else:
                        flat_metadata[key] = str(value)
                
                # Add content preview (first 400 characters) instead of full text
                # This saves space while still providing context in metadata
                content_preview = doc_content[:400] if doc_content else ""
                # Clean the preview as well (remove null bytes, control chars, thorn)
                content_preview = final_cleanup(content_preview)
                flat_metadata["content_preview"] = content_preview
                
                # CRITICAL: Add 'text' field to metadata for langchain_pinecone compatibility
                # langchain_pinecone checks for 'text' key and skips documents without it
                # We use content_preview as the text field to prevent skipping
                flat_metadata["text"] = content_preview
                
                vectors.append((doc_id, emb, flat_metadata))
            
            # Step 3: Upsert to Pinecone
            try:
                index.upsert(vectors=vectors)
                logger.info(f"   ✅ Batch {batch_num}/{total_batches}: Uploaded {len(vectors)} chunks")
            except Exception as e:
                logger.error(f"⚠️ Pinecone upsert failed on batch {batch_num}: {e}")
                import time
                time.sleep(5)
                # Retry once
                try:
                    index.upsert(vectors=vectors)
                    logger.info(f"   ✅ Batch {batch_num}/{total_batches}: Retry successful - uploaded {len(vectors)} chunks")
                except Exception as retry_error:
                    logger.error(f"❌ Retry also failed for batch {batch_num}: {retry_error}")
                    raise
        
        logger.info(f"✅ Finished uploading {len(filtered_documents)} chunks to Pinecone")
    
    def verify_upload(self, sample_query: str, top_k: int = 3) -> None:
        """
        Quick test query to verify upload worked correctly.
        
        Args:
            sample_query: Test query string
            top_k: Number of results to return
        """
        try:
            logger.info(f"\n🔍 Verifying upload with query: '{sample_query}'")
            
            # Generate embedding for query
            query_embedding = self.embedder.get_openai_embeddings([sample_query])[0]
            
            # Query Pinecone directly
            index = self.pc.Index(self.index_name)
            res = index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True
            )
            
            if not res.get("matches"):
                logger.warning("⚠️ No results found - upload may have failed")
                return
            
            logger.info(f"✅ Found {len(res['matches'])} results:")
            for i, match in enumerate(res["matches"], 1):
                meta = match.get("metadata", {})
                score = match.get("score", 0.0)
                logger.info(f"\n   Result {i}:")
                logger.info(f"      • Score: {score:.3f}")
                logger.info(f"      • Chapter: {meta.get('chapter', 'N/A')}")
                logger.info(f"      • Section: {meta.get('section', 'N/A')}")
                logger.info(f"      • Page: {meta.get('page_start', 'N/A')}–{meta.get('page_end', 'N/A')}")
                logger.info(f"      • Filename: {meta.get('filename', 'N/A')}")
                if meta.get('chunk_id'):
                    logger.info(f"      • Chunk ID: {meta.get('chunk_id')}")
                
        except Exception as e:
            logger.error(f"❌ Verification query failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def query_documents(self, query_text: str, k: int = 5, 
                       filter_metadata: Optional[Dict[str, Any]] = None,
                       use_content_store: bool = True) -> List[Dict[str, Any]]:
        """
        Query for most relevant documents
        
        Args:
            query_text: Text to search for
            k: Number of results to return
            filter_metadata: Optional dict to filter by metadata fields
            use_content_store: If True, enrich with full content from content store
        """
        try:
            vectorstore = self._get_vectorstore()
            
            # Build filter if provided
            pinecone_filter = None
            if filter_metadata:
                # Convert filter to Pinecone filter format
                pinecone_filter = {}
                for key, value in filter_metadata.items():
                    if isinstance(value, str):
                        # Pinecone supports substring matching with $regex
                        # For simple substring matching, we'll use $in with a list
                        # But for now, use exact match
                        pinecone_filter[key] = {"$eq": value}
                    else:
                        pinecone_filter[key] = {"$eq": value}
            
            # Query with similarity search
            if pinecone_filter:
                docs = vectorstore.similarity_search(
                    query_text,
                    k=k * 3,  # Fetch more to filter
                    filter=pinecone_filter
                )
            else:
                docs = vectorstore.similarity_search(query_text, k=k)
            
            # Format results
            formatted_results = []
            for doc in docs:
                chunk = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "distance": 0.0  # Pinecone doesn't return distances in similarity_search
                }
                
                # Enrich with full content from content store if available
                if use_content_store:
                    try:
                        from .content_store import ContentStore
                        content_store = ContentStore()
                        
                        chunk_id = doc.metadata.get("chunk_id")
                        filename = doc.metadata.get("filename")
                        chapter = doc.metadata.get("chapter")
                        
                        if chunk_id and filename:
                            full_content = content_store.get_chunk(
                                chunk_id=chunk_id,
                                filename=filename,
                                chapter=chapter
                            )
                            if full_content:
                                chunk["content"] = full_content
                                chunk["metadata"]["_content_source"] = "content_store"
                            else:
                                chunk["metadata"]["_content_source"] = "content_preview"
                    except Exception as e:
                        logger.debug(f"⚠️ Content store lookup failed: {e}, using preview")
                        chunk["metadata"]["_content_source"] = "content_preview"
                
                # Apply additional metadata filtering if needed (for substring matching)
                if filter_metadata:
                    metadata = chunk["metadata"]
                    matches = True
                    for key, value in filter_metadata.items():
                        if key not in metadata:
                            matches = False
                            break
                        # Support substring matching for string fields
                        if isinstance(metadata[key], str) and isinstance(value, str):
                            if value.lower() not in metadata[key].lower():
                                matches = False
                                break
                        elif metadata[key] != value:
                            matches = False
                            break
                    
                    if matches:
                        formatted_results.append(chunk)
                else:
                    formatted_results.append(chunk)
                
                # Stop if we have enough results
                if len(formatted_results) >= k:
                    break
            
            logger.info(f"✅ Found {len(formatted_results)} relevant chunks")
            return formatted_results[:k]
            
        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query Pinecone: {str(e)}"
            )
    
    def query_documents_mmr(self, query_text: str, fetch_k: int = 50, k: int = 10,
                            lambda_mult: float = 0.65,
                            filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query documents using MMR (Maximum Marginal Relevance) retriever.
        
        This uses LangChain's MMR retriever which works seamlessly with Pinecone.
        
        Args:
            query_text: Text to search for
            fetch_k: Number of documents to fetch before applying MMR (default: 50)
            k: Number of documents to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
            filter_metadata: Optional dict to filter by metadata fields
        """
        try:
            if not LANGCHAIN_AVAILABLE:
                logger.warning("⚠️ LangChain not available - falling back to standard query")
                return self.query_documents(query_text, k=k, filter_metadata=filter_metadata)
            
            vectorstore = self._get_vectorstore()
            
            # Build filter if provided
            pinecone_filter = None
            if filter_metadata:
                pinecone_filter = {}
                for key, value in filter_metadata.items():
                    if isinstance(value, str):
                        pinecone_filter[key] = {"$eq": value}
                    else:
                        pinecone_filter[key] = {"$eq": value}
            
            # Create MMR retriever
            retriever = vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "fetch_k": fetch_k,
                    "k": k,
                    "lambda_mult": lambda_mult,
                    "filter": pinecone_filter
                }
            )
            
            # Retrieve diverse chunks (using new LangChain API)
            docs = retriever.invoke(query_text)
            
            # Format results
            formatted_results = []
            for doc in docs:
                chunk = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "distance": 0.0
                }
                
                # Apply additional metadata filtering if needed
                if filter_metadata:
                    metadata = chunk["metadata"]
                    matches = True
                    for key, value in filter_metadata.items():
                        if key not in metadata:
                            matches = False
                            break
                        if isinstance(metadata[key], str) and isinstance(value, str):
                            if value.lower() not in metadata[key].lower():
                                matches = False
                                break
                        elif metadata[key] != value:
                            matches = False
                            break
                    
                    if matches:
                        formatted_results.append(chunk)
                else:
                    formatted_results.append(chunk)
            
            logger.info(f"✅ MMR retrieval found {len(formatted_results)} relevant chunks")
            return formatted_results[:k]
            
        except Exception as e:
            logger.error(f"❌ MMR query failed: {e}")
            logger.warning("⚠️ Falling back to standard similarity search")
            import traceback
            logger.error(traceback.format_exc())
            return self.query_documents(query_text, k=k, filter_metadata=filter_metadata)
    
    def get_mmr_retriever(self, fetch_k: int = 50, k: int = 10, lambda_mult: float = 0.7) -> BaseRetriever:
        """
        Create an MMR (Maximum Marginal Relevance) retriever using LangChain.
        
        This works seamlessly with Pinecone - no compatibility issues!
        
        Args:
            fetch_k: Number of documents to fetch before applying MMR (default: 50)
            k: Number of documents to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
        
        Returns:
            LangChain MMR retriever instance
        """
        if not LANGCHAIN_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="LangChain is not available. Please install langchain-pinecone."
            )
        
        try:
            vectorstore = self._get_vectorstore()
            retriever = vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "fetch_k": fetch_k,
                    "k": k,
                    "lambda_mult": lambda_mult
                }
            )
            logger.info(f"✅ Created MMR retriever: fetch_k={fetch_k}, k={k}, lambda_mult={lambda_mult}")
            return retriever
        except Exception as e:
            logger.error(f"❌ Failed to create MMR retriever: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create MMR retriever: {str(e)}"
            )
    
    def get_retriever(self, search_type: str = "similarity", k: int = 6, 
                     fetch_k: int = 50, lambda_mult: float = 0.65,
                     use_content_store: bool = True) -> BaseRetriever:
        """
        Create a LangChain retriever with configurable search type and content store enrichment.
        
        Args:
            search_type: "similarity" or "mmr" (default: "similarity")
            k: Number of documents to return (default: 6)
            fetch_k: Number of documents to fetch before MMR (only for MMR, default: 50)
            lambda_mult: Diversity parameter for MMR (0.0 = max diversity, 1.0 = max relevance, default: 0.65)
            use_content_store: If True, enrich documents with full content from SQLite (default: True)
        
        Returns:
            LangChain retriever instance (wrapped with ContentStoreRetriever if use_content_store=True)
        """
        logger.info(f"🔧 [PineconeHandler] Creating retriever:")
        logger.info(f"   • search_type: {search_type}")
        logger.info(f"   • k: {k}")
        logger.info(f"   • use_content_store: {use_content_store}")
        if search_type == "mmr":
            logger.info(f"   • fetch_k: {fetch_k}")
            logger.info(f"   • lambda_mult: {lambda_mult}")
        
        if not LANGCHAIN_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="LangChain is not available. Please install langchain-pinecone."
            )
        
        try:
            logger.debug(f"   → Getting vectorstore...")
            vectorstore = self._get_vectorstore()
            logger.debug(f"   → Vectorstore retrieved: {type(vectorstore).__name__}")
            
            # Create base retriever
            logger.info(f"   → Creating base {search_type} retriever from Pinecone vectorstore...")
            if search_type == "mmr":
                base_retriever = vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "fetch_k": fetch_k,
                        "k": k,
                        "lambda_mult": lambda_mult
                    }
                )
                logger.debug(f"   → Base MMR retriever created")
            else:
                base_retriever = vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": k}
                )
                logger.debug(f"   → Base similarity retriever created")
            
            # Wrap with content store enrichment if enabled
            if use_content_store:
                logger.info(f"   → Wrapping with ContentStoreRetriever for SQLite enrichment...")
                retriever = ContentStoreRetriever(base_retriever, use_content_store=True)
                logger.info(f"✅ [PineconeHandler] Created {search_type} retriever with content store enrichment:")
                logger.info(f"   • Flow: Pinecone (vector search) → SQLite (content enrichment)")
                logger.info(f"   • k={k}" + (f", lambda_mult={lambda_mult}" if search_type == "mmr" else ""))
            else:
                retriever = base_retriever
                logger.info(f"✅ [PineconeHandler] Created {search_type} retriever (no content store):")
                logger.info(f"   • Flow: Pinecone (vector search) only")
                logger.info(f"   • k={k}" + (f", lambda_mult={lambda_mult}" if search_type == "mmr" else ""))
            
            return retriever
        except Exception as e:
            logger.error(f"❌ [PineconeHandler] Failed to create retriever: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create retriever: {str(e)}"
            )
    
    def get_retriever_for_mode(self, mode: str, use_content_store: bool = True, k: Optional[int] = None) -> BaseRetriever:
        """
        Get a retriever configured for a specific mode (prelims, mains, topic, or concept).
        
        Args:
            mode: "prelims", "mains", "topic", or "concept" (case-insensitive)
            use_content_store: If True, enrich documents with full content from SQLite (default: True)
            k: Optional override for number of documents to retrieve (if None, uses mode default)
        
        Returns:
            LangChain retriever instance configured for the specified mode
            
        Raises:
            ValueError: If mode is not recognized
        """
        mode_lower = mode.lower()
        
        if mode_lower == "prelims":
            # Prelims: MMR with higher diversity for broader coverage
            retriever_k = k if k is not None else 12
            logger.info(f"🔧 [PineconeHandler] Creating PRELIMS retriever (MMR, fetch_k=50, k={retriever_k}, lambda_mult=0.55)")
            return self.get_retriever(
                search_type="mmr",
                k=retriever_k,
                fetch_k=50,
                lambda_mult=0.55,  # Higher diversity for prelims
                use_content_store=use_content_store
            )
        elif mode_lower == "mains":
            # Mains: Similarity search with fewer, more focused results
            retriever_k = k if k is not None else 8
            logger.info(f"🔧 [PineconeHandler] Creating MAINS retriever (similarity, k={retriever_k})")
            return self.get_retriever(
                search_type="similarity",
                k=retriever_k,
                use_content_store=use_content_store
            )
        elif mode_lower == "topic":
            # Topic: Similarity search for evaluation (moderate k)
            retriever_k = k if k is not None else 5
            logger.info(f"🔧 [PineconeHandler] Creating TOPIC retriever (similarity, k={retriever_k})")
            return self.get_retriever(
                search_type="similarity",
                k=retriever_k,
                use_content_store=use_content_store
            )
        elif mode_lower == "concept":
            # Concept: Similarity search for explaining concepts (query route)
            # Default k=5, but allows override for user customization
            retriever_k = k if k is not None else 5
            logger.info(f"🔧 [PineconeHandler] Creating CONCEPT retriever (similarity, k={retriever_k})")
            return self.get_retriever(
                search_type="similarity",
                k=retriever_k,
                use_content_store=use_content_store
            )
        else:
            raise ValueError(f"Unknown mode: '{mode}'. Choose 'prelims', 'mains', 'topic', or 'concept'")
    
    def get_qa_chain(self, search_type: str = "similarity", k: int = 6,
                    fetch_k: int = 50, lambda_mult: float = 0.65,
                    model: str = "gpt-4o-mini", temperature: float = 0.3) -> Optional[Any]:
        """
        Create a RetrievalQA chain using LangChain.
        
        This is an ENHANCEMENT - use this for better answer generation.
        Existing query_documents() methods remain unchanged.
        
        Args:
            search_type: "similarity" or "mmr" (default: "similarity")
            k: Number of documents to retrieve (default: 6)
            fetch_k: Number of documents to fetch before MMR (only for MMR, default: 50)
            lambda_mult: Diversity parameter for MMR (default: 0.65)
            model: OpenAI model name (default: "gpt-4o-mini")
            temperature: LLM temperature (default: 0.3)
        
        Returns:
            RetrievalQA chain instance, or None if not available
        
        Usage:
            qa_chain = handler.get_qa_chain(search_type="mmr", k=10, lambda_mult=0.6)
            result = qa_chain({"query": "Explain monsoon formation"})
            answer = result["result"]
            sources = result["source_documents"]
        """
        if not RETRIEVALQA_AVAILABLE:
            logger.warning("⚠️ RetrievalQA not available - install langchain and langchain-openai")
            return None
        
        try:
            # Get retriever
            retriever = self.get_retriever(
                search_type=search_type,
                k=k,
                fetch_k=fetch_k,
                lambda_mult=lambda_mult
            )
            
            # Initialize LLM
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("⚠️ OPENAI_API_KEY not found - cannot create QA chain")
                return None
            
            llm = ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
            
            # Create RetrievalQA chain
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm,
                retriever=retriever,
                return_source_documents=True,
                chain_type="stuff"  # "stuff" means concatenate all retrieved docs
            )
            
            logger.info(f"✅ Created RetrievalQA chain: {search_type}, k={k}, model={model}")
            return qa_chain
        except Exception as e:
            logger.error(f"❌ Failed to create QA chain: {e}")
            return None
    
    def query_with_qa_chain(self, query: str, search_type: str = "similarity", 
                           k: int = 6, fetch_k: int = 50, lambda_mult: float = 0.65,
                           model: str = "gpt-4o-mini", temperature: float = 0.3) -> Dict[str, Any]:
        """
        Query using RetrievalQA chain (ENHANCED method).
        
        This uses LangChain's RetrievalQA for better answer generation.
        Falls back to standard query_documents() if QA chain is not available.
        
        Args:
            query: Question to ask
            search_type: "similarity" or "mmr" (default: "similarity")
            k: Number of documents to retrieve
            fetch_k: For MMR - documents to fetch before selection
            lambda_mult: For MMR - diversity parameter
            model: OpenAI model name
            temperature: LLM temperature
        
        Returns:
            Dict with "answer" and "sources" keys
        """
        qa_chain = self.get_qa_chain(
            search_type=search_type,
            k=k,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            model=model,
            temperature=temperature
        )
        
        if not qa_chain:
            logger.warning("⚠️ QA chain not available, falling back to standard query")
            chunks = self.query_documents(query, k=k)
            return {
                "answer": "\n\n".join(chunk["content"] for chunk in chunks),
                "sources": [chunk["metadata"] for chunk in chunks]
            }
        
        try:
            result = qa_chain({"query": query})
            sources = []
            seen = set()
            for doc in result.get("source_documents", []):
                meta = doc.metadata
                filename = meta.get("filename", "Unknown")
                chapter = meta.get("chapter", "Unknown")
                section = meta.get("section", "Unknown")
                key = (filename, chapter, section)
                if key not in seen:
                    sources.append({
                        "filename": filename,
                        "chapter": chapter,
                        "section": section
                    })
                    seen.add(key)
            
            return {
                "answer": result.get("result", ""),
                "sources": sources
            }
        except Exception as e:
            logger.error(f"❌ QA chain query failed: {e}")
            # Fallback to standard query
            chunks = self.query_documents(query, k=k)
            return {
                "answer": "\n\n".join(chunk["content"] for chunk in chunks),
                "sources": [chunk["metadata"] for chunk in chunks]
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        try:
            index = self.pc.Index(self.index_name)
            stats = index.describe_index_stats()
            return {
                "total_chunks": stats.get("total_vector_count", 0),
                "index_name": self.index_name,
                "dimension": stats.get("dimension", self.langchain_embeddings.dimensionality),
                "metric": stats.get("metric", "cosine")
            }
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {"error": str(e)}
    
    def delete_documents_by_filename(self, filename: str) -> int:
        """
        Delete all documents/chunks that match a specific filename.
        
        Args:
            filename: The filename to match (supports substring matching)
        
        Returns:
            Number of documents deleted
        """
        try:
            # Query for documents with matching filename
            # Note: Pinecone doesn't have a direct query-by-metadata, so we need to use delete with filter
            index = self.pc.Index(self.index_name)
            
            # Use delete with filter (Pinecone supports metadata filtering in delete)
            # Note: This requires Pinecone serverless or pod-based index
            try:
                # Try to delete with filter
                index.delete(filter={"filename": {"$regex": filename}})
                logger.info(f"✅ Deleted documents matching filename '{filename}'")
                # Note: Pinecone doesn't return count, so we can't know exact number
                return 1  # Indicate success
            except Exception as filter_error:
                logger.warning(f"⚠️ Filter-based delete not supported: {filter_error}")
                logger.warning("   Pinecone delete with filter may not be available in your plan")
                return 0
                
        except Exception as e:
            logger.error(f"❌ Failed to delete documents by filename: {e}")
            raise
    
    def switch_to_collection(self, collection_name: str) -> None:
        """
        Switch active index to the specified index name.
        
        Note: In Pinecone, index names must be lowercase with hyphens (not underscores).
        This method automatically converts collection names to Pinecone-compatible format.
        Creates the index if it doesn't exist.
        """
        try:
            # Convert collection name to Pinecone index name format
            # Replace underscores with hyphens and ensure lowercase
            pinecone_index_name = collection_name.replace("_", "-").lower()
            
            # Check if index exists, create if not
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]
            if pinecone_index_name not in existing_indexes:
                logger.info(f"📝 Creating new Pinecone index: {pinecone_index_name}")
                dimension = self.langchain_embeddings.dimensionality
                from pinecone import ServerlessSpec
                self.pc.create_index(
                    name=pinecone_index_name,
                    dimension=dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                logger.info(f"✅ Created Pinecone index: {pinecone_index_name}")
            else:
                logger.info(f"✅ Pinecone index already exists: {pinecone_index_name}")
            
            self.index_name = pinecone_index_name
            self.vectorstore = None  # Reset vectorstore to force recreation
            logger.info(f"✅ Switched to index: {pinecone_index_name} (from collection: {collection_name})")
        except Exception as e:
            logger.error(f"❌ Failed to switch index: {e}")
            raise
    
    def mmr_select_from_chunks(self, chunks: List[Dict[str, Any]], query_text: str,
                               k: int = 10, lambda_mult: float = 0.65) -> List[Dict[str, Any]]:
        """
        Apply MMR diversity selection to a combined list of chunks from multiple sources.
        
        Uses LangChain's native MMR algorithm with embeddings - no FAISS required.
        This is a pure Python implementation that works with any embedding model.
        
        Args:
            chunks: List of chunks to select from (already retrieved from multiple sources)
            query_text: Query text for MMR relevance calculation
            k: Number of chunks to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
        
        Returns:
            List of diverse chunks selected via MMR
        """
        logger.info(f"🔄 [mmr_select_from_chunks] Starting MMR selection with {len(chunks)} chunks, k={k}")
        
        if not chunks:
            logger.warning("⚠️ No chunks provided for MMR selection")
            return []
        
        if not LANGCHAIN_AVAILABLE:
            logger.warning("⚠️ LangChain not available - returning first k chunks without MMR")
            return chunks[:k]
        
        try:
            import numpy as np
            
            # Pure Python MMR implementation - no FAISS or vectorstore needed
            # Step 1: Embed query and all chunks
            logger.debug(f"   → Embedding query and {len(chunks)} chunks...")
            query_embedding = np.array(self.langchain_embeddings.embed_query(query_text))
            
            chunk_texts = [chunk.get("content", "") for chunk in chunks]
            chunk_embeddings = [np.array(emb) for emb in self.langchain_embeddings.embed_documents(chunk_texts)]
            
            # Step 2: Calculate query-document similarities
            def cosine_similarity(a, b):
                """Calculate cosine similarity between two vectors"""
                return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
            
            query_similarities = [cosine_similarity(query_embedding, emb) for emb in chunk_embeddings]
            
            # Step 3: MMR algorithm
            # Start with most relevant document
            selected_indices = []
            remaining_indices = list(range(len(chunks)))
            
            # Select first document (most relevant)
            first_idx = max(remaining_indices, key=lambda i: query_similarities[i])
            selected_indices.append(first_idx)
            remaining_indices.remove(first_idx)
            
            # Select remaining k-1 documents using MMR
            fetch_k = min(len(chunks), 50)  # Consider top fetch_k by relevance
            top_candidates = sorted(remaining_indices, key=lambda i: query_similarities[i], reverse=True)[:fetch_k]
            
            for _ in range(min(k - 1, len(remaining_indices))):
                if not top_candidates:
                    break
                
                best_score = -float('inf')
                best_idx = None
                
                for candidate_idx in top_candidates:
                    # Calculate relevance to query
                    relevance = query_similarities[candidate_idx]
                    
                    # Calculate max similarity to already selected documents
                    max_similarity = 0.0
                    for selected_idx in selected_indices:
                        similarity = cosine_similarity(
                            chunk_embeddings[candidate_idx],
                            chunk_embeddings[selected_idx]
                        )
                        max_similarity = max(max_similarity, similarity)
                    
                    # MMR score: balance relevance and diversity
                    mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_similarity
                    
                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = candidate_idx
                
                if best_idx is not None:
                    selected_indices.append(best_idx)
                    top_candidates.remove(best_idx)
            
            # Step 4: Return selected chunks in order
            diverse_chunks = [chunks[i] for i in selected_indices]
            
            logger.info(f"✅ MMR selection: {len(chunks)} chunks → {len(diverse_chunks)} diverse chunks")
            return diverse_chunks
            
        except ImportError as import_error:
            logger.warning(f"⚠️ NumPy not available ({import_error}), using simple similarity selection")
            # Fallback: Simple top-k by content length (very basic)
            diverse_chunks = sorted(chunks, key=lambda c: len(c.get("content", "")), reverse=True)[:k]
            logger.info(f"✅ Simple selection: {len(chunks)} chunks → {len(diverse_chunks)} chunks")
            return diverse_chunks
            
        except Exception as e:
            logger.error(f"❌ MMR selection failed: {e}")
            logger.warning("⚠️ Falling back to first k chunks")
            import traceback
            logger.error(traceback.format_exc())
            return chunks[:k]
    
    def delete_all_collections(self) -> None:
        """
        Delete all collections (for backward compatibility).
        
        Note: In Pinecone, this deletes the current index.
        Pinecone doesn't have a concept of "all collections" like ChromaDB.
        """
        logger.warning("⚠️ delete_all_collections() called - Pinecone doesn't support deleting all indexes")
        logger.warning("   This method only logs a warning for Pinecone")
        logger.info(f"   To delete the current index '{self.index_name}', use delete_collection()")
    
    def delete_collection(self, collection_name: str) -> None:
        """
        Delete a specific index (for backward compatibility).
        
        Args:
            collection_name: Name of the index to delete
        """
        try:
            self.pc.delete_index(collection_name)
            logger.info(f"✅ Deleted Pinecone index: {collection_name}")
            
            # If deleting current index, reset vectorstore
            if collection_name == self.index_name:
                self.vectorstore = None
        except Exception as e:
            logger.error(f"❌ Failed to delete index {collection_name}: {e}")
            raise
    
    def get_all_documents_paginated(self, batch_size: int = 500) -> List[Dict[str, Any]]:
        """
        Fetch all documents from the index (for backward compatibility).
        
        Note: Pinecone doesn't have a direct "get all" API.
        This method uses similarity_search with a dummy query to retrieve documents.
        This is not efficient for large indexes - consider using Pinecone's native query methods instead.
        """
        logger.warning("⚠️ get_all_documents_paginated() is not efficient for Pinecone")
        logger.warning("   Consider using Pinecone's native query methods instead")
        
        try:
            vectorstore = self._get_vectorstore()
            stats = self.get_stats()
            total_vectors = stats.get("total_vector_count", 0)
            
            if total_vectors == 0:
                return []
            
            # Use similarity_search with a dummy query to fetch documents
            # LangChain Pinecone stores text in page_content
            # Fetch as many as possible (Pinecone has limits)
            max_fetch = min(total_vectors, 10000)  # Pinecone query limit
            
            # Use a generic query that should match most documents
            dummy_query = "geography"
            docs = vectorstore.similarity_search(dummy_query, k=max_fetch)
            
            all_docs = []
            for doc in docs:
                # Extract ID from metadata if available, otherwise generate one
                doc_id = doc.metadata.get("id", f"doc_{len(all_docs)}")
                
                all_docs.append({
                    "id": doc_id,
                    "content": doc.page_content,
                    "metadata": doc.metadata
                })
            
            logger.info(f"📦 Retrieved {len(all_docs)} documents from Pinecone")
            return all_docs
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch all documents: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def fetch_all_chunks_native(self, filename: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all chunks from Pinecone using native API (no LangChain).
        
        ⚠️ READ-ONLY OPERATION - This method ONLY reads from Pinecone.
        It does NOT modify, delete, or write anything to Pinecone index.
        Safe to use without any risk of disturbing existing Pinecone data.
        
        Operations used (all read-only):
        - index.describe_index_stats() - Get index statistics
        - index.query() - Query vectors with metadata filter
        
        Args:
            filename: Optional filename to filter chunks. If None, fetches all chunks.
        
        Returns:
            List of dicts with keys: id, metadata (including chunk_id, filename, content_preview, etc.)
        """
        try:
            index = self.pc.Index(self.index_name)
            
            # ⚠️ READ-ONLY: Get index stats (no modifications)
            stats = index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            
            if total_vectors == 0:
                logger.info("📦 No vectors found in Pinecone index")
                return []
            
            logger.info(f"📦 Fetching chunks from Pinecone (total vectors: {total_vectors})...")
            
            all_chunks = []
            
            # Pinecone list API returns IDs in batches
            # We'll use list to get IDs, then fetch to get metadata
            # But list doesn't support filtering, so we'll filter after fetching
            
            # Method 1: Use query with dummy vector and filter (if filename provided)
            if filename:
                logger.info(f"   Filtering by filename: {filename}")
                # Create a dummy zero vector (we're filtering by metadata, not similarity)
                dummy_vector = [0.0] * self.langchain_embeddings.dimensionality
                
                # ⚠️ READ-ONLY: Query Pinecone (no modifications to index)
                # Query with metadata filter
                # Pinecone query has a limit, so we need to paginate
                # Use a high top_k and paginate if needed
                top_k = min(10000, total_vectors)  # Pinecone limit is 10000
                
                query_response = index.query(
                    vector=dummy_vector,
                    top_k=top_k,
                    filter={"filename": {"$eq": filename}},
                    include_metadata=True
                )
                
                for match in query_response.get('matches', []):
                    chunk_data = {
                        'id': match.get('id'),
                        'metadata': match.get('metadata', {})
                    }
                    all_chunks.append(chunk_data)
                
                logger.info(f"   ✅ Fetched {len(all_chunks)} chunks for filename: {filename}")
            
            else:
                # Fetch all chunks - use query with zero vector (Pinecone doesn't have direct list API)
                logger.info("   Fetching all chunks using query API (this may take a while)...")
                
                # Create a zero vector (we're not filtering by similarity, just getting all)
                dummy_vector = [0.0] * self.langchain_embeddings.dimensionality
                
                # ⚠️ READ-ONLY: Query Pinecone (no modifications to index)
                # Query with high top_k to get as many chunks as possible
                # Pinecone limit is 10000 per query
                top_k = min(10000, total_vectors)
                
                query_response = index.query(
                    vector=dummy_vector,
                    top_k=top_k,
                    include_metadata=True,
                    include_values=False  # We don't need the vectors
                )
                
                for match in query_response.get('matches', []):
                    chunk_data = {
                        'id': match.get('id'),
                        'metadata': match.get('metadata', {})
                    }
                    all_chunks.append(chunk_data)
                
                logger.info(f"   ✅ Fetched {len(all_chunks)} chunks (limit: {top_k})")
                
                # If we hit the limit and there are more chunks, warn user
                if len(all_chunks) >= top_k and total_vectors > top_k:
                    logger.warning(f"⚠️ Fetched {len(all_chunks)} chunks but index has {total_vectors} total")
                    logger.warning(f"   Consider filtering by filename for better results")
            
            return all_chunks
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch chunks from Pinecone: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

