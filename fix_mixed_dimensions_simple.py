#!/usr/bin/env python3
"""
Simple script to delete TXT file chunks from ChromaDB collection.
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
os.chdir(project_root / "backend")

from app.utils.chroma_handler import ChromaHandler

def main():
    print("=" * 80)
    print("🔧 Delete TXT File Chunks from ChromaDB")
    print("=" * 80)
    
    chroma = ChromaHandler()
    chroma.switch_to_collection("geography_docs_enriched")
    
    # Get total count
    total_count = chroma.collection.count()
    print(f"\n📊 Total chunks in collection: {total_count}")
    
    # Delete chunks by filename pattern
    txt_filename = "Certificate Physical and Human Geography[www.UPSCPDF.com]_compressed-pages-1.txt"
    
    print(f"\n🗑️  Deleting chunks from TXT file:")
    print(f"   {txt_filename}")
    
    # Confirm
    response = input(f"\n⚠️  Delete all chunks from this TXT file? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled. No chunks deleted.")
        return
    
    try:
        deleted_count = chroma.delete_documents_by_filename(txt_filename)
        print(f"\n✅ Successfully deleted {deleted_count} chunks")
        print(f"\n📝 Next steps:")
        print(f"   1. Make sure OPENAI_API_KEY is set in your .env file")
        print(f"   2. Re-upload your TXT file")
        print(f"   3. It will be embedded with 1536-dim (OpenAI) to match your PDFs")
        print(f"   4. Chunks are now limited to 2500 words max to prevent token limit errors")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

