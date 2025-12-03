# Content Store & Pinecone Matching System - Summary

## Problem Statement

**Issue:** LangChain's RetrievalQA chains need full chunk content, but Pinecone only stores `content_preview` (400 chars) in metadata. This is insufficient for quality LLM responses.

**Solution:** Create a local content store (SQLite) that stores full chunk text, complementing Pinecone's vector search.

---

## Architecture Overview

```
┌─────────────────────────────────────┐
│   Pinecone (Cloud)                  │
│   - Embeddings (1536-dim)           │
│   - content_preview (400 chars)      │
│   - Metadata (chunk_id, filename,   │
│     chapter, section, etc.)          │
│   → Used for: Vector similarity search
└─────────────────────────────────────┘
              ↓ (query)
              ↓ (get chunk_ids)
              ↓
┌─────────────────────────────────────┐
│   Content Store (SQLite - Local)    │
│   - Full chunk text                  │
│   - chunk_id, filename, chapter      │
│   - content_preview (300 chars)      │
│   → Used for: Full text lookup       │
└─────────────────────────────────────┘
              ↓ (lookup by chunk_id)
              ↓ (merge full content)
              ↓
┌─────────────────────────────────────┐
│   RetrievalQA Chain                  │
│   - Gets full context                │
│   - Generates quality answers        │
└─────────────────────────────────────┘
```

---

## Components

### 1. Content Store (`backend/app/utils/content_store.py`)
- **Database:** SQLite (`backend/data/databases/content_store.db`)
- **Purpose:** Store full chunk content locally (no embeddings)
- **Key Methods:**
  - `store_chunk()` - Store full content with metadata
  - `get_chunk()` - Retrieve full content by chunk_id + filename
  - `match_chunk()` - Match chunks using multiple criteria
  - `get_stats()` - Get store statistics

### 2. Upload Endpoint (`backend/app/routes/upload_content_store.py`)
- **Route:** `POST /upload-content-store/`
- **Purpose:** Upload files to content store (separate from Pinecone)
- **Process:**
  1. Same cleaning/chunking as Pinecone upload
  2. Apply chunk splitting (>1500 words → split by sentences)
  3. Store full content in SQLite
  4. Match with Pinecone chunks (first 5 uploads only)
  5. No embeddings, no metadata enrichment

### 3. Enhanced Retrieval (`backend/app/utils/pinecone_handler.py`)
- **Method:** `query_documents(use_content_store=True)`
- **Process:**
  1. Query Pinecone → Get chunks with chunk_ids
  2. For each chunk: Lookup full content in SQLite
  3. Replace `content_preview` with full content
  4. Return enriched chunks to RetrievalQA

### 4. Frontend (`frontend/app.py`)
- **New Feature:** Upload destination selector
  - "Pinecone (Normal Upload)" - Existing functionality
  - "Content Store (Full Text Storage)" - New option
- **Shows:** Matching statistics, content store stats, sample matches

---

## Matching Logic

Chunks are matched using a scoring system:

| Criteria | Points | Notes |
|----------|--------|-------|
| `chunk_id` (exact) | 10 | Primary identifier |
| `filename` (exact) | 5 | Must match |
| `chapter` (exact) | 3 | Preferred but not required |
| `chapter` (partial) | 1 | Partial match |
| `content_preview` (first 300 chars, exact) | 5 | Strong indicator |
| `content_preview` (first 200 chars, partial) | 3 | Partial match |

**Match Threshold:** Score >= 8 = good match

**Matching Function:** `match_chunk()` in `content_store.py`

---

## Chunk Splitting

**Problem:** Chunks > 1500 words exceed embedder limits and need splitting.

**Solution:** Same splitting logic in both systems:

1. **Check word count:** If > 1500 words → split
2. **Split by sentences:** Preserve sentence boundaries
3. **Add overlap:** 100-word overlap between split chunks
4. **Update chunk_id:** `chunk_id_split1`, `chunk_id_split2`, etc.

