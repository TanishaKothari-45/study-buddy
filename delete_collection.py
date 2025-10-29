#!/usr/bin/env python3
"""
Quick script to delete the geography_docs_enriched collection
"""
import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

# Paths to check (based on config.py, it should be backend/data/chroma)
DB_PATHS = ["backend/data/chroma", "data/chroma"]

collection_name = "geography_docs_enriched"

for db_path in DB_PATHS:
    try:
        print(f"\n🔍 Checking: {db_path}")
        client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
        )
        
        # List existing collections
        existing = client.list_collections()
        print(f"   Found collections: {[c.name for c in existing]}")
        
        if any(c.name == collection_name for c in existing):
            try:
                client.delete_collection(collection_name)
                print(f"   ✅ Successfully deleted collection: {collection_name}")
            except Exception as e:
                print(f"   ❌ Error deleting: {e}")
        else:
            print(f"   ℹ️  Collection '{collection_name}' not found in this location")
            
    except Exception as e:
        print(f"   ⚠️  Could not access {db_path}: {e}")
        continue

