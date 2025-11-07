#!/usr/bin/env python3
"""
Script to fix mixed embedding dimensions in ChromaDB collection.
Removes chunks with wrong dimension and provides instructions for re-uploading.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).resolve().parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add backend to path
sys.path.insert(0, str(project_root / "backend"))

# Fix import path
import sys
import os
backend_path = str(project_root / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Change to backend directory to fix imports
os.chdir(project_root / "backend")

from app.utils.chroma_handler import ChromaHandler

def analyze_collection_dimensions():
    """Analyze collection to find chunks with different dimensions"""
    chroma = ChromaHandler()
    chroma.switch_to_collection("geography_docs_enriched")
    
    print("🔍 Analyzing collection dimensions...")
    
    try:
        # Get collection count
        total_count = chroma.collection.count()
        print(f"📊 Total chunks in collection: {total_count}")
        
        # Get a sample to check dimensions
        sample = chroma.collection.get(limit=min(100, total_count), include=['embeddings', 'metadatas'])
        
        if not sample.get('embeddings') or not sample['embeddings']:
            print("⚠️ Could not retrieve embeddings. Collection may be empty.")
            return None
        
        # Check dimensions
        dimensions = {}
        txt_filenames = set()
        pdf_filenames = set()
        
        for i, emb in enumerate(sample['embeddings']):
            if emb:  # Check if embedding exists
                dim = len(emb)
                if dim not in dimensions:
                    dimensions[dim] = []
                dimensions[dim].append(i)
                
                # Check filename
                if i < len(sample.get('metadatas', [])):
                    filename = sample['metadatas'][i].get('filename', '')
                    if filename.lower().endswith('.txt'):
                        txt_filenames.add(filename)
                    elif filename.lower().endswith('.pdf'):
                        pdf_filenames.add(filename)
        
        print(f"\n📏 Found embedding dimensions:")
        for dim, indices in dimensions.items():
            print(f"   • {dim} dimensions: {len(indices)} chunks (in sample)")
            if dim == 384:
                print(f"     ⚠️ These are Sentence Transformers embeddings")
            elif dim == 1536:
                print(f"     ✅ These are OpenAI embeddings")
        
        print(f"\n📁 Files found in sample:")
        print(f"   • TXT files: {len(txt_filenames)}")
        for fname in txt_filenames:
            print(f"     - {fname}")
        print(f"   • PDF files: {len(pdf_filenames)}")
        
        # If we have mixed dimensions, TXT files are likely 384-dim
        if 384 in dimensions and 1536 in dimensions:
            print(f"\n❌ MIXED DIMENSIONS DETECTED!")
            print(f"   • Collection has both 384-dim and 1536-dim embeddings")
            print(f"   • This will cause retrieval problems!")
            print(f"\n💡 Solution:")
            print(f"   1. Delete TXT file chunks (likely 384-dim)")
            print(f"   2. Re-upload TXT files with OpenAI API key set")
            print(f"   3. This will create 1536-dim embeddings matching your PDFs")
            
            return {
                'has_mixed': True,
                'txt_filenames': list(txt_filenames),
                'total_chunks': total_count
            }
        else:
            dim = list(dimensions.keys())[0] if dimensions else None
            print(f"\n✅ Collection has consistent dimensions: {dim}")
            return {
                'has_mixed': False,
                'dimension': dim,
                'total_chunks': total_count
            }
            
    except Exception as e:
        print(f"❌ Error analyzing collection: {e}")
        import traceback
        traceback.print_exc()
        return None

def delete_txt_chunks(txt_filenames):
    """Delete chunks from TXT files (likely 384-dim)"""
    chroma = ChromaHandler()
    chroma.switch_to_collection("geography_docs_enriched")
    
    print("\n🗑️  Finding TXT file chunks to delete...")
    
    # Use ChromaDB's query to find chunks by filename
    txt_chunk_ids = []
    
    for filename in txt_filenames:
        try:
            # Query for chunks with this filename
            # We'll get all chunks and filter by metadata
            results = chroma.collection.get(
                where={"filename": {"$contains": filename}},
                include=['metadatas']
            )
            
            if results and results.get('ids'):
                txt_chunk_ids.extend(results['ids'])
                print(f"   Found {len(results['ids'])} chunks from {filename}")
        except Exception as e:
            print(f"   ⚠️ Could not query for {filename}: {e}")
            # Try alternative: get all and filter
            try:
                all_results = chroma.collection.get(include=['metadatas'])
                if all_results and all_results.get('ids'):
                    for i, meta in enumerate(all_results.get('metadatas', [])):
                        if meta and meta.get('filename', '').lower().endswith('.txt'):
                            if all_results['ids'][i] not in txt_chunk_ids:
                                txt_chunk_ids.append(all_results['ids'][i])
            except Exception as e2:
                print(f"   ❌ Alternative method also failed: {e2}")
    
    if not txt_chunk_ids:
        print("✅ No TXT file chunks found. Collection may already be clean.")
        return
    
    print(f"\n📋 Found {len(txt_chunk_ids)} chunks from TXT files total")
    
    # Confirm deletion
    response = input(f"\n⚠️  Delete {len(txt_chunk_ids)} TXT file chunks? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled. No chunks deleted.")
        return
    
    # Delete chunks in batches
    try:
        batch_size = 100
        deleted = 0
        for i in range(0, len(txt_chunk_ids), batch_size):
            batch = txt_chunk_ids[i:i+batch_size]
            chroma.collection.delete(ids=batch)
            deleted += len(batch)
            print(f"   Deleted batch: {deleted}/{len(txt_chunk_ids)}")
        
        print(f"\n✅ Successfully deleted {deleted} TXT file chunks")
        print(f"\n📝 Next steps:")
        print(f"   1. Make sure OPENAI_API_KEY is set in your .env file")
        print(f"   2. Re-upload your TXT files")
        print(f"   3. They will be embedded with 1536-dim (OpenAI) to match your PDFs")
        print(f"   4. Chunks are now limited to 2500 words max to prevent token limit errors")
    except Exception as e:
        print(f"❌ Error deleting chunks: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🔧 ChromaDB Dimension Fixer")
    print("=" * 80)
    
    result = analyze_collection_dimensions()
    
    if result and result.get('has_mixed'):
        print("\n" + "=" * 80)
        txt_filenames = result.get('txt_filenames', [])
        if txt_filenames:
            delete_txt_chunks(txt_filenames)
        else:
            print("⚠️ Could not identify TXT filenames. You may need to manually delete chunks.")
    elif result and not result.get('has_mixed'):
        print("\n✅ Collection is already consistent!")
        print(f"   All chunks use {result.get('dimension')}-dim embeddings")
    
    print("\n" + "=" * 80)

