"""
Migration script to export chunks from ChromaDB and import to Pinecone
"""
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.core.env import load_env_vars
from backend.app.core.config import settings
from backend.app.utils.chroma_handler import ChromaHandler
from backend.app.utils.embedder import Embedder

# Load environment variables
load_env_vars()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def export_from_chroma(chroma_handler, chroma_collection_name: str = None):
    """
    Stage 1: Export all documents from ChromaDB collection.
    
    Args:
        chroma_handler: ChromaHandler instance
        chroma_collection_name: Name of ChromaDB collection to export from
    
    Returns:
        List of exported documents with id, content, and metadata
    """
    logger.info("📦 Stage 1: Exporting all documents from Chroma collection...")
    
    # Switch to the specified collection if provided
    if chroma_collection_name:
        chroma_handler.switch_to_collection(chroma_collection_name)
    
    # Get all documents using pagination
    all_docs = chroma_handler.get_all_documents_paginated()
    
    # Format exported documents
    exported = [
        {
            "id": d["id"],
            "content": d["content"],
            "metadata": d["metadata"]
        }
        for d in all_docs
    ]
    
    logger.info(f"✅ Exported {len(exported)} documents from Chroma.")
    
    if exported:
        logger.info(f"   • Sample document ID: {exported[0]['id'][:50]}...")
        logger.info(f"   • Sample content preview: {exported[0]['content'][:100]}...")
        logger.info(f"   • Sample metadata keys: {list(exported[0]['metadata'].keys())}")
    
    return exported

def initialize_pinecone(pinecone_api_key: str, index_name: str, dimension: int = None):
    """
    Stage 2: Initialize Pinecone client and index.
    
    Args:
        pinecone_api_key: Pinecone API key
        index_name: Name of the Pinecone index
        dimension: Embedding dimension (will be detected if not provided)
    
    Returns:
        Tuple of (Pinecone client, Pinecone index)
    """
    logger.info("🔧 Stage 2: Initializing Pinecone client and index...")
    
    try:
        from pinecone import Pinecone, ServerlessSpec
    except ImportError as e:
        logger.error(f"❌ Pinecone not installed: {e}")
        logger.error("   Please install: pip install pinecone-client")
        raise
    
    # Initialize Pinecone client
    pc = Pinecone(api_key=pinecone_api_key)
    logger.info("✅ Pinecone client initialized")
    
    # Check if index exists
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    
    if index_name not in existing_indexes:
        logger.info(f"📝 Creating new Pinecone index: {index_name}")
        
        # Determine dimension if not provided
        if dimension is None:
            embedder = Embedder()
            if embedder.openai_client:
                dimension = 1536  # OpenAI text-embedding-3-small
            else:
                dimension = 384  # Sentence Transformers
            logger.info(f"   • Auto-detected dimension: {dimension}")
        else:
            logger.info(f"   • Using provided dimension: {dimension}")
        
        # Create index
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        logger.info(f"✅ Created Pinecone index: {index_name}")
    else:
        logger.info(f"✅ Pinecone index already exists: {index_name}")
    
    # Get the index
    index = pc.Index(index_name)
    logger.info(f"✅ Connected to Pinecone index: {index_name}")
    
    return pc, index