**Location:**
- Pinecone upload: `backend/app/utils/pinecone_handler.py` (lines 210-277)
- Content store upload: `backend/app/routes/upload_content_store.py` (lines 233-287)

**Result:** Both systems create identical split chunks with matching IDs.

---

## Database Schema

### SQLite Table: `chunks`

```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    chapter TEXT,
    section TEXT,
    full_content TEXT NOT NULL,
    content_length INTEGER NOT NULL,
    content_preview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunk_id, filename)
);

-- Indexes for fast lookup
CREATE INDEX idx_chunk_filename ON chunks(chunk_id, filename);
CREATE INDEX idx_filename ON chunks(filename);
CREATE INDEX idx_chapter ON chunks(chapter);
```

---

## Usage Flow

### Step 1: Upload to Content Store

```bash
POST /upload-content-store/
Content-Type: multipart/form-data

files: [file1.pdf, file2.pdf]
```

**Response:**
```json
{
  "status": "success",
  "message": "Stored chunks from 2 file(s)",
  "processed_files": [
    {
      "filename": "book.pdf",
      "chunks_stored": 45,
      "chunk_ids": ["1_1_1", "1_1_2", ...]
    }
  ],
  "content_store_stats": {
    "total_chunks": 45,
    "total_files": 1,
    "total_characters": 123456
  },
  "matching_results": {
    "total_chunks": 45,
    "samples_checked": 5,
    "matches": [...],
    "no_matches": [...],
    "match_rate": 0.8
  },
  "sample_check": true
}
```

### Step 2: Query with Full Content

```python
# In your routes (query.py, mains_answer.py, etc.)
chunks = chroma_handler.query_documents(
    query_text="Explain monsoon formation",
    k=10,
    use_content_store=True  # Default: True
)
# chunks now have full content instead of just preview
```

### Step 3: Use with RetrievalQA

```python
qa_chain = handler.get_qa_chain(
    search_type="mmr",
    k=10,
    lambda_mult=0.6
)
result = qa_chain({"query": "Explain monsoon formation"})
# Result uses full content from content store
```

---

## Sample Checking (First 5 Uploads)

For the **first 5 uploads**, the system automatically:
1. Checks first 5 chunks from each upload
2. Matches them with Pinecone chunks
3. Reports match statistics
4. Logs sample matches and non-matches

**Purpose:** Verify chunking consistency and matching accuracy.

**Logs show:**
- Match rate (should be > 80%)
- Sample matches with scores
- Non-matches with best scores

---

## File Structure

```
backend/
├── app/
│   ├── utils/
│   │   ├── content_store.py          # SQLite content store manager
│   │   └── pinecone_handler.py      # Enhanced with content store lookup
│   ├── routes/
│   │   └── upload_content_store.py  # Content store upload endpoint
│   └── main.py                       # Route registration
└── data/
    └── databases/
        └── content_store.db          # SQLite database

frontend/
└── app.py                            # Upload destination selector added
```

---

## Key Features

### ✅ Safety
- **Zero risk to Pinecone:** Completely separate upload endpoint
- **Backward compatible:** Existing code works unchanged
- **Graceful fallback:** Uses `content_preview` if no match found
- **Optional:** Can disable content store lookup (`use_content_store=False`)

### ✅ Matching
- **Multi-criteria:** chunk_id + filename + chapter + content_preview
- **Chapter preference:** Better match if chapter matches (not required)
- **Length tolerance:** ±10 chars for content length
- **Preview matching:** First 300 chars must match

### ✅ Chunk Splitting
- **Same logic:** Both systems use identical splitting
- **Sentence-based:** Preserves sentence boundaries
- **Overlap:** 100-word overlap between splits
- **Matching IDs:** Split chunks have matching IDs in both systems

---

## Configuration

