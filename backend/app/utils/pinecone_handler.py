"""
Pinecone vector store handler with LangChain integration
"""
import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

# LangChain imports
try:
    from langchain_pinecone import PineconeVectorStore
    from langchain_core.embeddings import Embeddings
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    # Create dummy classes if import fails (to prevent NameError)
    class Embeddings:
        pass
    class PineconeVectorStore:
        pass
    class Document:
        pass
    class BaseRetriever:
        pass

try:
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

from ..core.config import settings
from .embedder import Embedder

logger = logging.getLogger(__name__)

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
        
        # Filter out empty or invalid documents
        valid_indices = []
        filtered_documents = []
        filtered_metadatas = []
        
        for i, doc in enumerate(documents):
            if isinstance(doc, str) and doc.strip() and len(doc.strip()) > 10:
                valid_indices.append(i)
                filtered_documents.append(doc.strip())
                filtered_metadatas.append(metadatas[i])
        
        if not filtered_documents:
            logger.warning("⚠️ No valid documents to embed after filtering")
            return
        
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
                
                if len(embeddings) != len(batch_docs):
                    logger.error(f"❌ Embedding count mismatch: {len(embeddings)} embeddings for {len(batch_docs)} documents")
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
                doc_content = batch_docs[idx]  # Get the original content for preview
                
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
                flat_metadata["content_preview"] = content_preview
                
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
                       filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query for most relevant documents
        
        Args:
            query_text: Text to search for
            k: Number of results to return
            filter_metadata: Optional dict to filter by metadata fields
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
                # Use content_preview from metadata if available (since we store preview, not full text)
                # Fall back to page_content for backward compatibility
                content = doc.metadata.get("content_preview") or doc.page_content or ""
                
                chunk = {
                    "content": content,
                    "metadata": doc.metadata,
                    "distance": 0.0  # Pinecone doesn't return distances in similarity_search
                }
                
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
            
            # Retrieve diverse chunks
            docs = retriever.get_relevant_documents(query_text)
            
            # Format results
            formatted_results = []
            for doc in docs:
                chunk = {
                    "content": doc.metadata.get("content_preview") or doc.page_content or "",
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
        
        This uses FAISS internally (same as ChromaDB version) to avoid compatibility issues.
        
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
            from langchain_core.documents import Document
            from langchain_community.vectorstores import FAISS
            
            # Convert chunks to LangChain Documents
            documents = []
            for chunk in chunks:
                doc = Document(
                    page_content=chunk.get("content", ""),
                    metadata=chunk.get("metadata", {})
                )
                documents.append(doc)
            
            # Create temporary FAISS vectorstore
            vectorstore = FAISS.from_documents(documents, self.langchain_embeddings)
            
            # Create MMR retriever
            retriever = vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "fetch_k": min(len(chunks), 50),
                    "k": k,
                    "lambda_mult": lambda_mult
                }
            )
            
            # Retrieve diverse chunks
            diverse_docs = retriever.get_relevant_documents(query_text)
            
            # Convert back to our chunk format
            diverse_chunks = []
            for doc in diverse_docs:
                chunk = {
                    "content": doc.metadata.get("content_preview") or doc.page_content or "",
                    "metadata": doc.metadata,
                    "distance": 0.0
                }
                diverse_chunks.append(chunk)
            
            logger.info(f"✅ MMR selection: {len(chunks)} chunks → {len(diverse_chunks)} diverse chunks")
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
                    "content": doc.metadata.get("content_preview") or doc.page_content or "",
                    "metadata": doc.metadata
                })
            
            logger.info(f"📦 Retrieved {len(all_docs)} documents from Pinecone")
            return all_docs
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch all documents: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

