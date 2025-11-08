#!/usr/bin/env python3
"""
Delete chunks from the full PDF (Workbook_ September 2025.pdf) 
Keep only chunks from the extracted PDF (Workbook_ September 2025_geo_env.pdf)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).resolve().parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add backend to path
sys.path.insert(0, str(project_root / "backend"))
os.chdir(project_root / "backend")

from app.utils.chroma_handler import ChromaHandler

def main():
    print("=" * 80)
    print("🗑️  Delete Full PDF Chunks from ChromaDB")
    print("=" * 80)
    
    chroma = ChromaHandler()
    chroma.switch_to_collection("geography_docs_enriched")
    
    # Get total count
    total_count = chroma.collection.count()
    print(f"\n📊 Total chunks in collection: {total_count}")
    
    # Count chunks by filename
    try:
        all_docs = chroma.get_all_documents_paginated()
        filename_counts = {}
        for doc in all_docs:
            filename = doc.get('metadata', {}).get('filename', 'Unknown')
            filename_counts[filename] = filename_counts.get(filename, 0) + 1
        
        print(f"\n📋 Chunks by filename:")
        for filename, count in sorted(filename_counts.items()):
            print(f"   • {filename}: {count} chunks")
    except Exception as e:
        print(f"   ⚠️ Could not list chunks: {e}")
    
    # Delete chunks from full PDF
    full_pdf_filename = "Workbook_ September 2025.pdf"
    
    print(f"\n🗑️  Deleting chunks from full PDF:")
    print(f"   {full_pdf_filename}")
    print(f"\n   (Keeping chunks from extracted PDF: Workbook_ September 2025_geo_env.pdf)")
    
    # Confirm deletion
    response = input(f"\n⚠️  Delete all chunks from '{full_pdf_filename}'? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled. No chunks deleted.")
        return
    
    try:
        deleted_count = chroma.delete_documents_by_filename(full_pdf_filename)
        print(f"\n✅ Successfully deleted {deleted_count} chunks")
        
        # Verify
        new_count = chroma.collection.count()
        print(f"📊 Remaining chunks: {new_count}")
        
        # Show remaining chunks by filename
        try:
            all_docs = chroma.get_all_documents_paginated()
            filename_counts = {}
            for doc in all_docs:
                filename = doc.get('metadata', {}).get('filename', 'Unknown')
                filename_counts[filename] = filename_counts.get(filename, 0) + 1
            
            print(f"\n📋 Remaining chunks by filename:")
            for filename, count in sorted(filename_counts.items()):
                print(f"   • {filename}: {count} chunks")
        except Exception as e:
            print(f"   ⚠️ Could not list remaining chunks: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

