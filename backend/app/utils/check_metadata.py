"""
Quick sanity check for metadata enrichment
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).resolve().parent.parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.utils.chroma_handler import ChromaHandler
import json

ch = ChromaHandler()
ch.switch_to_collection('geography_docs_enriched')
docs = ch.get_all_documents_paginated()

print(f'\n📊 Total chunks: {len(docs)}')
print(f'\n🔍 Sample metadata from first chunk:')
print('=' * 60)
print(json.dumps(docs[0]['metadata'], indent=2))
print('=' * 60)

print(f'\n✅ Metadata keys present: {list(docs[0]["metadata"].keys())}')
print(f'\n✨ Checking enrichment fields:')
print(f'  - major_domain: {"✓" if docs[0]["metadata"].get("major_domain") else "✗"} {docs[0]["metadata"].get("major_domain", "Missing")}')
print(f'  - sub_domain: {"✓" if docs[0]["metadata"].get("sub_domain") else "✗"} {docs[0]["metadata"].get("sub_domain", "Missing")}')
print(f'  - difficulty: {"✓" if docs[0]["metadata"].get("difficulty") else "✗"} {docs[0]["metadata"].get("difficulty", "Missing")}')
print(f'  - summary: {"✓" if docs[0]["metadata"].get("summary") else "✗"}')

# Check a few more samples
print(f'\n📋 Checking 5 random samples:')
for i in [0, 100, 200, 400, 600]:
    if i < len(docs):
        meta = docs[i]['metadata']
        print(f'  Chunk {i}: major_domain={meta.get("major_domain", "Missing")}, sub_domain={meta.get("sub_domain", "Missing")[:30] if meta.get("sub_domain") else "Missing"}')