def migrate_chroma_to_pinecone(
    chroma_collection_name: str = None,
    pinecone_index_name: str = None,
    batch_size: int = 100
):
    """
    Migrate all chunks from ChromaDB to Pinecone
    
    Args:
        chroma_collection_name: Name of ChromaDB collection to migrate from
        pinecone_index_name: Name of Pinecone index to migrate to
        batch_size: Number of chunks to process in each batch
    """
    try:
        # Import Pinecone
        try:
            from pinecone import Pinecone, ServerlessSpec
            from langchain_pinecone import PineconeVectorStore
        except ImportError as e:
            logger.error(f"❌ Pinecone not installed: {e}")
            logger.error("   Please install: pip install pinecone-client langchain-pinecone")
            return False
        
        # Get Pinecone API key
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            logger.error("❌ PINECONE_API_KEY not found in environment variables")
            logger.error("   Please set PINECONE_API_KEY in your .env file")
            return False
        
        # Use default collection name if not provided
        if not chroma_collection_name:
            chroma_collection_name = settings.COLLECTION_NAME
        
        if not pinecone_index_name:
            pinecone_index_name = chroma_collection_name.replace("_", "-").lower()
        
        logger.info(f"🔄 Starting migration from ChromaDB to Pinecone")
        logger.info(f"   • Source: ChromaDB collection '{chroma_collection_name}'")
        logger.info(f"   • Destination: Pinecone index '{pinecone_index_name}'")
        logger.info(f"   • Batch size: {batch_size}")
        
        # Initialize ChromaDB handler
        logger.info("📦 Connecting to ChromaDB...")
        chroma_handler = ChromaHandler()
        
        # Stage 1: Export from Chroma
        all_docs = export_from_chroma(chroma_handler, chroma_collection_name)
        total_chunks = len(all_docs)
        
        if total_chunks == 0:
            logger.warning("⚠️ No documents found in ChromaDB collection")
            return False
        
        # Stage 2: Initialize Pinecone
        pc, index = initialize_pinecone(pinecone_api_key, pinecone_index_name)
        
        # Initialize embedder for re-embedding (to ensure consistency)
        embedder = Embedder()
        
        # Initialize LangChain Pinecone for consistent storage format
        try:
            from langchain_pinecone import PineconeVectorStore
            from langchain_core.embeddings import Embeddings
            
            # Create embeddings wrapper
            class MigrationEmbeddings(Embeddings):
                def __init__(self, embedder):
                    self.embedder = embedder
                    test_emb = embedder.get_embeddings(["test"])[0]
                    self.dimensionality = len(test_emb)
                
                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    return self.embedder.get_embeddings(texts)
                
                def embed_query(self, text: str) -> List[float]:
                    return self.embedder.get_embeddings([text])[0]
            
            langchain_embeddings = MigrationEmbeddings(embedder)
            
            # Create or get vectorstore
            vectorstore = PineconeVectorStore(
                index_name=pinecone_index_name,
                embedding=langchain_embeddings,
                pinecone_api_key=pinecone_api_key
            )
            
            logger.info("✅ Using LangChain Pinecone for consistent storage format")
            
        except ImportError:
            logger.warning("⚠️ LangChain Pinecone not available, using raw Pinecone client")
            logger.warning("   This may cause compatibility issues - install langchain-pinecone")
            vectorstore = None
            index = pc.Index(pinecone_index_name)
        
        # Process chunks in batches
        logger.info(f"🚀 Starting batch upload to Pinecone...")
        uploaded_count = 0
        failed_count = 0
        
        for i in range(0, total_chunks, batch_size):
            batch = all_docs[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            logger.info(f"📤 Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
            
            try:
                if vectorstore:
                    # Use LangChain Pinecone for consistent format
                    from langchain_core.documents import Document
                    
                    # Convert to LangChain Documents
                    documents = []
                    for doc in batch:
                        # Flatten metadata for Pinecone
                        flat_metadata = {}
                        for key, value in doc['metadata'].items():
                            if isinstance(value, (str, int, float, bool)):
                                flat_metadata[key] = value
                            elif value is None:
                                continue
                            else:
                                flat_metadata[key] = str(value)
                        
                        # Store ID in metadata for reference
                        flat_metadata['id'] = doc['id']
                        
                        documents.append(Document(
                            page_content=doc['content'],
                            metadata=flat_metadata
                        ))
                    
                    # Add documents using LangChain
                    logger.info(f"   💾 Uploading batch {batch_num} to Pinecone via LangChain...")
                    vectorstore.add_documents(documents)
                    
                else:
                    # Fallback to raw Pinecone client
                    texts = [doc['content'] for doc in batch]
                    metadatas = [doc['metadata'] for doc in batch]
                    ids = [doc['id'] for doc in batch]
                    
                    # Generate embeddings
                    logger.info(f"   🔍 Generating embeddings for batch {batch_num}...")
                    if embedder.openai_client:
                        embeddings = embedder.get_openai_embeddings(texts)
                    else:
                        embeddings = embedder.get_sbert_embeddings(texts)
                    
                    # Prepare vectors for Pinecone
                    vectors = []
                    for j, (text_id, embedding, metadata) in enumerate(zip(ids, embeddings, metadatas)):
                        # Pinecone metadata must be flat
                        flat_metadata = {}
                        for key, value in metadata.items():
                            if isinstance(value, (str, int, float, bool)):
                                flat_metadata[key] = value
                            elif value is None:
                                continue
                            else:
                                flat_metadata[key] = str(value)
                        
                        vectors.append({
                            "id": text_id,
                            "values": embedding,
                            "metadata": flat_metadata
                        })
                    
                    # Upsert to Pinecone
                    logger.info(f"   💾 Uploading batch {batch_num} to Pinecone...")
                    index.upsert(vectors=vectors)
                
                uploaded_count += len(batch)
                logger.info(f"   ✅ Batch {batch_num} uploaded successfully ({uploaded_count}/{total_chunks})")
                
            except Exception as batch_error:
                logger.error(f"   ❌ Failed to upload batch {batch_num}: {batch_error}")
                failed_count += len(batch)
                import traceback
                logger.error(traceback.format_exc())
        
        # Verify migration
        logger.info(f"\n📊 Migration Summary:")
        logger.info(f"   • Total chunks in ChromaDB: {total_chunks}")
        logger.info(f"   • Successfully uploaded: {uploaded_count}")
        logger.info(f"   • Failed: {failed_count}")
        
        # Check Pinecone index stats
        try:
            index_for_stats = pc.Index(pinecone_index_name)
            stats = index_for_stats.describe_index_stats()
            logger.info(f"\n📈 Pinecone Index Stats:")
            logger.info(f"   • Total vectors: {stats.get('total_vector_count', 0)}")
            logger.info(f"   • Index name: {pinecone_index_name}")
        except Exception as stats_error:
            logger.warning(f"⚠️ Could not get Pinecone stats: {stats_error}")
        
        if uploaded_count == total_chunks:
            logger.info(f"\n✅ Migration completed successfully!")
            logger.info(f"   • All {uploaded_count} chunks migrated to Pinecone")
            logger.info(f"   • Index name: {pinecone_index_name}")
            return True
        else:
            logger.warning(f"\n⚠️ Migration completed with errors")
            logger.warning(f"   • Uploaded: {uploaded_count}/{total_chunks}")
            logger.warning(f"   • Failed: {failed_count}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate chunks from ChromaDB to Pinecone")
    parser.add_argument(
        "--chroma-collection",
        type=str,
        default=None,
        help="ChromaDB collection name (default: from settings)"
    )
    parser.add_argument(
        "--pinecone-index",
        type=str,
        default=None,
        help="Pinecone index name (default: chroma collection name)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for uploads (default: 100)"
    )
    
    args = parser.parse_args()
    
    success = migrate_chroma_to_pinecone(
        chroma_collection_name=args.chroma_collection,
        pinecone_index_name=args.pinecone_index,
        batch_size=args.batch_size
    )
    
    sys.exit(0 if success else 1)

