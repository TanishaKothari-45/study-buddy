"""
ChromaDB vector store handler
"""
import logging
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings

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

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": settings.DISTANCE_METRIC}
        )

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

            # Generate embeddings
            embeddings = self.embedder.get_embeddings(documents)

            # Generate IDs
            ids = [f"doc_{i}_{hash(doc)}" for i, doc in enumerate(documents)]

            # Add to collection
            self.collection.add(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"✅ Added {len(documents)} chunks to ChromaDB")

        except Exception as e:
            logger.error(f"❌ Failed to add documents: {e}")
            raise

    def query_documents(self, query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Query for most relevant documents"""
        try:
            # Generate query embedding
            query_embedding = self.embedder.get_embeddings([query_text])[0]

            # Query collection
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=['documents', 'metadatas', 'distances']
            )

            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i]
                    })

            logger.info(f"✅ Found {len(formatted_results)} relevant chunks")
            return formatted_results

        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
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