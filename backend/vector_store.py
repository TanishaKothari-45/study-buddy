"""
Vector store operations using ChromaDB
"""

import os
import json
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import numpy as np

class VectorStore:
    """ChromaDB wrapper for document storage and retrieval"""

    def __init__(self, persist_directory: str = "../embeddings/chroma_db"):
        """Initialize ChromaDB client and embedding model"""
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )

        # Initialize embedding model (lazy loading)
        self.embedding_model = None

        # Create or get collections
        self.documents_collection = self.client.get_or_create_collection(
            name="study_documents",
            metadata={"description": "UPSC study materials, PYQs, and current affairs"}
        )

    def _init_embedding_model(self):
        """Initialize the embedding model if not already done"""
        if self.embedding_model is None:
            print("Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("Embedding model loaded successfully")

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        collection_name: str = "study_documents"
    ) -> bool:
        """
        Add documents to the vector store

        Args:
            documents: List of text chunks
            metadatas: List of metadata dictionaries for each chunk
            ids: List of unique IDs for each chunk
            collection_name: Name of the collection to add to

        Returns:
            bool: True if successful
        """
        try:
            collection = self.client.get_or_create_collection(name=collection_name)

            # Initialize embedding model if needed
            self._init_embedding_model()

            # Generate embeddings
            embeddings = self.embedding_model.encode(documents).tolist()

            # Add to collection
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )

            return True

        except Exception as e:
            print(f"Error adding documents to vector store: {e}")
            return False

    def search_documents(
        self,
        query: str,
        top_k: int = 5,
        collection_name: str = "study_documents",
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search for relevant documents

        Args:
            query: Search query
            top_k: Number of results to return
            collection_name: Collection to search in
            where: Metadata filters

        Returns:
            Dict containing documents, metadatas, and distances
        """
        try:
            collection = self.client.get_or_create_collection(name=collection_name)

            # Initialize embedding model if needed
            self._init_embedding_model()

            # Generate query embedding
            query_embedding = self.embedding_model.encode([query]).tolist()[0]

            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"]
            )

            return results

        except Exception as e:
            print(f"Error searching documents: {e}")
            return {"documents": [], "metadatas": [], "distances": []}

    def delete_documents(
        self,
        where: Dict[str, Any],
        collection_name: str = "study_documents"
    ) -> bool:
        """
        Delete documents based on metadata filters

        Args:
            where: Metadata filters for deletion
            collection_name: Collection to delete from

        Returns:
            bool: True if successful
        """
        try:
            collection = self.client.get_or_create_collection(name=collection_name)
            collection.delete(where=where)
            return True

        except Exception as e:
            print(f"Error deleting documents: {e}")
            return False

    def get_collection_stats(self, collection_name: str = "study_documents") -> Dict[str, Any]:
        """
        Get statistics about a collection

        Args:
            collection_name: Name of the collection

        Returns:
            Dict with collection statistics
        """
        try:
            collection = self.client.get_or_create_collection(name=collection_name)
            count = collection.count()

            # Get sample metadata to understand document types
            if count > 0:
                sample = collection.get(limit=1, include=["metadatas"])
                doc_types = {}
                if sample["metadatas"]:
                    for metadata in sample["metadatas"]:
                        doc_type = metadata.get("document_type", "unknown")
                        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
            else:
                doc_types = {}

            return {
                "total_documents": count,
                "document_types": doc_types,
                "collection_name": collection_name
            }

        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {"error": str(e)}

    def list_collections(self) -> List[str]:
        """List all collections in the vector store"""
        try:
            return [collection.name for collection in self.client.list_collections()]
        except Exception as e:
            print(f"Error listing collections: {e}")
            return []

# Global vector store instance
vector_store = VectorStore()

def get_vector_store() -> VectorStore:
    """Get the global vector store instance"""
    return vector_store
