"""
pinecone_auto_cleaner.py

----------------------------------------------------

Cleans all chunks in your Pinecone index:

- Removes institute names, URLs, page numbers, OCR junk, etc.

- Normalizes Unicode + whitespace

- Deletes chunks that are too short / meaningless

- Re-upserts cleaned chunks with the same embeddings (no re-embedding)

⚡ Zero OpenAI cost (only Pinecone metadata operations)

⚠️ NOTE: This script cleans content_preview (first 400 chars) stored in metadata.
The full content is not stored in Pinecone, so only previews can be cleaned.

"""

import re
import unicodedata
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables
project_root = Path(__file__).resolve().parent
env_path = project_root / ".env"
load_dotenv(env_path)

# ---------------- CONFIG ----------------

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY not found in environment variables. Please set it in your .env file.")

INDEX_NAME = "study-buddy"
EMBEDDING_DIMENSION = 1536  # OpenAI text-embedding-3-small dimension

MAX_RESULTS = 10000         # how many vectors to fetch
MIN_WORDS_THRESHOLD = 10    # delete chunks shorter than this (lowered since we only have previews)
BATCH_SIZE = 1000           # optional batching for large datasets

# ---------------- CLEANING RULES ----------------

garbage_patterns = [
    # Coaching Branding / Watermarks
    r'visionias', r'gsscore', r'forumias', r'vajiram', r'insightsonindia',
    r'byjus', r'drishtiias', r'upscpathshala', r'unacademy', r'nextias',
    r'iasscore', r'civilsdaily', r'iasbaba', r'arihant', r'madeeasy',
    r'arihantpublications', r'arihantseries', r'compilation', r'handout',
    r'mentorship', r'coaching\s*institute', r'www\.ncert\.nic\.in',
    
    # URLs, Contact Info, File Paths
    r'www\.[a-z0-9\-\.]+', r'https?://[^\s]+',
    r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b',  # emails
    r'[A-Z]:\\[^\s]+', r'\b\d{6,}\b',              # phone numbers / file paths
    r'\bcontact\s+us\b', r'\bcall\s+(us|on)\b',
    
    # Headers / Footers / Common Labels
    r'page\s*\d+(\s*of\s*\d+)?',
    r'(test\s*series|class\s*notes|study\s*material)',
    r'(current\s*affairs|monthly\s*magazine)',
    r'(module\s*\d+|paper\s*\d+|set\s*\d+)',
    r'\b(2020|2021|2022|2023|2024|2025)\b',
    r'\bpdf\b', r'\bversion\b', r'\bfile\b',
    
    # Metadata / Book Info
    r'\bsubject\s*:', r'\bexercise\s*\d+', r'\bchapter\s*\d+', 
    r'\bunit\s*\d+', r'\bclass\s*\d+\b', r'\bbook\s*name\s*:',
    r'\bquestion\s*bank\b', r'\banswers?\b', r'\bchapter\s*overview\b',
    r'\bnotes\s*[:\-]', r'\bsource\s*[:\-]',
    
    # OCR / Encoding Artifacts
    r'[\x00-\x1F\x7F-\x9F]',  # invisible control chars
    r'—', r'–', r''', r''', r'"', r'"', r'•', r'…', r'→', r'←',
    r'\bfig\.\s*\d+', r'\btable\s*\d+', r'\bdiagram\s*\d+', r'figure\s*\d+', r'\bchart\s*\d+',
    
    # Misc Marginal / Web-only text
    r'\bread\s*more\b', r'\bdownload\s*now\b', 
    r'\bplease\s*(refer|visit)\b', r'\bfor\s+more\s+details\b',
    r'\bquiz\b', r'\banswers?\b', r'\bmcq\b', r'\bquestion\s*\d+\b',
    r'\bsection\s*[a-z]\b'
]

# ---------------- CLEANING FUNCTION ----------------

