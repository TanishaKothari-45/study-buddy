# Content Store Implementation

## Overview

A content store system that complements Pinecone by storing full chunk content locally. This solves the problem where Pinecone only stores `content_preview` (400 chars) but RetrievalQA chains need full content for quality answers.

## Architecture

```
┌─────────────────────────────────────┐
│   Normal Upload (Existing)          │
│   POST /upload                      │
│   → Pinecone only                   │
│   → No changes                      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│   Content Store Upload (NEW)         │
│   POST /upload-content-store        │
│   → ChromaDB content_store          │
│   → Full text only (no embeddings)  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│   Enhanced Retrieval                 │
│   query_documents(use_content_store=True)
│   1. Query Pinecone (unchanged)     │
│   2. Lookup full content from store  │
│   3. Merge & return                  │
└─────────────────────────────────────┘
```

## Components

### 1. Content Store (`backend/app/utils/content_store.py`)
- Stores full chunk content in ChromaDB (no embeddings)
- Fast lookup by `chunk_id` + `filename` + `chapter`
- Matching logic for verifying chunks

### 2. Upload Endpoint (`backend/app/routes/upload_content_store.py`)
- **Route**: `POST /upload-content-store`
- Processes files with same cleaning/chunking as Pinecone upload
- Stores full content in ChromaDB `content_store` collection
- **Sample checking**: First 5 uploads are matched with Pinecone chunks
- No embeddings, no metadata enrichment

### 3. Enhanced Retrieval (`backend/app/utils/pinecone_handler.py`)
- `query_documents()` now has `use_content_store=True` parameter
- Automatically enriches Pinecone results with full content
- Falls back to `content_preview` if no match found

## Usage

### Step 1: Upload Files to Content Store

```bash
POST /upload-content-store
Content-Type: multipart/form-data

files: [file1.pdf, file2.pdf, ...]
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
    "collection_name": "content_store"
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

### Step 2: Use Enhanced Retrieval

All existing query methods automatically use content store if available:

```python
# In your routes (query.py, mains_answer.py, etc.)
chunks = chroma_handler.query_documents(
    query_text="Explain monsoon formation",
    k=10,
    use_content_store=True  # Default: True
)
# chunks now have full content instead of just preview
```

## Matching Logic

Chunks are matched using:
1. **chunk_id** (exact match) - 10 points
2. **filename** (exact match) - 5 points  
3. **chapter** (preferred but not exact) - 3 points (exact) or 1 point (partial)
4. **content_preview** (first 300 chars) - 5 points (exact) or 3 points (partial)

**Match threshold**: Score >= 8 = good match

## Sample Checking

For the **first 5 uploads**, the system:
- Checks first 5 chunks from each upload
- Matches them with Pinecone chunks
- Reports match statistics
- Logs sample matches and non-matches

This helps verify that:
- Chunking strategy is consistent
- Matching logic works correctly
- Content store is properly populated

## Safety Features

✅ **Zero risk to Pinecone**: Completely separate upload endpoint
✅ **Backward compatible**: Existing code works unchanged
✅ **Graceful fallback**: Uses `content_preview` if no match found
✅ **Optional**: Can disable content store lookup (`use_content_store=False`)
✅ **Incremental**: Can test before full rollout

## File Structure

```
backend/app/
├── utils/
│   ├── content_store.py          # Content store manager
│   └── pinecone_handler.py       # Enhanced with content store lookup
├── routes/
│   └── upload_content_store.py   # New upload endpoint
└── main.py                        # Route registration
```

## Next Steps

1. **Upload files** to content store using `/upload-content-store`
2. **Check sample matches** in logs (first 5 uploads)
3. **Verify matching** - ensure match_rate > 80%
4. **Test retrieval** - queries should now return full content
5. **Monitor performance** - check if content store lookup is fast enough

## Troubleshooting

### Low Match Rate
- Check if chunking strategy matches Pinecone upload
- Verify filename consistency
- Check chapter names match

### Content Store Lookup Fails
- Verify ChromaDB is accessible
- Check `content_store` collection exists
- Ensure chunk_id and filename are present in metadata

### Performance Issues
- Content store lookup is O(1) by chunk_id+filename
- Should be fast (<10ms per chunk)
- If slow, check ChromaDB indexing

## Future Enhancements

- [ ] Batch matching for faster verification
- [ ] Content store statistics dashboard
- [ ] Automatic sync between Pinecone and content store
- [ ] Content store cleanup (remove orphaned chunks)


