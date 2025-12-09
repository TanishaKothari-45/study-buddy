#!/usr/bin/env python3
"""
Simple script to delete a ChromaDB collection
Usage: python3 delete_collection.py [collection_name]
If no collection name is provided, uses the default from settings
"""
import sys
import os

# Add backend directory to path (parent of scripts/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.chroma_handler import ChromaHandler
from app.core.config import settings

def main():
    # Get collection name from command line or use default
    if len(sys.argv) > 1:
        collection_name = sys.argv[1]
    else:
        collection_name = settings.COLLECTION_NAME
    
    print(f"🗑️  Deleting collection: {collection_name}")
    
    try:
        chroma_handler = ChromaHandler()
        chroma_handler.delete_collection(collection_name)
        print(f"✅ Successfully deleted collection: {collection_name}")
    except Exception as e:
        print(f"❌ Error deleting collection: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

