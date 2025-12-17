import os
import logging
from pinecone import Pinecone
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "study-buddy")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY not set")

def migrate_pyq_metadata():
    """
    Migrate existing PYQ chunks in Pinecone:
    - Set source_subtype = "prelims" for all chunks where source_type="pyq" AND source_subtype is missing/null.
    """
    logger.info(f"Connecting to Pinecone index: {INDEX_NAME}")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    
    # 1. Fetch all PYQ vectors (using filter)
    # Note: query() with filter but dummy vector is one way, or iteration if supported.
    # Ideally, we should iterate. For now, let's assume we can fetch via empty query or iterate.
    # Pinecone list/pagination is best for bulk updates.
    
    # Actually, Pinecone doesn't support "update by query". We must fetch IDs then update.
    # Efficient way: list_paginated (if available) or query with vector of zeros.
    
    logger.info("Fetching existing PYQ vectors...")
    
    # Using a dummy zero vector to find "pyq" docs
    # Using specific namespace if you have one. Assuming default namespace.
    
    # Note: To update metadata, we need IDs. 
    # Since we can't easily iterate ALL, we'll try to find them via query if dataset is small (<10k),
    # or use `list` if valid. 
    
    matches_to_update = []
    
    # Try fetching via query (limit 10000)
    # Create a dummy vector of correct dimension (assuming 1536 for OpenAI)
    dummy_vector = [0.0] * 1536 
    
    results = index.query(
        vector=dummy_vector,
        top_k=5000, # Adjust as needed
        filter={
            "source_type": {"$eq": "pyq"}
        },
        include_metadata=True
    )
    
    if not results.matches:
        logger.info("No 'pyq' vectors found.")
        return

    logger.info(f"Found {len(results.matches)} PYQ vectors.")
    
    # 2. Filter valid ones to update
    for match in results.matches:
        meta = match.metadata
        # Check if subtype is missing or None
        if "source_subtype" not in meta or meta["source_subtype"] == "None" or not meta["source_subtype"]:
            matches_to_update.append(match.id)
            
    logger.info(f"Found {len(matches_to_update)} vectors requiring update (missing source_subtype).")
            
    if not matches_to_update:
        logger.info("All PYQ vectors already have source_subtype.")
        return

    # 3. Update in batches
    batch_size = 100
    for i in tqdm(range(0, len(matches_to_update), batch_size)):
        batch_ids = matches_to_update[i:i+batch_size]
        
        # Prepare updates
        # update(id, set_metadata={...})
        for doc_id in batch_ids:
            index.update(
                id=doc_id,
                set_metadata={"source_subtype": "prelims"}  # Default migration value
            )
            
    logger.info("Migration complete.")

if __name__ == "__main__":
    migrate_pyq_metadata()