def clean_text(text: str) -> str:
    """Apply all cleaning rules and normalize whitespace + Unicode."""
    text = unicodedata.normalize("NFKC", text)
    for p in garbage_patterns:
        text = re.sub(p, '', text, flags=re.I)
    # collapse extra whitespace / newlines
    text = re.sub(r'\s+', ' ', text)
    # remove punctuation-only lines or leftover junk
    text = re.sub(r'^\W+$', '', text, flags=re.M)
    return text.strip()

def is_valid_chunk(text: str) -> bool:
    """Decide if a chunk is meaningful enough to keep."""
    words = text.split()
    if len(words) < MIN_WORDS_THRESHOLD:
        return False
    if not any(c.isalpha() for c in text):
        return False
    return True

# ---------------- MAIN CLEANUP ----------------

def main():
    print(f"🔗 Connecting to Pinecone index '{INDEX_NAME}'...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    
    print(f"📦 Fetching up to {MAX_RESULTS} chunks for cleanup...")
    # Query with a zero vector to get all chunks (or use list_all if available)
    # Note: Pinecone doesn't have a direct "list all" API, so we use query with zero vector
    res = index.query(
        vector=[0]*EMBEDDING_DIMENSION, 
        top_k=MAX_RESULTS, 
        include_metadata=True
    )
    vectors = res.get('matches', [])
    print(f"✅ Retrieved {len(vectors)} chunks")
    
    cleaned, deleted = [], []
    stats = {"short": 0, "empty": 0, "cleaned": 0}
    
    for v in vectors:
        meta = v.get("metadata", {}).copy()  # Make a copy to avoid modifying original
        # Pinecone stores content_preview (first 400 chars), not full content
        text = meta.get("content_preview", "") or meta.get("content", "") or meta.get("summary", "")
        
        if not text:
            stats["empty"] += 1
            deleted.append(v["id"])
            continue
        
        cleaned_text = clean_text(text)
        
        if not is_valid_chunk(cleaned_text):
            stats["short"] += 1
            deleted.append(v["id"])
            continue
        
        if cleaned_text != text:
            stats["cleaned"] += 1
            # Update content_preview (or create it if it doesn't exist)
            meta["content_preview"] = cleaned_text
            # Also clean summary if it exists
            if "summary" in meta:
                cleaned_summary = clean_text(meta["summary"])
                meta["summary"] = cleaned_summary
        
        cleaned.append({
            "id": v["id"],
            "values": v["values"],  # same embeddings
            "metadata": meta
        })
    
    # Delete low-quality chunks
    if deleted:
        print(f"🗑️ Deleting {len(deleted)} low-quality chunks...")
        for i in range(0, len(deleted), BATCH_SIZE):
            batch = deleted[i:i+BATCH_SIZE]
            index.delete(ids=batch)
    
    # Re-upload cleaned chunks
    if cleaned:
        print(f"📤 Uploading {len(cleaned)} cleaned chunks back to Pinecone...")
        for i in range(0, len(cleaned), BATCH_SIZE):
            batch = cleaned[i:i+BATCH_SIZE]
            index.upsert(vectors=batch)
    
    # Report
    print("\n===== 🧹 CLEANUP SUMMARY =====")
    print(f"Total fetched: {len(vectors)}")
    print(f"Cleaned & kept: {len(cleaned)}")
    print(f"Deleted short/empty: {len(deleted)}")
    print(f" - Short chunks: {stats['short']}")
    print(f" - Empty chunks: {stats['empty']}")
    print(f" - Text cleaned: {stats['cleaned']}")
    print("✅ Cleanup complete!\n")
    
    # Optional backup (just metadata, for audit)
    backup = [{"id": c["id"], "metadata": c["metadata"]} for c in cleaned]
    backup_path = Path(__file__).resolve().parent.parent.parent / "config" / "cleaned_metadata_backup.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print(f"💾 Backup saved to {backup_path}")

if __name__ == "__main__":
    main()

