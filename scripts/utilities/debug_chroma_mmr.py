#!/usr/bin/env python3
"""
Diagnostic script to identify ChromaDB/LangChain compatibility issues
Run this to see what's causing the 'dict' object has no attribute 'dimensionality' error
"""
import os
import sys
import logging
from pathlib import Path

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import chromadb
from chromadb.config import Settings

# Disable telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"

# Import settings
from backend.app.core.config import settings

DB_DIR = settings.DB_DIR
COLLECTION_NAME = settings.COLLECTION_NAME

print("=" * 80)
print("ChromaDB/LangChain Diagnostic Script")
print("=" * 80)
print(f"DB_DIR: {DB_DIR}")
print(f"COLLECTION_NAME: {COLLECTION_NAME}")
print()

client = chromadb.PersistentClient(
    path=str(DB_DIR),
    settings=Settings(anonymized_telemetry=False, allow_reset=True, is_persistent=True)
)

print("✅ Client created")
print(f"Client type: {type(client)}")
print()

try:
    col = client.get_collection(name=COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' retrieved")
except Exception as e:
    print(f"❌ GET_COLLECTION ERROR: {e}")
    print(f"   Error type: {type(e)}")
    raise

print(f"Collection object type: {type(col)}")
print(f"Collection name: {col.name}")
print()

print("Collection object inspection:")
print("-" * 80)
try:
    # Check for common attributes
    attrs_to_check = [
        "_embedding_function", 
        "embedding_function", 
        "metadata", 
        "name", 
        "count",
        "_client",
        "id"
    ]
    
    for att in attrs_to_check:
        has_attr = hasattr(col, att)
        print(f"  {att:30s} exists? {has_attr}", end="")
        if has_attr:
            try:
                val = getattr(col, att)
                val_type = type(val)
                print(f"  type: {val_type}")
                
                # If it's a dict or small object, try to show value
                if isinstance(val, dict):
                    print(f"    value (dict keys): {list(val.keys())[:10]}")
                    # Check if it has embedding_function inside
                    if "embedding_function" in val:
                        print(f"    → embedding_function in dict: {type(val['embedding_function'])}")
                        print(f"    → embedding_function value: {val['embedding_function']}")
                elif isinstance(val, (str, int, float, bool)) or val is None:
                    print(f"    value: {val}")
                elif hasattr(val, '__len__') and len(str(val)) < 200:
                    print(f"    value: {val}")
                else:
                    print(f"    value: <{val_type.__name__} object>")
            except Exception as e:
                print(f"    ERROR accessing value: {e}")
        else:
            print()
    
    # Try to get repr (might be too long)
    try:
        repr_str = repr(col)
        if len(repr_str) > 1000:
            print(f"\n  repr (first 500 chars): {repr_str[:500]}...")
        else:
            print(f"\n  repr: {repr_str}")
    except Exception as e:
        print(f"\n  Could not get repr: {e}")
        
except Exception as e:
    print(f"❌ Error introspecting collection: {e}")
    import traceback
    traceback.print_exc()

print()
print("Sample data inspection:")
print("-" * 80)
try:
    count = col.count()
    print(f"Collection count: {count}")
    
    if count > 0:
        sample = col.get(limit=1, include=['embeddings', 'documents', 'metadatas'])
        print(f"col.get() returned keys: {list(sample.keys())}")
        if 'ids' in sample:
            print(f"  ids: {sample['ids'][:5]}")  # Show first 5 IDs
        
        if 'embeddings' in sample:
            emb = sample['embeddings']
            print(f"  embeddings type: {type(emb)}")
            if emb and len(emb) > 0:
                print(f"  embeddings length: {len(emb)}")
                print(f"  example embedding type: {type(emb[0])}")
                if isinstance(emb[0], (list, tuple)):
                    print(f"  example embedding length: {len(emb[0])}")
                else:
                    print(f"  example embedding: {emb[0]}")
    else:
        print("  Collection is empty")
        
except Exception as e:
    print(f"❌ col.get() failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("LangChain compatibility check:")
print("-" * 80)
try:
    from langchain_community.vectorstores import Chroma as LangChainChroma
    from langchain_core.embeddings import Embeddings
    
    print("✅ LangChainChroma imported OK")
    
    # Try creating wrapper with collection_name only
    print("\n1. Testing LangChainChroma(client=client, collection_name=COLLECTION_NAME)...")
    try:
        v = LangChainChroma(client=client, collection_name=COLLECTION_NAME)
        print(f"   ✅ Created OK, type: {type(v)}")
        
        # Check what embedding function it has
        if hasattr(v, 'embeddings'):
            print(f"   v.embeddings type: {type(v.embeddings)}")
            if hasattr(v.embeddings, 'dimensionality'):
                print(f"   v.embeddings.dimensionality: {v.embeddings.dimensionality}")
            else:
                print(f"   ⚠️ v.embeddings missing dimensionality attribute")
        elif hasattr(v, '_embedding_function'):
            print(f"   v._embedding_function type: {type(v._embedding_function)}")
            if isinstance(v._embedding_function, dict):
                print(f"   ❌ PROBLEM FOUND: v._embedding_function is a dict!")
                print(f"      dict keys: {list(v._embedding_function.keys())}")
            elif hasattr(v._embedding_function, 'dimensionality'):
                print(f"   v._embedding_function.dimensionality: {v._embedding_function.dimensionality}")
            else:
                print(f"   ⚠️ v._embedding_function missing dimensionality attribute")
    except AttributeError as ae:
        error_msg = str(ae)
        print(f"   ❌ AttributeError: {error_msg}")
        if "dimensionality" in error_msg:
            print(f"   → This is the error we're trying to fix!")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    # Try creating wrapper with explicit embedding function
    print("\n2. Testing LangChainChroma with explicit embedding_function...")
    try:
        # Create a simple test embedding function
        class TestEmbeddings(Embeddings):
            def __init__(self):
                self.dimensionality = 1536  # OpenAI dimension
            def embed_documents(self, texts):
                return [[0.0] * self.dimensionality for _ in texts]
            def embed_query(self, text):
                return [0.0] * self.dimensionality
        
        test_emb = TestEmbeddings()
        v2 = LangChainChroma(
            client=client, 
            collection_name=COLLECTION_NAME,
            embedding_function=test_emb  # Explicitly pass embedding function
        )
        print(f"   ✅ Created OK with explicit embedding_function, type: {type(v2)}")
        print(f"   v2.embeddings type: {type(v2.embeddings)}")
        if v2.embeddings and hasattr(v2.embeddings, 'dimensionality'):
            print(f"   v2.embeddings.dimensionality: {v2.embeddings.dimensionality}")
        else:
            print(f"   ⚠️ v2.embeddings missing or no dimensionality")
    except AttributeError as ae:
        error_msg = str(ae)
        print(f"   ❌ AttributeError: {error_msg}")
        if "dimensionality" in error_msg:
            print(f"   → This is the error we're trying to fix!")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError as ie:
    print(f"❌ LangChainChroma import failed: {ie}")
    print("   Install with: pip install langchain-community langchain-core")

print()
print("=" * 80)
print("Diagnostic complete!")
print("=" * 80)
print("\nPlease share the full output above, especially any ❌ errors or ⚠️ warnings.")
print("This will help identify exactly where the dict is coming from.")

