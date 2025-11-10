"""
ChromaDB vector store handler
"""
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
try:
    import numpy as np
except ImportError:
    np = None
try:
    from chromadb.errors import NotFoundError
except ImportError:
    # ChromaDB version compatibility - NotFoundError might not exist in older versions
    class NotFoundError(Exception):
        pass
from fastapi import HTTPException

# LangChain imports for MMR retriever
try:
    from langchain_community.vectorstores import Chroma as LangChainChroma
    from langchain_core.embeddings import Embeddings
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from ..core.config import settings
from .embedder import Embedder

logger = logging.getLogger(__name__)

# Log LangChain availability after logger is initialized
if not LANGCHAIN_AVAILABLE:
    logger.warning("LangChain not available - MMR retriever will not work")

class ChromaHandler:
    def __init__(self):
        """Initialize ChromaDB client and collection"""
        # Initialize client with telemetry disabled
        # Disable telemetry to avoid posthog errors
        import os
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
        
        self.client = chromadb.PersistentClient(
            path=str(settings.DB_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
        )

        # Initialize embedder
        self.embedder = Embedder()
        
        # Check existing collection dimension to ensure consistency
        self.expected_dimension = None

        # Check if collection exists
        try:
            try:
                self.collection = self.client.get_collection(name=settings.COLLECTION_NAME)
                logger.info(f"Found existing collection: {settings.COLLECTION_NAME}")
            except AttributeError as attr_err:
                error_msg = str(attr_err)
                # Check if it's the ChromaDB internal dimensionality error
                if "dimensionality" in error_msg.lower() and ("dict" in error_msg.lower() or "attribute" in error_msg.lower()):
                    logger.error(f"❌ ChromaDB collection metadata corruption detected: {attr_err}")
                    logger.error("   The collection's persisted metadata has dimensionality stored as dict")
                    logger.error("   This is a ChromaDB version compatibility issue")
                    logger.warning("   Attempting to fix by deleting and recreating collection...")
                    logger.warning("   ⚠️ ALL DATA IN THIS COLLECTION WILL BE LOST!")
                    
                    # Delete the corrupted collection
                    try:
                        self.client.delete_collection(name=settings.COLLECTION_NAME)
                        logger.info(f"✅ Deleted corrupted collection: {settings.COLLECTION_NAME}")
                    except Exception as del_err:
                        logger.error(f"❌ Failed to delete corrupted collection: {del_err}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Collection metadata is corrupted and cannot be fixed automatically. Please manually delete the collection '{settings.COLLECTION_NAME}' from the database directory: {settings.DB_DIR}"
                        )
                    
                    # Create a fresh collection
                    self.collection = self.client.create_collection(
                        name=settings.COLLECTION_NAME,
                        metadata={"hnsw:space": settings.DISTANCE_METRIC}
                    )
                    logger.info(f"✅ Created fresh collection: {settings.COLLECTION_NAME}")
                    logger.warning("   ⚠️ Collection is now empty - you'll need to re-upload your documents")
                else:
                    # Re-raise if it's a different AttributeError
                    raise
            
            # Check existing dimension to ensure consistency
            try:
                count = self.collection.count()
                if count > 0:
                    # Try to get sample embeddings
                    sample = self.collection.get(limit=1, include=['embeddings'])
                    # Check for None explicitly to avoid numpy array truthiness issues
                    if sample is not None:
                        embeddings = sample.get('embeddings')
                        # Check if embeddings exists and is not empty (avoid numpy array truthiness)
                        if embeddings is not None:
                            try:
                                embeddings_len = len(embeddings)
                                if embeddings_len > 0:
                                    embedding_list = embeddings[0]
                                    # Handle numpy arrays - check length without truthiness check
                                    try:
                                        embedding_length = len(embedding_list)
                                        if embedding_length > 0:
                                            self.expected_dimension = embedding_length
                                            logger.info(f"📏 Collection has {count} chunks with {self.expected_dimension}-dim embeddings")
                                            logger.info(f"   ⚠️ All new chunks MUST use {self.expected_dimension}-dim embeddings for consistency!")
                                        else:
                                            logger.info(f"📏 Collection has {count} chunks but couldn't determine dimension (will detect on first add)")
                                    except (TypeError, ValueError) as len_error:
                                        logger.debug(f"Could not get embedding length: {len_error}")
                                        logger.info(f"📏 Collection has {count} chunks but couldn't determine dimension (will detect on first add)")
                                else:
                                    logger.info(f"📏 Collection has {count} chunks but couldn't retrieve embeddings (will detect on first add)")
                            except (TypeError, ValueError) as len_error:
                                logger.debug(f"Could not get embeddings length: {len_error}")
                                logger.info(f"📏 Collection has {count} chunks but couldn't retrieve embeddings (will detect on first add)")
                        else:
                            logger.info(f"📏 Collection has {count} chunks but couldn't retrieve embeddings (will detect on first add)")
                    else:
                        logger.info(f"📏 Collection has {count} chunks but couldn't retrieve embeddings (will detect on first add)")
                else:
                    logger.info(f"📏 Collection is empty (new collection)")
            except Exception as dim_check_error:
                logger.warning(f"⚠️ Could not check existing dimension: {dim_check_error}")
                logger.info(f"   Will detect dimension on first add")
        except ValueError:
            # Collection doesn't exist, create new one
            self.collection = self.client.create_collection(
                name=settings.COLLECTION_NAME,
                metadata={"hnsw:space": settings.DISTANCE_METRIC}
            )
            logger.info(f"Created new collection: {settings.COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"❌ Error accessing collection: {e}")
            raise

        logger.info(f"✅ Initialized ChromaDB collection: {self.collection.name}")

    def add_documents(self, chunks_with_metadata: List[Dict[str, Any]]) -> None:
        """Add document chunks to ChromaDB"""
        if not chunks_with_metadata:
            logger.warning("No chunks provided")
            return

        try:
            # Extract texts and metadata
            documents = [item['content'] for item in chunks_with_metadata]
            metadatas = [item['metadata'] for item in chunks_with_metadata]

            # Log what we're about to store
            logger.info(f"💾 Preparing to store {len(documents)} chunks in ChromaDB")
            if documents:
                logger.info(f"   • First chunk content preview: {documents[0][:200].replace(chr(10), ' ')}...")
                logger.info(f"   • First chunk metadata: {metadatas[0]}")
                if len(documents) > 1:
                    logger.info(f"   • Last chunk content preview: {documents[-1][:200].replace(chr(10), ' ')}...")
                    logger.info(f"   • Last chunk metadata: {metadatas[-1]}")

            # Filter out empty or invalid documents before embedding
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
            
            logger.info(f"📊 Filtered {len(documents)} → {len(filtered_documents)} valid documents")
            
            # Log what will actually be stored after filtering
            if filtered_documents:
                logger.info(f"   • Sample filtered chunk: {filtered_documents[0][:200].replace(chr(10), ' ')}...")
                logger.info(f"   • Sample filtered metadata: {filtered_metadatas[0]}")

            # Generate embeddings - ensure dimension consistency
            # Only enforce dimension if we successfully detected existing dimension
            if self.expected_dimension is not None:
                logger.info(f"🔍 Ensuring embeddings match existing dimension: {self.expected_dimension}")
                # Force OpenAI if we need 1536 dims, or Sentence Transformers if 384 dims
                if self.expected_dimension == 1536:
                    if not self.embedder.openai_client:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Collection requires 1536-dim embeddings (OpenAI), but OpenAI API key is not available. Please set OPENAI_API_KEY in your .env file."
                        )
                    logger.info(f"   → Using OpenAI embeddings (1536 dims) to match collection")
                    try:
                        embeddings = self.embedder.get_openai_embeddings(filtered_documents)
                    except Exception as embed_error:
                        # If OpenAI fails due to token limit, fail gracefully - don't fall back
                        error_msg = str(embed_error)
                        if "token" in error_msg.lower() or "8192" in error_msg:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Chunks are too large for OpenAI embeddings (token limit exceeded). Some chunks exceed 8192 tokens. Please reduce chunk sizes or preprocess text better. Error: {error_msg}"
                            )
                        raise
                elif self.expected_dimension == 384:
                    logger.info(f"   → Using Sentence Transformers embeddings (384 dims) to match collection")
                    embeddings = self.embedder.get_sbert_embeddings(filtered_documents)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported embedding dimension: {self.expected_dimension}. Expected 1536 (OpenAI) or 384 (Sentence Transformers)."
                    )
            else:
                # No existing dimension detected (new collection or couldn't read) - use OpenAI if available
                logger.info(f"🔍 No existing dimension detected - using OpenAI if available")
                if self.embedder.openai_client:
                    try:
                        embeddings = self.embedder.get_openai_embeddings(filtered_documents)
                        if embeddings and len(embeddings) > 0:
                            actual_dim = len(embeddings[0])
                            logger.info(f"📏 Collection initialized with {actual_dim}-dim embeddings (OpenAI)")
                            self.expected_dimension = actual_dim
                    except Exception as embed_error:
                        error_msg = str(embed_error)
                        if "token" in error_msg.lower() or "8192" in error_msg:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Chunks are too large for OpenAI embeddings (token limit exceeded). Some chunks exceed 8192 tokens. Please reduce chunk sizes. Error: {error_msg}"
                            )
                        # For other errors, fall back to Sentence Transformers
                        logger.warning(f"⚠️ OpenAI failed, falling back to Sentence Transformers: {embed_error}")
                        embeddings = self.embedder.get_sbert_embeddings(filtered_documents)
                        if embeddings and len(embeddings) > 0:
                            actual_dim = len(embeddings[0])
                            logger.info(f"📏 Collection initialized with {actual_dim}-dim embeddings (Sentence Transformers)")
                            self.expected_dimension = actual_dim
                else:
                    # No OpenAI - use Sentence Transformers
                    embeddings = self.embedder.get_sbert_embeddings(filtered_documents)
                    if embeddings and len(embeddings) > 0:
                        actual_dim = len(embeddings[0])
                        logger.info(f"📏 Collection initialized with {actual_dim}-dim embeddings (Sentence Transformers)")
                        self.expected_dimension = actual_dim
            
            if not embeddings:
                logger.warning("⚠️ No embeddings generated, skipping add")
                return

            # Verify dimension matches expected
            if embeddings and self.expected_dimension:
                actual_dim = len(embeddings[0])
                if actual_dim != self.expected_dimension:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Embedding dimension mismatch! Generated {actual_dim}-dim embeddings but collection requires {self.expected_dimension}-dim embeddings. Cannot mix different embedding models."
                    )

            # Ensure embeddings match documents length
            if len(embeddings) != len(filtered_documents):
                logger.error(f"❌ Mismatch: {len(filtered_documents)} documents but {len(embeddings)} embeddings")
                # Use the minimum length to avoid crashes
                min_len = min(len(embeddings), len(filtered_documents))
                filtered_documents = filtered_documents[:min_len]
                filtered_metadatas = filtered_metadatas[:min_len]
                embeddings = embeddings[:min_len]
                logger.warning(f"⚠️ Truncated to {min_len} items to match")

            # Generate IDs for filtered documents
            ids = [f"doc_{i}_{hash(doc)}" for i, doc in enumerate(filtered_documents)]

            # Add to collection
            self.collection.add(
                embeddings=embeddings,
                documents=filtered_documents,
                metadatas=filtered_metadatas,
                ids=ids
            )

            logger.info(f"✅ Successfully stored {len(filtered_documents)} chunks in ChromaDB")
            logger.info(f"   • Collection: {self.collection.name}")
            logger.info(f"   • Embedding dimension: {len(embeddings[0]) if embeddings else 'N/A'}")
            
            # Verify storage by querying one document back
            try:
                sample_id = ids[0] if ids else None
                if sample_id:
                    retrieved = self.collection.get(ids=[sample_id], include=['documents', 'metadatas'])
                    if retrieved['documents']:
                        logger.info(f"   • Verification: Successfully retrieved stored chunk (ID: {sample_id[:50]}...)")
                        logger.info(f"   • Retrieved content preview: {retrieved['documents'][0][:200].replace(chr(10), ' ')}...")
                        logger.info(f"   • Retrieved metadata: {retrieved['metadatas'][0]}")
            except Exception as verify_error:
                logger.warning(f"   ⚠️ Could not verify storage: {verify_error}")

        except Exception as e:
            error_msg = str(e)
            # Check if it's a dimension mismatch error
            if "dimension" in error_msg.lower() or "expecting embedding" in error_msg.lower():
                # Check if collection actually has data with different dimension
                existing_count = 0
                existing_dim = None
                try:
                    existing_count = self.collection.count()
                    if existing_count > 0:
                        sample = self.collection.get(limit=1, include=['embeddings'])
                        if sample and sample.get('embeddings') and len(sample['embeddings']) > 0:
                            embedding_list = sample['embeddings'][0]
                            if embedding_list and len(embedding_list) > 0:
                                existing_dim = len(embedding_list)
                except Exception as check_err:
                    logger.debug(f"Could not check existing dimension: {check_err}")
                
                new_dim = len(embeddings[0]) if embeddings and len(embeddings) > 0 else 0
                
                # Only fail if we actually have existing chunks with a different dimension
                if existing_count > 0 and existing_dim is not None and existing_dim != new_dim:
                    logger.error(f"❌ CRITICAL: Dimension mismatch!")
                    logger.error(f"   • Existing chunks: {existing_count}")
                    logger.error(f"   • Existing dimension: {existing_dim}")
                    logger.error(f"   • New dimension: {new_dim}")
                    
                    # If trying to upgrade from 384 to 1536, provide helpful message
                    if existing_dim == 384 and new_dim == 1536:
                        logger.error(f"   • Collection has old 384-dim embeddings (Sentence Transformers)")
                        logger.error(f"   • Trying to add new 1536-dim embeddings (OpenAI)")
                        logger.error(f"   • Solution: Delete the collection first, then re-upload all files")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot add chunks: Collection has {existing_count} chunks with 384-dim embeddings (Sentence Transformers), but new chunks use 1536-dim embeddings (OpenAI). To upgrade to OpenAI embeddings, delete the collection first using the delete_collection script, then re-upload all files."
                        )
                    else:
                        logger.error(f"   • Collection will NOT be reset to prevent data loss!")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot add chunks: Dimension mismatch! Collection has {existing_count} chunks with {existing_dim}-dim embeddings, but new chunks have {new_dim}-dim embeddings. Please ensure all chunks use the same embedding model."
                        )
                else:
                    # If we can't determine existing dimension or collection is empty, 
                    # this might be a ChromaDB internal error - log and re-raise original error
                    logger.error(f"❌ ChromaDB error (possibly dimension-related but can't verify): {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to add documents to ChromaDB: {error_msg}"
                    )
            else:
                logger.error(f"❌ Failed to add documents: {e}")
                raise

    def query_documents(self, query_text: str, k: int = 5, 
                      filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query for most relevant documents
        
        Args:
            query_text: Text to search for
            k: Number of results to return
            filter_metadata: Optional dict to filter by metadata fields
                            Example: {"filename": "pyq"} or {"major_domain": "Indian Geography"}
                            Supports substring matching for string fields
        """
        try:
            # Generate query embedding
            query_embedding = self.embedder.get_embeddings([query_text])[0]

            # Query more results if filtering is needed (to ensure we get enough after filtering)
            query_k = k * 3 if filter_metadata else k

            # Query collection
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=query_k,
                include=['documents', 'metadatas', 'distances']
            )

            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    chunk = {
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i]
                    }
                    
                    # Apply metadata filtering if specified
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
            return formatted_results[:k]  # Return only requested k

        except AttributeError as attr_err:
            error_msg = str(attr_err)
            # Check if it's the ChromaDB internal dimensionality error
            if "dimensionality" in error_msg.lower() and ("dict" in error_msg.lower() or "attribute" in error_msg.lower()):
                logger.error(f"❌ ChromaDB collection metadata corruption detected during query: {attr_err}")
                logger.error("   The collection's persisted metadata has dimensionality stored as dict")
                logger.error("   This is a ChromaDB version compatibility issue with the persisted collection")
                logger.error("   The collection metadata needs to be fixed or the collection recreated")
                import traceback
                logger.error(f"   Stack trace:\n{traceback.format_exc()}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Collection metadata is corrupted. The collection '{self.collection.name}' has incompatible metadata format. Please delete and recreate the collection, or contact support for a migration script."
                )
            # Re-raise if it's a different AttributeError
            raise
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(f"❌ Query failed: {e}")
            logger.error(f"   Error type: {error_type}")
            # Check if it's the dimensionality error
            if "dimensionality" in error_msg.lower() or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                logger.error("   ⚠️ This is a dimensionality error - unexpected in query_documents()!")
                logger.error("   query_documents() doesn't use LangChain, so this shouldn't happen here")
                import traceback
                logger.error(f"   Stack trace:\n{traceback.format_exc()}")
            raise

    def delete_all_collections(self) -> None:
        """Delete all collections and their data"""
        try:
            # Get all collections
            collections = self.client.list_collections()
            for collection in collections:
                self.client.delete_collection(collection.name)
                logger.info(f"Deleted collection: {collection.name}")
            
            # Create fresh collection
            self.collection = self.client.create_collection(
                name=settings.COLLECTION_NAME,
                metadata={"hnsw:space": settings.DISTANCE_METRIC}
            )
            logger.info(f"✨ Created fresh collection: {settings.COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"❌ Failed to delete collections: {e}")
            raise

    def reset_collection(self) -> None:
        """Reset the collection to handle dimension mismatch"""
        try:
            # Delete existing collection
            self.client.delete_collection(settings.COLLECTION_NAME)
            logger.info(f"Deleted collection: {settings.COLLECTION_NAME}")
            
            # Create new collection
            self.collection = self.client.create_collection(
                name=settings.COLLECTION_NAME,
                metadata={"hnsw:space": settings.DISTANCE_METRIC}
            )
            logger.info(f"Created new collection: {settings.COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"❌ Failed to reset collection: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": self.collection.name
            }
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {"error": str(e)}

    def create_new_collection(self, collection_name: str) -> None:
        """Create a new collection for newly processed chunks"""
        try:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": settings.DISTANCE_METRIC}
            )
            logger.info(f"✨ Created new collection: {collection_name}")
        except Exception as e:
            logger.error(f"❌ Failed to create new collection: {e}")
            raise

    def delete_collection(self, collection_name: str) -> None:
        """Delete a specific collection by name"""
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"✅ Deleted collection: {collection_name}")
        except NotFoundError:
            logger.warning(f"Collection {collection_name} not found, nothing to delete")
        except Exception as e:
            logger.error(f"❌ Failed to delete collection {collection_name}: {e}")
            raise

    def get_all_documents_paginated(self, batch_size: int = 500) -> List[Dict[str, Any]]:
        """Fetch all documents from the collection in small batches."""
        try:
            total_count = self.collection.count()
            if total_count == 0:
                logger.info("📦 Collection is empty, no documents to retrieve")
                return []
            
            logger.info(f"📦 Fetching {total_count} documents using query method...")
            all_docs = []
            
            # Simple approach: Query with a generic term and get max results
            try:
                query_text = "geography"
                logger.info(f"   Generating embedding for query: '{query_text}'")
                query_embedding = self.embedder.get_embeddings([query_text])[0]
                logger.info(f"   Embedding dimension: {len(query_embedding)}")
                
                # Query for maximum results
                max_results = min(total_count, 10000)
                logger.info(f"   Querying for up to {max_results} results...")
                
                query_results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_results,
                    include=['documents', 'metadatas']  # IDs are always returned, don't include in include list
                )
                
                logger.info(f"   Query returned keys: {list(query_results.keys()) if query_results else 'None'}")
                
                if query_results and 'documents' in query_results:
                    documents_list = query_results['documents']
                    if documents_list and len(documents_list) > 0:
                        documents = documents_list[0]
                        metadatas = query_results.get('metadatas', [[]])
                        ids = query_results.get('ids', [[]])
                        
                        meta_list = metadatas[0] if metadatas and len(metadatas) > 0 else []
                        id_list = ids[0] if ids and len(ids) > 0 else []
                        
                        logger.info(f"   Found {len(documents)} documents")
                        
                        for i in range(len(documents)):
                            doc_id = id_list[i] if i < len(id_list) else f"doc_{i}"
                            meta = meta_list[i] if i < len(meta_list) else {}
                            all_docs.append({
                                "id": doc_id,
                                "content": documents[i],
                                "metadata": meta
                            })
                    else:
                        logger.warning(f"   Documents list is empty")
                else:
                    logger.error(f"   Query did not return 'documents' key")
                    
            except Exception as query_err:
                logger.error(f"❌ Error in query: {query_err}")
                import traceback
                logger.error(traceback.format_exc())
                raise
            
            logger.info(f"✅ Retrieved {len(all_docs)} total documents")
            return all_docs
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch all documents in batches: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def update_metadata_batch(self, docs_with_metadata: List[Dict[str, Any]]) -> None:
        """Safely merge new metadata with existing ones instead of overwriting."""
        if not docs_with_metadata:
            return
        
        try:
            for item in docs_with_metadata:
                doc_id = item["id"]
                new_meta = item["metadata"]
                existing = self.collection.get(ids=[doc_id], include=['metadatas'])
                
                merged_meta = existing['metadatas'][0] if existing['metadatas'] else {}
                merged_meta.update(new_meta)
                
                self.collection.update(ids=[doc_id], metadatas=[merged_meta])
            
            logger.info(f"✅ Merged metadata for {len(docs_with_metadata)} documents")
        except Exception as e:
            logger.error(f"❌ Failed to merge metadata batch: {e}")
            raise

    def get_unenriched_documents(self, key: str = "major_domain") -> List[Dict[str, Any]]:
        """Return only docs missing a given metadata key (e.g., major_domain)."""
        all_docs = self.get_all_documents_paginated()
        unenriched = [d for d in all_docs if key not in d["metadata"]]
        logger.info(f"🧠 Found {len(unenriched)} unenriched documents (missing '{key}')")
        return unenriched

    def switch_to_collection(self, collection_name: str) -> None:
        """Switch active collection to the specified collection name, creating it if necessary."""
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"✅ Switched to collection: {collection_name}")
            
            # Check existing dimension to warn about mismatches, but default to OpenAI (1536)
            existing_dimension = None
            try:
                count = self.collection.count()
                if count > 0:
                    # Try to get sample embeddings to detect dimension
                    sample = self.collection.get(limit=1, include=['embeddings'])
                    # Check for None explicitly to avoid numpy array truthiness issues
                    if sample is not None:
                        embeddings = sample.get('embeddings')
                        # Check if embeddings exists and is not empty (avoid numpy array truthiness)
                        if embeddings is not None:
                            try:
                                # Check if embeddings is a list/array
                                if isinstance(embeddings, (list, tuple)) and len(embeddings) > 0:
                                    embedding_list = embeddings[0]
                                    # Check if embedding_list is actually a list/array (not an int)
                                    try:
                                        if isinstance(embedding_list, (list, tuple)) or (np is not None and isinstance(embedding_list, np.ndarray)):
                                            embedding_length = len(embedding_list)
                                            if embedding_length > 0:
                                                existing_dimension = embedding_length
                                                logger.info(f"📏 Collection '{collection_name}' has {count} chunks with {existing_dimension}-dim embeddings")
                                                
                                                # If existing is 384-dim, warn but we'll still try OpenAI first
                                                if existing_dimension == 384:
                                                    logger.warning(f"   ⚠️ Collection has 384-dim embeddings (Sentence Transformers)")
                                                    logger.warning(f"   ⚠️ Will try OpenAI (1536-dim) first - if mismatch occurs, old chunks may need to be deleted")
                                                elif existing_dimension == 1536:
                                                    logger.info(f"   ✅ Collection already uses 1536-dim embeddings (OpenAI) - perfect match!")
                                                else:
                                                    logger.warning(f"   ⚠️ Collection has {existing_dimension}-dim embeddings (unexpected dimension)")
                                            else:
                                                logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't determine dimension")
                                        elif isinstance(embedding_list, (int, float)):
                                            # If it's a number, it might be the dimension itself (unlikely but handle it)
                                            logger.warning(f"⚠️ Unexpected embedding format: got number instead of array")
                                            logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't determine dimension")
                                        else:
                                            logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't determine dimension (unexpected type: {type(embedding_list)})")
                                    except (TypeError, ValueError) as len_error:
                                        logger.debug(f"Could not get embedding length: {len_error}")
                                        logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't determine dimension")
                                else:
                                    logger.info(f"📏 Collection '{collection_name}' has {count} chunks but embeddings format is unexpected")
                            except (TypeError, ValueError) as len_error:
                                logger.debug(f"Could not get embeddings length: {len_error}")
                                logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't retrieve embeddings")
                        else:
                            logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't retrieve embeddings")
                    else:
                        logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't retrieve embeddings")
                else:
                    logger.info(f"📏 Collection '{collection_name}' is empty (new collection)")
            except Exception as dim_check_error:
                logger.warning(f"⚠️ Could not check dimension for collection '{collection_name}': {dim_check_error}")
            
            # Default to OpenAI (1536 dims) - will be enforced in add_documents
            # Only set expected_dimension if we want to match existing, otherwise let it default to OpenAI
            if existing_dimension == 1536:
                # Collection already uses OpenAI, so enforce it
                self.expected_dimension = 1536
            else:
                # Try OpenAI first (1536 dims) - don't enforce existing dimension if it's 384
                # This allows us to upgrade collections from 384 to 1536
                self.expected_dimension = None  # Will default to OpenAI in add_documents
                logger.info(f"   🎯 Will use OpenAI (1536-dim) embeddings by default")
                
        except NotFoundError:
            logger.warning(f"Collection {collection_name} not found. Creating new one.")
            self.create_new_collection(collection_name)
            # New collection - will use OpenAI (1536 dims) by default
            self.expected_dimension = None

    def delete_documents_by_filename(self, filename: str) -> int:
        """
        Delete all documents/chunks that match a specific filename.
        
        Args:
            filename: The filename to match (supports substring matching)
        
        Returns:
            Number of documents deleted
        """
        try:
            # Get all documents with matching filename
            all_docs = self.get_all_documents_paginated()
            matching_docs = [
                doc for doc in all_docs 
                if filename.lower() in doc.get('metadata', {}).get('filename', '').lower()
            ]
            
            if not matching_docs:
                logger.info(f"ℹ️  No documents found with filename containing '{filename}'")
                return 0
            
            # Get IDs of matching documents
            ids_to_delete = [doc['id'] for doc in matching_docs]
            
            # Delete by IDs
            self.collection.delete(ids=ids_to_delete)
            
            logger.info(f"✅ Deleted {len(ids_to_delete)} documents matching filename '{filename}'")
            return len(ids_to_delete)
            
        except Exception as e:
            logger.error(f"❌ Failed to delete documents by filename: {e}")
            raise

    def get_mmr_retriever(self, fetch_k: int = 50, k: int = 10, lambda_mult: float = 0.7):
        """
        ⚠️ DEPRECATED: This method has compatibility issues with ChromaDB persistent collections.
        
        ChromaDB stores embedding function metadata as a dict, but LangChain expects an object
        with a .dimensionality attribute, causing 'dict' object has no attribute 'dimensionality' errors.
        
        Use mmr_select_from_chunks() instead, which uses FAISS for MMR and avoids this issue.
        
        Create an MMR (Maximum Marginal Relevance) retriever using LangChain.
        
        MMR balances relevance and diversity by selecting documents that are:
        - Relevant to the query
        - Diverse from each other (not redundant)
        
        Args:
            fetch_k: Number of documents to fetch before applying MMR (default: 50)
            k: Number of documents to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
                        Default 0.7 balances both
        
        Returns:
            LangChain MMR retriever instance
        
        Raises:
            ValueError: If ChromaDB/LangChain compatibility issues prevent retriever creation
        """
        if not LANGCHAIN_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="LangChain is not available. Please install langchain and langchain-community."
            )
        
        try:
            # Create a LangChain-compatible embeddings wrapper
            class ChromaEmbeddings(Embeddings):
                """Wrapper to make our embedder compatible with LangChain"""
                def __init__(self, embedder):
                    self.embedder = embedder
                    # Determine dimensionality by actually generating a test embedding
                    # This ensures accuracy regardless of which embedder is used
                    try:
                        # Generate a test embedding to determine actual dimension
                        test_embedding = embedder.get_embeddings(["test"])[0]
                        # Set as regular attribute (not property) for LangChain compatibility
                        self.dimensionality = len(test_embedding)
                        logger.debug(f"✅ Detected embedding dimensionality: {self.dimensionality}")
                    except Exception as dim_error:
                        # Fallback to expected dimensions based on embedder availability
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
            
            # Create LangChain embeddings wrapper
            langchain_embeddings = ChromaEmbeddings(self.embedder)
            
            # CRITICAL FIX: Reset collection's embedding_function attributes if they're dicts
            # The issue: ChromaDB stores embedding_function metadata as a dict when collection
            # was created without a LangChain embeddings object. LangChain tries to use this dict
            # and fails when accessing .dimensionality attribute.
            # Solution: Reset ALL possible embedding_function attributes to None so LangChain uses our explicit embedding_function instead.
            collection_obj = self.client.get_collection(name=self.collection.name)
            
            # Check and reset _embedding_function (private attribute)
            if hasattr(collection_obj, "_embedding_function"):
                if isinstance(collection_obj._embedding_function, dict):
                    logger.debug("⚠️ Collection has _embedding_function as dict, resetting to None")
                    collection_obj._embedding_function = None
                elif hasattr(collection_obj._embedding_function, '__dict__'):
                    # Check if it's an object with dict-like attributes
                    try:
                        if isinstance(collection_obj._embedding_function, dict) or str(type(collection_obj._embedding_function)) == "<class 'dict'>":
                            logger.debug("⚠️ Collection _embedding_function is dict-like, resetting to None")
                            collection_obj._embedding_function = None
                    except:
                        pass
            
            # Check and reset embedding_function (public attribute, if it exists)
            if hasattr(collection_obj, "embedding_function"):
                if isinstance(collection_obj.embedding_function, dict):
                    logger.debug("⚠️ Collection has embedding_function as dict, resetting to None")
                    collection_obj.embedding_function = None
            
            # Check collection metadata for embedding_function info
            if hasattr(collection_obj, "metadata") and isinstance(collection_obj.metadata, dict):
                if "embedding_function" in collection_obj.metadata:
                    logger.debug("⚠️ Collection metadata contains embedding_function, removing it")
                    # Don't modify metadata directly, but log it
                    # The metadata is read-only, but we've already reset the attributes above
            
            # CRITICAL FIX: Always pass embedding_function explicitly
            # The issue: When LangChainChroma is created without embedding_function,
            # it tries to read from collection metadata (which is a dict), causing
            # 'dict' object has no attribute 'dimensionality' error.
            # Solution: Always pass embedding_function explicitly so LangChain doesn't
            # try to read from stored metadata.
            
            # DEBUG: Log types before creating LangChainChroma
            logger.debug(f"🔍 Type of langchain_embeddings: {type(langchain_embeddings)}")
            logger.debug(f"   Has dim? {hasattr(langchain_embeddings, 'dimensionality')}")
            if hasattr(langchain_embeddings, 'dimensionality'):
                try:
                    dim_val = langchain_embeddings.dimensionality
                    logger.debug(f"   dimensionality value: {dim_val} (type: {type(dim_val)})")
                except Exception as dim_err:
                    logger.debug(f"   Error accessing dimensionality: {dim_err}")
            
            try:
                sample_col = self.client.get_collection(name=self.collection.name)
                ef = getattr(sample_col, '_embedding_function', None)
                logger.debug(f"🔍 Type of collection._embedding_function: {type(ef)} value: {ef}")
                if isinstance(ef, dict):
                    logger.debug(f"   ⚠️ collection._embedding_function is a dict with keys: {list(ef.keys()) if ef else 'None'}")
            except Exception as err:
                logger.debug(f"Could not inspect collection._embedding_function: {err}")
            
            try:
                # Create vectorstore with explicit embedding_function
                # This prevents LangChain from trying to read embedding_function from collection metadata
                logger.debug(f"🔍 Creating LangChainChroma with collection_name='{self.collection.name}' and embedding_function={type(langchain_embeddings)}")
                vectorstore = LangChainChroma(
                    client=self.client,
                    collection_name=self.collection.name,
                    embedding_function=langchain_embeddings  # CRITICAL: Always pass this explicitly
                )
                logger.debug(f"✅ LangChainChroma created successfully")
                
                # Verify embeddings were set correctly
                if not hasattr(vectorstore, 'embeddings') or vectorstore.embeddings is None:
                    logger.warning("⚠️ LangChainChroma.embeddings is None, setting it explicitly")
                    vectorstore.embeddings = langchain_embeddings
                elif isinstance(vectorstore.embeddings, dict):
                    # If it's a dict (read from metadata), replace it immediately
                    logger.warning("⚠️ LangChainChroma.embeddings is a dict! Replacing with our embeddings")
                    vectorstore.embeddings = langchain_embeddings
                elif vectorstore.embeddings != langchain_embeddings:
                    # If it's different, replace it
                    logger.warning("⚠️ LangChainChroma.embeddings differs from our embeddings, replacing it")
                    vectorstore.embeddings = langchain_embeddings
                
                # Also check _embedding_function attribute
                if hasattr(vectorstore, '_embedding_function'):
                    if isinstance(vectorstore._embedding_function, dict):
                        logger.warning("⚠️ LangChainChroma._embedding_function is a dict! Replacing with our embeddings")
                        vectorstore._embedding_function = langchain_embeddings
                    elif vectorstore._embedding_function is None:
                        logger.debug("⚠️ LangChainChroma._embedding_function is None, setting it")
                        vectorstore._embedding_function = langchain_embeddings
                    
            except (AttributeError, TypeError, KeyError) as e1:
                error_msg = str(e1)
                if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                    logger.warning(f"⚠️ Failed to create MMR retriever from existing collection: {e1}")
                    logger.warning("   This is due to ChromaDB/LangChain compatibility issue")
                    logger.warning("   MMR retriever will not be available - use mmr_select_from_chunks instead")
                    raise ValueError(f"Cannot create MMR retriever from existing collection due to compatibility issue: {error_msg}")
                raise
            
            # Create MMR retriever - wrap in try-catch to handle dimensionality errors during retriever creation
            try:
                retriever = vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "fetch_k": fetch_k,
                        "k": k,
                        "lambda_mult": lambda_mult
                    }
                )
            except AttributeError as retriever_attr_error:
                error_msg = str(retriever_attr_error).lower()
                if "dimensionality" in error_msg or ("dict" in error_msg and "attribute" in error_msg):
                    logger.error(f"❌ Failed to create retriever due to dimensionality error: {retriever_attr_error}")
                    logger.error("   This happens when LangChain tries to access dimensionality during retriever creation")
                    logger.warning("   MMR retriever will not be available - use mmr_select_from_chunks instead")
                    raise ValueError(f"Cannot create MMR retriever: ChromaDB/LangChain compatibility issue - {str(retriever_attr_error)}")
                raise
            
            logger.info(f"✅ Created MMR retriever: fetch_k={fetch_k}, k={k}, lambda_mult={lambda_mult}")
            return retriever
            
        except AttributeError as ae:
            # Specifically catch dimensionality attribute errors
            error_msg = str(ae).lower()
            if "dimensionality" in error_msg or ("dict" in error_msg and "attribute" in error_msg):
                logger.error(f"❌ Failed to create MMR retriever due to dimensionality error: {ae}")
                raise ValueError(f"Cannot create MMR retriever: ChromaDB/LangChain compatibility issue - {str(ae)}")
            raise  # Re-raise if it's a different AttributeError
        except Exception as e:
            error_msg = str(e).lower()
            if "dimensionality" in error_msg or ("dict" in error_msg and "attribute" in error_msg):
                logger.error(f"❌ Failed to create MMR retriever due to dimensionality error: {e}")
                raise ValueError(f"Cannot create MMR retriever: ChromaDB/LangChain compatibility issue - {str(e)}")
            logger.error(f"❌ Failed to create MMR retriever: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create MMR retriever: {str(e)}"
            )

    def query_documents_mmr(self, query_text: str, fetch_k: int = 50, k: int = 10, 
                           lambda_mult: float = 0.65,
                           filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query documents using MMR (Maximum Marginal Relevance) retriever.
        
        This method provides better diversity in results compared to standard similarity search.
        
        Uses FAISS-based MMR internally (via mmr_select_from_chunks) to avoid ChromaDB/LangChain
        compatibility issues with persistent collections.
        
        Args:
            query_text: Text to search for
            fetch_k: Number of documents to fetch before applying MMR (default: 50)
            k: Number of documents to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
                        Default 0.65 balances factual grounding + variety for UPSC Qs
            filter_metadata: Optional dict to filter by metadata fields (applied before MMR)
        
        Returns:
            List of document chunks with content, metadata, and distance
        """
        # NUCLEAR OPTION: Skip LangChainChroma entirely and always use FAISS-based MMR
        # This avoids all ChromaDB/LangChain compatibility issues
        # Set to True to force FAISS-only MMR (recommended if errors persist)
        FORCE_FAISS_ONLY = True  # Enabled: bypass LangChainChroma completely, use FAISS-based MMR
        
        if FORCE_FAISS_ONLY:
            logger.info("🔄 Using FAISS-only MMR (LangChainChroma bypassed)")
            return self._query_documents_mmr_faiss_only(query_text, fetch_k, k, lambda_mult, filter_metadata)
        
        try:
            # Try to use LangChain MMR retriever first (for backward compatibility)
            # But if it fails, we'll fall back to FAISS-based MMR
            try:
                retriever = self.get_mmr_retriever(fetch_k=fetch_k, k=k, lambda_mult=lambda_mult)
                # If we got a retriever, use it
                docs = retriever.get_relevant_documents(query_text)
                
                # Format results
                formatted_results = []
                for doc in docs:
                    chunk = {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "distance": 0.0  # MMR doesn't return distances
                    }
                    
                    # Apply metadata filtering if specified
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
                
            except (ValueError, AttributeError) as ve:
                # If LangChain/Chroma compatibility issue detected, fallback to FAISS-based MMR
                msg = str(ve).lower()
                if "dimensionality" in msg or "compatibility" in msg or "embedding" in msg or ("dict" in msg and "attribute" in msg):
                    logger.warning(f"⚠️ LangChain/Chroma MMR not available: {ve}")
                    logger.info("   Falling back to FAISS-based MMR selection")
                    # Fallback to FAISS-based MMR: fetch candidate chunks then call mmr_select_from_chunks
                    candidate_chunks = self.query_documents(query_text, k=fetch_k, filter_metadata=filter_metadata)
                    if not candidate_chunks:
                        logger.warning("⚠️ No documents found for MMR selection")
                        return []
                    return self.mmr_select_from_chunks(candidate_chunks, query_text, k=k, lambda_mult=lambda_mult)
                raise  # Re-raise if it's a different ValueError/AttributeError
            
        except AttributeError as ae:
            # Catch the '.dimensionality' attribute errors explicitly and fallback
            error_msg = str(ae).lower()
            if "dimensionality" in error_msg or ("dict" in error_msg and "attribute" in error_msg):
                logger.warning(f"⚠️ AttributeError during MMR creation: {ae}. Falling back to FAISS-based MMR.")
                candidate_chunks = self.query_documents(query_text, k=fetch_k, filter_metadata=filter_metadata)
                if not candidate_chunks:
                    return []
                return self.mmr_select_from_chunks(candidate_chunks, query_text, k=k, lambda_mult=lambda_mult)
            raise  # Re-raise if it's a different AttributeError
        except Exception as e:
            logger.error(f"❌ MMR query failed (final): {e} - falling back to standard query")
            # Fallback to standard query if MMR fails
            logger.warning("⚠️ Falling back to standard similarity search")
            return self.query_documents(query_text, k=k, filter_metadata=filter_metadata)
    
    def _query_documents_mmr_faiss_only(self, query_text: str, fetch_k: int = 50, k: int = 10,
                                       lambda_mult: float = 0.65,
                                       filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        FAISS-only MMR implementation - bypasses LangChainChroma entirely.
        Use this if LangChainChroma compatibility issues persist.
        """
        logger.info("🔄 Using FAISS-only MMR (bypassing LangChainChroma)")
        # Step 1: Query initial set of documents
        initial_chunks = self.query_documents(
            query_text=query_text,
            k=fetch_k,
            filter_metadata=filter_metadata
        )
        
        if not initial_chunks:
            logger.warning("⚠️ No documents found for MMR selection")
            return []
        
        # Step 2: Apply MMR diversity selection using FAISS
        diverse_chunks = self.mmr_select_from_chunks(
            chunks=initial_chunks,
            query_text=query_text,
            k=k,
            lambda_mult=lambda_mult
        )
        
        logger.info(f"✅ FAISS MMR retrieval: {len(initial_chunks)} candidates → {len(diverse_chunks)} diverse chunks")
        return diverse_chunks

    def mmr_select_from_chunks(self, chunks: List[Dict[str, Any]], query_text: str, 
                               k: int = 10, lambda_mult: float = 0.65) -> List[Dict[str, Any]]:
        """
        Apply MMR diversity selection to a combined list of chunks from multiple sources.
        
        This ensures cross-source diversity - getting a mix of different source types
        (e.g., PYQ style examples + factual content) in the final selection.
        
        Args:
            chunks: List of chunks to select from (already retrieved from multiple sources)
            query_text: Query text for MMR relevance calculation
            k: Number of chunks to return after MMR (default: 10)
            lambda_mult: Diversity parameter (0.0 = max diversity, 1.0 = max relevance)
                        Default 0.65 balances factual grounding + variety
        
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
        
        # Wrap entire MMR operation in try-catch to handle dimensionality errors gracefully
        try:
            from langchain_core.documents import Document
            
            # Convert chunks to LangChain Documents
            documents = []
            for chunk in chunks:
                doc = Document(
                    page_content=chunk.get("content", ""),
                    metadata=chunk.get("metadata", {})
                )
                documents.append(doc)
            
            # Create temporary vectorstore from these documents
            # We'll use the existing embedder to create embeddings
            class ChromaEmbeddings(Embeddings):
                """Wrapper to make our embedder compatible with LangChain"""
                def __init__(self, embedder):
                    self.embedder = embedder
                    # Determine dimensionality by actually generating a test embedding
                    # This ensures accuracy regardless of which embedder is used
                    try:
                        # Generate a test embedding to determine actual dimension
                        test_embedding = embedder.get_embeddings(["test"])[0]
                        # Set as regular attribute (not property) for LangChain compatibility
                        self.dimensionality = len(test_embedding)
                        logger.debug(f"✅ Detected embedding dimensionality: {self.dimensionality}")
                    except Exception as dim_error:
                        # Fallback to expected dimensions based on embedder availability
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
            
            langchain_embeddings = ChromaEmbeddings(self.embedder)
            
            # Verify dimensionality is set correctly before proceeding
            if not hasattr(langchain_embeddings, 'dimensionality'):
                logger.error("❌ ChromaEmbeddings missing dimensionality attribute!")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            
            # Ensure dimensionality is a regular attribute (not property) and is an integer
            try:
                dim_value = langchain_embeddings.dimensionality
                if not isinstance(dim_value, int):
                    logger.warning(f"⚠️ Dimensionality is not an integer: {type(dim_value)}, fixing...")
                    # Re-detect dimensionality
                    test_emb = langchain_embeddings.embed_query("test")
                    langchain_embeddings.dimensionality = len(test_emb)
                    logger.debug(f"   Fixed dimensionality to {langchain_embeddings.dimensionality}")
            except Exception as dim_check_error:
                logger.error(f"❌ Error checking dimensionality: {dim_check_error}")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            
            # Create a temporary in-memory vectorstore
            # Use FAISS only (avoid ChromaDB due to dimensionality compatibility issues)
            vectorstore = None
            try:
                from langchain_community.vectorstores import FAISS
                
                # DEBUG: Verify embeddings before FAISS creation
                logger.debug(f"🔍 [mmr_select_from_chunks] Type of langchain_embeddings: {type(langchain_embeddings)}")
                logger.debug(f"   Has dimensionality? {hasattr(langchain_embeddings, 'dimensionality')}")
                if hasattr(langchain_embeddings, 'dimensionality'):
                    try:
                        dim_val = langchain_embeddings.dimensionality
                        logger.debug(f"   dimensionality value: {dim_val} (type: {type(dim_val)})")
                    except Exception as dim_err:
                        logger.error(f"   ❌ Error accessing dimensionality: {dim_err}")
                        import random
                        return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
                
                # Wrap FAISS creation in try-catch to handle dimensionality errors
                try:
                    logger.debug(f"🔍 [mmr_select_from_chunks] Creating FAISS vectorstore with {len(documents)} documents")
                    vectorstore = FAISS.from_documents(documents, langchain_embeddings)
                    logger.debug("✅ Created temporary FAISS vectorstore for MMR")
                except AttributeError as attr_err:
                    error_msg = str(attr_err)
                    if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                        logger.error(f"❌ FAISS creation failed due to dimensionality error: {attr_err}")
                        logger.error("   LangChain/FAISS tried to access dimensionality on a dict object")
                        logger.warning("   Falling back to random sampling without MMR")
                        import random
                        return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
                    raise  # Re-raise if it's a different AttributeError
            except ImportError:
                logger.warning("⚠️ FAISS not available - cannot create temporary vectorstore for MMR")
                logger.warning("   Falling back to random sampling without MMR")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            except Exception as faiss_error:
                error_msg = str(faiss_error)
                logger.error(f"❌ Failed to create FAISS vectorstore: {faiss_error}")
                # Check for dimensionality or compatibility issues
                if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                    logger.error("   Dimensionality/compatibility issue detected - falling back to random sampling")
                else:
                    logger.error("   Unknown error - falling back to random sampling")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            
            # Ensure vectorstore was created successfully
            if vectorstore is None:
                logger.error("❌ Failed to create vectorstore, falling back to random sampling")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            
            # Verify embedding function has dimensionality attribute before creating retriever
            try:
                if hasattr(vectorstore, 'embeddings') and vectorstore.embeddings:
                    if not hasattr(vectorstore.embeddings, 'dimensionality'):
                        logger.warning("⚠️ Embedding function missing dimensionality attribute, setting it...")
                        # Try to detect and set dimensionality
                        test_emb = vectorstore.embeddings.embed_query("test")
                        vectorstore.embeddings.dimensionality = len(test_emb)
                        logger.debug(f"   Set dimensionality to {vectorstore.embeddings.dimensionality}")
                elif hasattr(vectorstore, '_embedding_function') and vectorstore._embedding_function:
                    if not hasattr(vectorstore._embedding_function, 'dimensionality'):
                        logger.warning("⚠️ Embedding function missing dimensionality attribute, setting it...")
                        test_emb = vectorstore._embedding_function.embed_query("test")
                        vectorstore._embedding_function.dimensionality = len(test_emb)
                        logger.debug(f"   Set dimensionality to {vectorstore._embedding_function.dimensionality}")
            except Exception as verify_error:
                logger.warning(f"⚠️ Could not verify/set dimensionality: {verify_error}")
                # Continue anyway - might still work
            
            # Create MMR retriever
            try:
                retriever = vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "fetch_k": min(len(chunks), 50),  # Don't fetch more than available
                        "k": k,
                        "lambda_mult": lambda_mult
                    }
                )
                
                # Retrieve diverse chunks
                diverse_docs = retriever.get_relevant_documents(query_text)
            except Exception as retriever_error:
                error_msg = str(retriever_error)
                logger.error(f"❌ Failed to create/use MMR retriever: {retriever_error}")
                # Check for dimensionality or compatibility issues
                if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                    logger.error("   Dimensionality/compatibility issue detected - falling back to random sampling")
                else:
                    logger.error("   Unknown error - falling back to random sampling")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            
            # Recommendation #4: Fallback if MMR returns < k results
            if len(diverse_docs) < k:
                logger.warning(f"⚠️ MMR returned only {len(diverse_docs)} chunks (requested {k}), using fallback")
                # Fallback: randomly sample from original chunks to reach k
                import random
                if len(chunks) >= k:
                    # Use MMR results + random sample from remaining chunks
                    diverse_docs_set = {doc.page_content for doc in diverse_docs}
                    remaining_chunks = [c for c in chunks if c.get("content") not in diverse_docs_set]
                    needed = k - len(diverse_docs)
                    if remaining_chunks:
                        sampled = random.sample(remaining_chunks, min(needed, len(remaining_chunks)))
                        # Convert sampled chunks to Document format
                        for chunk in sampled:
                            doc = Document(
                                page_content=chunk.get("content", ""),
                                metadata=chunk.get("metadata", {})
                            )
                            diverse_docs.append(doc)
                else:
                    # Not enough chunks available, use all we have
                    logger.warning(f"⚠️ Only {len(chunks)} chunks available, returning all")
                    diverse_docs = documents[:k]
            
            # Convert back to our chunk format
            diverse_chunks = []
            for doc in diverse_docs:
                chunk = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "distance": 0.0
                }
                diverse_chunks.append(chunk)
            
            # Cleanup temporary collection if we used ChromaDB
            try:
                if hasattr(vectorstore, 'collection_name') and 'temp_mmr' in vectorstore.collection_name:
                    self.client.delete_collection(vectorstore.collection_name)
                    logger.debug(f"🧹 Cleaned up temporary collection: {vectorstore.collection_name}")
            except Exception as cleanup_error:
                logger.debug(f"Could not cleanup temporary collection: {cleanup_error}")
            
            logger.info(f"✅ MMR selection: {len(chunks)} chunks → {len(diverse_chunks)} diverse chunks")
            return diverse_chunks
            
        except AttributeError as attr_error:
            error_msg = str(attr_error)
            # Specifically catch 'dict' object has no attribute 'dimensionality'
            if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                logger.error(f"❌ MMR selection failed due to dimensionality error: {attr_error}")
                logger.error("   This is a LangChain/FAISS compatibility issue with embedding function")
                logger.error(f"   Full error: {type(attr_error).__name__}: {attr_error}")
                import traceback
                logger.error(f"   Stack trace:\n{traceback.format_exc()}")
                logger.warning("   Falling back to random sampling without MMR")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            # Re-raise if it's a different AttributeError
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ MMR selection failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            import traceback
            logger.error(f"   Stack trace:\n{traceback.format_exc()}")
            # Check if it's the dimensionality error
            if "dimensionality" in error_msg or ("dict" in error_msg.lower() and "attribute" in error_msg.lower()):
                logger.error("   This is a ChromaDB/LangChain compatibility issue with embedding function")
                logger.warning("   Falling back to random sampling without MMR")
                import random
                return random.sample(chunks, min(k, len(chunks))) if len(chunks) >= k else chunks
            logger.warning("⚠️ Falling back to first k chunks")
            return chunks[:k]