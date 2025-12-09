"""
Simple script to export chunks from ChromaDB
"""
import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.core.env import load_env_vars
from backend.app.core.config import settings
from backend.app.utils.chroma_handler import ChromaHandler
from migrate_chroma_to_pinecone import export_from_chroma

# Load environment variables
load_env_vars()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Export chunks from ChromaDB"""
    # Use geography_docs_enriched collection
    chroma_collection_name = "geography_docs_enriched"
    
    logger.info(f"📦 Exporting chunks from ChromaDB collection: {chroma_collection_name}")
    
    # Initialize ChromaDB handler
    chroma_handler = ChromaHandler()
    
    # Stage 1: Export from Chroma
    exported_chunks = export_from_chroma(chroma_handler, chroma_collection_name)
    
    if not exported_chunks:
        logger.warning("⚠️ No chunks exported")
        return
    
    logger.info(f"\n✅ Export complete!")
    logger.info(f"   • Total chunks exported: {len(exported_chunks)}")
    
    # Show sample chunk structure
    if exported_chunks:
        logger.info(f"\n📋 Sample chunk structure:")
        sample = exported_chunks[0]
        logger.info(f"   • ID: {sample['id'][:50]}...")
        logger.info(f"   • Content length: {len(sample['content'])} chars")
        logger.info(f"   • Content preview: {sample['content'][:100]}...")
        logger.info(f"   • Metadata keys: {list(sample['metadata'].keys())}")
        logger.info(f"   • Metadata sample: {json.dumps({k: str(v)[:50] for k, v in list(sample['metadata'].items())[:3]}, indent=2)}")
    
    # Optionally save to JSON file
    output_file = "exported_chunks.json"
    logger.info(f"\n💾 Saving exported chunks to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(exported_chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Saved {len(exported_chunks)} chunks to {output_file}")
    
    return exported_chunks

if __name__ == "__main__":
    main()

