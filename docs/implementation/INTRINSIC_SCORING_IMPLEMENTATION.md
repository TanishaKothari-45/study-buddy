# Intrinsic Scoring Implementation

## Overview

Added intrinsic quality scoring to filter out garbage chunks and improve retrieval quality. Chunks are classified into three categories and assigned scores that are combined with similarity scores during retrieval.

## Components

### 1. **Intrinsic Scorer** (`backend/app/utils/intrinsic_scorer.py`)

**Classification Labels:**
- `HIGH_GEOGRAPHY_CONTENT`: 0.9 (clean, factual, NCERT-style content)
- `LOW_GEOGRAPHY_CONTENT`: 0.6 (incomplete, shallow, but usable)
- `NOISE_OR_GARBAGE`: 0.1 (OCR errors, URLs, PYQ answers, not usable)

**Functions:**
- `classify_chunk_intrinsic()`: Classify single chunk using GPT-4o-mini
- `classify_chunks_batch_intrinsic()`: Batch classification for efficiency
- `calculate_combined_score()`: Score = 0.8 * similarity + 0.2 * intrinsic
- `reorder_chunks_by_combined_score()`: Re-rank chunks by combined score

### 2. **Metadata Enricher Integration** (`backend/app/utils/metadata_enricher.py`)

**Changes:**
- Added `intrinsic_score` to metadata during enrichment
- New chunks automatically get classified and scored
- Defaults to 0.6 (LOW) if classification fails

**Integration Points:**
- `classify_chunks_batch()`: Adds intrinsic_score during batch classification
- `enrich_metadata()`: Adds intrinsic_score for single chunk enrichment

### 3. **Script for Existing Chunks** (`backend/add_intrinsic_scores.py`)

**Usage:**
```bash
python add_intrinsic_scores.py [--batch-size 10] [--limit 100]
```

**What it does:**
1. Retrieves all chunks from vector store
2. Classifies each chunk using LLM
3. Updates metadata with `intrinsic_score`
4. Re-uploads chunks with updated metadata

**Note:** Currently works best with ChromaDB. Pinecone requires manual update or query-based approach.

### 4. **Retrieval Integration** (`backend/app/utils/pinecone_handler.py`)

**Modified Functions:**

**`mmr_select_from_chunks()`:**
- Now uses combined scores (0.8 * similarity + 0.2 * intrinsic) in MMR calculation
- Prefers high-quality chunks while maintaining diversity
- Falls back to similarity-only if intrinsic scorer unavailable

**`query_documents_mmr()`:**
- Uses similarity search to get candidates
- Applies MMR with combined scoring via `mmr_select_from_chunks()`
- Ensures quality chunks are preferred

## Scoring Formula

```
Combined Score = 0.8 * similarity_score + 0.2 * intrinsic_score
```

**Where:**
- `similarity_score`: Cosine similarity from vector search (0-1)
- `intrinsic_score`: Quality score (0.1, 0.6, or 0.9)

**Example:**
- High similarity (0.9) + High intrinsic (0.9) = 0.8*0.9 + 0.2*0.9 = **0.90**
- High similarity (0.9) + Low intrinsic (0.6) = 0.8*0.9 + 0.2*0.6 = **0.84**
- High similarity (0.9) + Garbage (0.1) = 0.8*0.9 + 0.2*0.1 = **0.74**

Garbage chunks are penalized but can still be selected if very relevant.

## Flow

### For New Chunks:
```
Upload → Metadata Enricher → LLM Classification → intrinsic_score added → Store
```

### For Existing Chunks:
```
Run add_intrinsic_scores.py → Classify all chunks → Update metadata → Re-store
```

### During Retrieval:
```
Query → Similarity Search (fetch_k candidates) → 
Calculate Combined Scores (similarity + intrinsic) → 
MMR Selection (uses combined scores) → 
Top k chunks returned
```

## Benefits

1. **Filters Garbage**: Low-quality chunks (OCR errors, URLs) get penalized
2. **Prefers Quality**: High-quality chunks get boosted in ranking
3. **Maintains Relevance**: Similarity still dominates (80% weight)
4. **Preserves Diversity**: MMR still ensures diverse selection
5. **Backward Compatible**: Defaults to 0.6 if intrinsic_score missing

## Default Behavior

- **If `intrinsic_score` missing**: Defaults to 0.6 (LOW_GEOGRAPHY_CONTENT)
- **If classification fails**: Defaults to 0.6 (safe fallback)
- **If scorer unavailable**: Uses similarity-only (backward compatible)

## Next Steps

1. **Run script for existing chunks:**
   ```bash
   cd backend
   python add_intrinsic_scores.py --batch-size 10
   ```

2. **Monitor logs** to see score distribution

3. **Test retrieval** - should see better quality chunks

4. **Adjust weights** if needed (currently 0.8/0.2 split)

## Notes

- Uses GPT-4o-mini for cost efficiency
- Classification is done once per chunk (stored in metadata)
- Combined scoring happens during retrieval (no extra LLM calls)
- Current retrieval logic preserved, just enhanced with quality filtering

