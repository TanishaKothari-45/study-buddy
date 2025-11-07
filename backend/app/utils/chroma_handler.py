"""
ChromaDB vector store handler
"""
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

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

        # Check if collection exists
        try:
            self.collection = self.client.get_collection(name=settings.COLLECTION_NAME)
            logger.info(f"Found existing collection: {settings.COLLECTION_NAME}")
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

            # Generate embeddings
            embeddings = self.embedder.get_embeddings(filtered_documents)
            
            if not embeddings:
                logger.warning("⚠️ No embeddings generated, skipping add")
                return

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

            logger.info(f"✅ Added {len(filtered_documents)} chunks to ChromaDB")

        except Exception as e:
            error_msg = str(e)
            # Check if it's a dimension mismatch error
            if "dimension" in error_msg.lower() or "expecting embedding" in error_msg.lower():
                logger.warning(f"⚠️ Dimension mismatch detected. Resetting collection...")
                try:
                    collection_name = self.collection.name
                    self.client.delete_collection(collection_name)
                    self.collection = self.client.create_collection(
                        name=collection_name,
                        metadata={"hnsw:space": settings.DISTANCE_METRIC}
                    )
                    logger.info(f"✨ Collection reset, retrying add...")
                    # Retry once
                    self.collection.add(
                        embeddings=embeddings,
                        documents=filtered_documents,
                        metadatas=filtered_metadatas,
                        ids=ids
                    )
                    logger.info(f"✅ Added {len(filtered_documents)} chunks to ChromaDB after reset")
                except Exception as retry_error:
                    logger.error(f"❌ Failed to add documents after reset: {retry_error}")
                    raise
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
        except NotFoundError:
            logger.warning(f"Collection {collection_name} not found. Creating new one.")
            self.create_new_collection(collection_name)

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