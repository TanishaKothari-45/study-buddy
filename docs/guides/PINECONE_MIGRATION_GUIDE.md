# Pinecone Migration Guide

This guide explains how to migrate from ChromaDB to Pinecone and use the new Pinecone integration.

## Overview

We've migrated from ChromaDB to Pinecone to avoid the "dict object has no attribute 'dimensionality'" error that was occurring with ChromaDB/LangChain compatibility issues. Pinecone has native LangChain integration that works seamlessly.

## Prerequisites

1. **Pinecone Account**: Sign up at https://www.pinecone.io/
2. **API Key**: Get your Pinecone API key from the dashboard
3. **Environment Variables**: Add to your `.env` file:
   ```bash
   PINECONE_API_KEY=your-pinecone-api-key-here
   ```

## Installation

Install the required dependencies:

```bash
pip install pinecone-client>=3.0.0 langchain-pinecone>=0.0.3
```

Or install all requirements:

```bash
pip install -r backend/requirements.txt
```

## Migration Steps

### Step 1: Run the Migration Script

The migration script will export all chunks from ChromaDB and import them to Pinecone:

```bash
python migrate_chroma_to_pinecone.py
```

Options:
- `--chroma-collection`: ChromaDB collection name (default: from settings)
- `--pinecone-index`: Pinecone index name (default: chroma collection name converted)
- `--batch-size`: Batch size for uploads (default: 100)

Example:
```bash
python migrate_chroma_to_pinecone.py --chroma-collection geography_docs_enriched --pinecone-index geography-docs-enriched --batch-size 100
```

### Step 2: Configure the Application

Update `backend/app/core/config.py` or set environment variables:

```python
USE_PINECONE = True  # Set to True to use Pinecone
PINECONE_INDEX_NAME = "geography-docs-enriched"  # Your Pinecone index name
```

Or set in `.env`:
```bash
USE_PINECONE=True
PINECONE_INDEX_NAME=geography-docs-enriched
```

### Step 3: Restart the Application

Restart your FastAPI backend:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

## Features

### ✅ What Works

- **Query Documents**: `query_documents()` - Standard similarity search
- **MMR Retrieval**: `query_documents_mmr()` - Maximum Marginal Relevance search
- **MMR Selection**: `mmr_select_from_chunks()` - Apply MMR to pre-retrieved chunks
- **Add Documents**: `add_documents()` - Add new chunks to Pinecone
- **Switch Index**: `switch_to_collection()` - Switch between Pinecone indexes
- **Get Stats**: `get_stats()` - Get index statistics
- **Delete Collection**: `delete_collection()` - Delete a Pinecone index

### ⚠️ Differences from ChromaDB

1. **Index Names**: Pinecone index names must be lowercase and use hyphens (not underscores)
2. **Metadata**: Pinecone metadata must be flat (no nested dicts) and values must be strings, numbers, or booleans
3. **Get All Documents**: `get_all_documents_paginated()` is less efficient in Pinecone (uses similarity search with dummy query)
4. **Delete All**: `delete_all_collections()` doesn't work the same way - Pinecone doesn't have a concept of "all collections"

## Backward Compatibility

The code maintains backward compatibility:
- Routes continue to use `app.state.chroma_handler` (which now points to `vector_handler`)
- All existing method calls work the same way
- You can switch between ChromaDB and Pinecone via config

## Troubleshooting

### Error: PINECONE_API_KEY not found
- Make sure you've added `PINECONE_API_KEY` to your `.env` file
- Restart the application after adding the key

### Error: Index not found
- Make sure the index name matches exactly (case-sensitive)
- Check that the index exists in your Pinecone dashboard
- The migration script will create the index if it doesn't exist

### Error: Dimension mismatch
- Make sure all chunks use the same embedding dimension
- OpenAI embeddings: 1536 dimensions
- Sentence Transformers: 384 dimensions
- The migration script detects this automatically

### Migration fails partway through
- The migration script processes in batches
- You can re-run it - it will skip already-uploaded chunks (based on IDs)
- Check Pinecone dashboard for upload progress

## Benefits of Pinecone

1. **No Dict Errors**: Native LangChain integration avoids compatibility issues
2. **Scalability**: Pinecone is designed for production-scale vector search
3. **Performance**: Faster query times for large indexes
4. **Reliability**: Managed service with high availability
5. **MMR Support**: Native MMR support without workarounds

## Switching Back to ChromaDB

If you need to switch back to ChromaDB:

1. Set `USE_PINECONE = False` in config
2. Restart the application
3. The application will use ChromaDB instead

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. Verify your Pinecone API key is correct
3. Ensure the index exists and has the correct dimension
4. Check that LangChain and Pinecone packages are installed correctly

