# Batch Input Clarification: Chunk Distribution

**Date**: 2026-04-04  
**Topic**: Stage 1 → Stage 3 data flow for mock generator  
**Status**: ✅ Clarified and implemented

---

## The Question

How are chunks distributed when batching skeletons for the mock generator?

---

## The Answer

### Structure: One Batch = N Skeletons × 5 Chunks Each

**Batch 1 (7 skeletons):**
- 7 skeletons
- 5 chunks per skeleton
- **Total: 35 chunks** sent to LLM in one prompt

**Batch 2 (6 skeletons):**
- 6 skeletons  
- 5 chunks per skeleton
- **Total: 30 chunks** sent to LLM in one prompt

### Why 5 Chunks Per Skeleton?

**Stage 1 retrieves:** 65 chunks per skeleton
- 50 from structured queries (70%)
- 15 from exploratory queries (30%)

**Stage 3 filters to:** Top 5 chunks per skeleton
- These 5 are already ranked by relevance (Pinecone score + cross-encoder re-ranking)
- Mixed: both structured AND exploratory together, ranked
- No separate batching of 7 structured + 3 exploratory
- They're merged and ranked as one pool

### Prompt Structure

```
BATCH PROMPT:
├─ Shared Rules (question types, formatting)
├─ Question 1 (Batch 1)
│  ├─ Skeleton spec
│  ├─ Top 5 chunks (from 65 retrieved)
│  └─ CA context (if flag=True)
├─ Question 2 (Batch 1)
│  ├─ Skeleton spec
│  ├─ Top 5 chunks
│  └─ CA context
├─ ...
└─ Question 7 (Batch 1)
   ├─ Skeleton spec
   ├─ Top 5 chunks
   └─ CA context

Total in prompt: 35 chunks + rules + 7 skeleton specs
```

### Implementation in Code

**pipeline.py (lines ~310):**
```python
# Calculate total chunks for this batch
chunks_per_skeleton = 5
total_chunks_in_batch = len(batch_skeletons) * chunks_per_skeleton

logger.info(
    f"  [3] Sub-batch {batch_idx+1}: "
    f"{len(batch_skeletons)} skeletons × {chunks_per_skeleton} chunks/sk = {total_chunks_in_batch} chunks"
)
```

**stage3_generation.py (lines ~555):**
```python
# Filter to top 5 chunks per skeleton
chunks_to_use = retrieval_result.static_chunks[:5]
static_text = _format_chunks(chunks_to_use)

logger.info(
    f"[Stage3][Chunk Filtering] Q{idx}: "
    f"Retrieved {len(retrieval_result.static_chunks)} chunks → using top 5"
)
```

---

## Logging Output

Expected logs from test run:

```
[Stage3][BatchPrompt] Building prompt for 7 questions (35 chunks: 7 skeletons × 5 chunks/sk)
  [Stage3][Q1][Chunk Filtering] Q1/sk_001: Retrieved 65 chunks → using top 5
  [Stage3][Q2][Chunk Filtering] Q2/sk_002: Retrieved 65 chunks → using top 5
  ...
  [Stage3][Q7][Chunk Filtering] Q7/sk_007: Retrieved 65 chunks → using top 5
```

---

## Why This Works

1. **Efficiency:** 35 tokens vs 455 tokens (5 vs 65 chunks × 7 skeletons)
2. **Quality:** Top 5 are most relevant (already ranked)
3. **Diversity:** Top 5 includes both structured AND exploratory mixed together
4. **Simplicity:** LLM can choose from both types naturally (no artificial separation)

---

## Summary

✅ **One batch = N skeletons**  
✅ **N skeletons = 5 chunks each (filtered from 65)**  
✅ **Per batch: 35 or 30 chunks total**  
✅ **5 chunks are pre-ranked mix of 70% structured + 30% exploratory**  
✅ **Ready for mock generator**