### Database Location
- **Path:** `backend/data/databases/content_store.db`
- **Config:** `settings.DB_DIR` in `backend/app/core/config.py`

### Chunk Limits
- **Max words per chunk:** 1500 (matches embedder limit)
- **Overlap:** 100 words
- **Preview length:** 300 chars (for matching)

### Matching Parameters
- **Length tolerance:** ±10 chars
- **Match threshold:** Score >= 8
- **Sample checking:** First 5 uploads only

---

## Integration Points

### Routes Using Content Store
1. **Query (`/query`)**
   - Uses `query_documents(use_content_store=True)`
   - Automatically enriches with full content

2. **Mains Answer (`/mains-answer`)**
   - Uses `query_documents(use_content_store=True)`
   - Gets full context for answer generation

3. **Mock Test (`/mock-test`)**
   - Uses `query_documents(use_content_store=True)`
   - Gets full context for question generation

### RetrievalQA Chains
- **Prelims Question Generation:** `search_type="mmr", k=10, lambda_mult=0.6`
- **Mains Answer Evaluation:** `search_type="similarity", k=4`
- **Concept Explanation:** `search_type="similarity", k=6`

---

## Current Status

### ✅ Implemented
- SQLite content store
- Content store upload endpoint
- Enhanced retrieval with content lookup
- Frontend upload button
- Chunk splitting (same logic in both systems)
- Matching logic with chapter preference
- Sample checking (first 5 uploads)

### 🔄 Next Steps (Optional)
- Test with real uploads
- Verify matching accuracy
- Monitor performance
- Consider batch matching for faster verification

---

## Troubleshooting

### Low Match Rate
- **Check:** Chunking strategy matches Pinecone upload
- **Check:** Filename consistency
- **Check:** Chapter names match
- **Check:** Content preview (first 300 chars) matches

### Content Store Lookup Fails
- **Check:** SQLite database exists (`content_store.db`)
- **Check:** `chunk_id` and `filename` present in metadata
- **Check:** Database permissions

### Performance Issues
- **Check:** SQLite indexes (should be fast <10ms per lookup)
- **Check:** Database size (SQLite handles millions of rows)

---

## Example: Complete Flow

```
1. User uploads "NCERT-Geography.pdf" to Content Store
   → Chunks created: 1_1_1, 1_1_2, 1_2_1, ...
   → Stored in SQLite with full content

2. User queries: "Explain monsoon formation"
   → Pinecone returns: chunk_id="1_2_1", content_preview="Monsoon refers to..."
   → Content store lookup: chunk_id="1_2_1", filename="NCERT-Geography.pdf"
   → Found! Full content retrieved
   → Merged: chunk["content"] = full_content (replaces preview)

3. RetrievalQA chain receives full content
   → Generates comprehensive answer with full context
   → Quality improved significantly
```

---

## Benefits

1. **Full Context:** RetrievalQA gets complete chunk text
2. **Cost Effective:** No re-embedding needed
3. **Fast Lookup:** SQLite O(1) lookup by chunk_id
4. **Safe:** No changes to Pinecone
5. **Flexible:** Can disable if needed
6. **Future-proof:** Easy to merge later

---

## Notes

- **Database:** SQLite (simple, lightweight, no dependencies)
- **Matching:** Multi-criteria scoring (not just exact match)
- **Chapter:** Preferred but not required for matching
- **Splitting:** Same logic ensures perfect matching
- **Sample Checking:** Only first 5 uploads (for verification)

---

## Related Files

- `backend/app/utils/content_store.py` - Content store implementation
- `backend/app/routes/upload_content_store.py` - Upload endpoint
- `backend/app/utils/pinecone_handler.py` - Enhanced retrieval
- `frontend/app.py` - Frontend upload button
- `CONTENT_STORE_IMPLEMENTATION.md` - Detailed implementation guide

---

**Last Updated:** 2025-01-XX
**Status:** ✅ Implemented and ready for testing

