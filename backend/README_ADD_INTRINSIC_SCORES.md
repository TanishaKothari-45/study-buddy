# Add Intrinsic Scores Script

This script adds `intrinsic_label` and `intrinsic_score` to existing chunks in your database.

## Quick Start

### Option 1: Using the Helper Script (Recommended)

```bash
# From project root
./run_add_intrinsic_scores.sh

# With options
./run_add_intrinsic_scores.sh --limit 100 --batch-size 20
```

### Option 2: Manual Activation

```bash
# 1. Activate virtual environment
source ../venv/bin/activate  # or: source venv/bin/activate

# 2. Change to backend directory
cd backend

# 3. Run the script
python3 add_intrinsic_scores.py
```

## Usage Examples

```bash
# Process all chunks (default batch size 10)
python3 add_intrinsic_scores.py

# Process first 100 chunks only (for testing)
python3 add_intrinsic_scores.py --limit 100

# Process chunks from specific file
python3 add_intrinsic_scores.py --filename "NCERT_Geography_Class_11.pdf"

# Use larger batch size (faster but more API calls)
python3 add_intrinsic_scores.py --batch-size 20

# Skip content store update (only update vector store)
python3 add_intrinsic_scores.py --skip-content-store
```

## What It Does

1. **Retrieves chunks** from vector store (Pinecone/ChromaDB)
2. **Enriches with full content** from content store (SQLite)
3. **Classifies chunks** using LLM (gpt-4o-mini) in batches
4. **Stores both label and score**:
   - `intrinsic_label`: "HIGH_GEOGRAPHY_CONTENT", "LOW_GEOGRAPHY_CONTENT", or "NOISE_OR_GARBAGE"
   - `intrinsic_score`: 0.9, 0.6, or 0.1
5. **Updates metadata** in both vector store and content store

## Output

The script will show:
- Progress for each batch
- Distribution statistics (how many chunks in each category)
- Summary of updates

Example output:
```
📊 Intrinsic Classification Distribution:
======================================================================
   HIGH_GEOGRAPHY_CONTENT      (score: 0.9):   450 chunks (45.0%)
   LOW_GEOGRAPHY_CONTENT        (score: 0.6):   400 chunks (40.0%)
   NOISE_OR_GARBAGE             (score: 0.1):   150 chunks (15.0%)
======================================================================
   Total chunks processed: 1000
```

## Requirements

- Virtual environment activated
- OpenAI API key set in `.env` file
- Vector store (Pinecone or ChromaDB) configured
- Content store (SQLite) initialized

## Notes

- The script skips chunks that already have both `intrinsic_label` and `intrinsic_score`
- Classification uses gpt-4o-mini for cost efficiency
- Default batch size is 10 (adjust based on API rate limits)
- Processing time depends on number of chunks and batch size


