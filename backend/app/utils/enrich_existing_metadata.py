"""
Batch metadata enrichment for existing ChromaDB documents
"""

import os
import sys
import logging
from pathlib import Path
from tqdm import tqdm
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).resolve().parent.parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.utils.metadata_enricher import enrich_metadata
from app.utils.chroma_handler import ChromaHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION_NAME = "geography_docs_enriched"  # Target collection
BATCH_SIZE = 50  # Process in batches

def enrich_existing_chunks():
    chroma = ChromaHandler()
    chroma.switch_to_collection(COLLECTION_NAME)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        return
    client = OpenAI(api_key=api_key)

    # Get all documents and filter for unenriched ones (incremental processing)
    all_docs = chroma.get_all_documents_paginated()
    docs = [
        d for d in all_docs
        if not d["metadata"].get("major_domain")
    ]
    logger.info(f"📚 Found {len(docs)} chunks missing enrichment (out of {len(all_docs)} total)")
    
    if not docs:
        logger.info("✅ All documents already enriched!")
        return

    enriched = []
    for i, doc in enumerate(tqdm(docs, desc="Enriching metadata")):
        try:
            text = doc["content"]
            filename = doc["metadata"].get("filename", "unknown")
            chapter = doc["metadata"].get("chapter", "unknown")
            section = doc["metadata"].get("section", "unknown")

            new_meta = enrich_metadata(text, filename, chapter, section, client)
            enriched.append({"id": doc["id"], "metadata": new_meta})

            if len(enriched) >= BATCH_SIZE:
                chroma.update_metadata_batch(enriched)
                enriched = []
        except Exception as e:
            logger.warning(f"⚠️ Error enriching chunk {i}: {e}")

    if enriched:
        chroma.update_metadata_batch(enriched)

    logger.info("✅ Metadata enrichment complete!")

if __name__ == "__main__":
    enrich_existing_chunks()
