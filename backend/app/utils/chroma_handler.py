"""
ChromaDB vector store handler
"""
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
try:
    from chromadb.errors import NotFoundError
except ImportError:
    # ChromaDB version compatibility - NotFoundError might not exist in older versions
    class NotFoundError(Exception):
        pass
from fastapi import HTTPException

from ..core.config import settings
from .embedder import Embedder

logger = logging.getLogger(__name__)

class ChromaHandler:
    def __init__(self):
        """Initialize ChromaDB client and collection"""
        # Initialize client with telemetry disabled
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
            self.collection = self.client.get_collection(name=settings.COLLECTION_NAME)
            logger.info(f"Found existing collection: {settings.COLLECTION_NAME}")
            
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

        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
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
            all_docs = []
            for offset in range(0, total_count, batch_size):
                results = self.collection.get(
                    include=['documents', 'metadatas'],
                    limit=batch_size,
                    offset=offset
                )
                for i in range(len(results['documents'])):
                    all_docs.append({
                        "id": results['ids'][i],
                        "content": results['documents'][i],
                        "metadata": results['metadatas'][i]
                    })
                logger.info(f"📦 Retrieved {len(all_docs)}/{total_count} so far...")
            return all_docs
        except Exception as e:
            logger.error(f"❌ Failed to fetch all documents in batches: {e}")
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
                                embeddings_len = len(embeddings)
                                if embeddings_len > 0:
                                    embedding_list = embeddings[0]
                                    # Handle numpy arrays - check length without truthiness check
                                    try:
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
                                    except (TypeError, ValueError) as len_error:
                                        logger.debug(f"Could not get embedding length: {len_error}")
                                        logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't determine dimension")
                                else:
                                    logger.info(f"📏 Collection '{collection_name}' has {count} chunks but couldn't retrieve embeddings")
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