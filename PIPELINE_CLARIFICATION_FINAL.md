# Pipeline Clarification: Final Correct Version

**Date**: 2026-04-04  
**Status**: ✅ Corrected and implemented  

---

## The Pipeline (Corrected)

### Stage 0: Blueprint (v4.5 Controlled)
```
Output: 30 skeletons → select 13
Each skeleton has:
  - Concept (e.g., "Monsoon")
  - Question type (e.g., "multi_statement")
  - Difficulty (easy/medium/hard)
  - Difficulty type (15 specific types)
  - Sub-concepts (topics to test)
  - Trap strategy (e.g., GEO_T01)
  - CA flag (if current affairs needed)
  - Concept pool source
```

---

### Stage 1: Retrieval (70% Structured + 30% Exploratory)

**Per Skeleton:**

1. **Build Structured Queries**
   - One query per unique source_concept in sub_concepts
   - Count varies: 1-4 queries per skeleton

2. **Generate Exploratory Queries**
   - LLM-generated novel angles
   - Same count as structured (e.g., if 2 structured → 2 exploratory)
   - Total: 2-8 queries per skeleton

3. **Pinecone Retrieval Per Query**
   ```
   For each query:
     - Fetch: 20 chunks
     - Cross-encode: check semantic relevance against THAT QUERY
     - MMR: select top 5 with randomized lambda (0.7/0.5/0.3)
   ```

4. **Result Per Skeleton: Variable Chunks**
   ```
   SK001: 2 queries × 5 chunks = 10 chunks
   SK002: 3 queries × 5 chunks = 15 chunks
   SK003: 1 query × 5 chunks = 5 chunks
   ...
   ```

5. **CA Context (if ca_flag=True)**
   - 4 Google Search queries: 2 structured + 2 exploratory
   - Returns bullet points added to that skeleton

---

### Stage 3: Generation (Direct Batch)

**Batch Input Structure:**

**Batch 1 (7 skeletons):**
```
QUESTION 1: SK001
  - Skeleton spec
  - 10 chunks (from 2 queries)
  - CA context (if applicable)
  
QUESTION 2: SK002
  - Skeleton spec
  - 15 chunks (from 3 queries)
  - CA context (if applicable)

... 7 questions total

Total chunks in Batch 1: Variable (sum of individual chunk counts)
Example: 10 + 15 + 5 + 12 + 8 + 10 + 15 = ~75 chunks
```

**Batch 2 (6 skeletons):**
```
QUESTION 1: SK008
  - Skeleton spec
  - 10 chunks
  - CA context

... 6 questions total

Total chunks in Batch 2: Variable
```

**One API Call Per Batch:**
- Batch 1 → 1 API call (7 questions + variable chunks)
- Batch 2 → 1 API call (6 questions + variable chunks)

---

### Stage 4: Quality Gate

```
Check each of 10 generated questions:
  ✓ Structural validity (4 options, clear stem)
  ✓ v4.5 Controlled constraints (question_type match, trap_id validity)
  ✓ Trap presence in question
  ✓ CA in stem (if ca_flag=True)
  ✓ Distractor plausibility
  
Output: passed[], failed_ids[]
```

---

### Stage 5: Gap Fill & Finalize

```
For each failed skeleton:
  1. Downgrade difficulty (hard → medium → easy)
  2. Disable CA flag
  3. Retry generation with relaxed skeleton
  
If still fails → replace with fresh easy skeleton

Final: 10 questions in wire format
```

---

## Key Insights

### Why Variable Chunks Per Skeleton?

**Option 1: Fixed 5 chunks per skeleton**
- ❌ Loses information from different query angles
- ❌ All skeletons treated equally despite different query needs

**Option 2: Variable chunks (queries × 5) ✅**
- ✅ Preserves all query angles
- ✅ Respects skeleton's actual retrieval needs
- ✅ Diversity comes from different queries, not artificial sampling

### Why No Re-ranking All Chunks?

Already done per query:
- Query 1: 20 fetched → cross-encode → 5 selected ✓
- Query 2: 20 fetched → cross-encode → 5 selected ✓
- Query 3: 20 fetched → cross-encode → 5 selected ✓

Re-ranking all combined would:
- ❌ Lose query diversity
- ❌ Bias toward first query chunks
- ❌ Redundant (already ranked per query)

### Chunk Filtering: ONLY in Stage 1

✅ **Stage 1 correctly filters:**
- Per query: 20 → 5 (via cross-encode + MMR)
- Variable per skeleton: (queries × 5)

❌ **Stage 3 should NOT filter:**
- Use all chunks returned by Stage 1
- They're already the best from each query angle

---

## Example: SK001 with 2 Queries

```
Stage 1 Input:
  Skeleton: Monsoon
  Sub-concepts: [Monsoon withdrawal, ITCZ role, El Nino impact]

Stage 1 Process:
  Query 1 (Structured): "Monsoon withdrawal ITCZ El Nino"
    → Fetch 20 → Cross-encode (query relevance) → MMR select 5
    → Chunks: [C1, C2, C3, C4, C5]
  
  Query 2 (Exploratory): "Monsoon impact Indian agriculture climate change"
    → Fetch 20 → Cross-encode (query relevance) → MMR select 5
    → Chunks: [C6, C7, C8, C9, C10]

Stage 1 Output:
  RetrievalResult:
    static_chunks: [C1-C10]  ← 10 chunks
    query_metadata: [
      {query_text: "...", is_exploratory: false, mmr_lambda: 0.7, chunk_count: 5},
      {query_text: "...", is_exploratory: true, mmr_lambda: 0.3, chunk_count: 5}
    ]

Stage 3 Input:
  Batch: 7 skeletons including SK001
  For SK001: Use all 10 chunks (don't filter to 5)
  
Stage 3 LLM sees:
  "QUESTION 1: Monsoon (difficulty: hard)
   Chunks: [C1, C2, ..., C10]
   These chunks are from 2 different query angles:
   - 5 from structured (Monsoon withdrawal, ITCZ, El Nino)
   - 5 from exploratory (agriculture, climate impact)
   Use them creatively to build the question."
```

---

## Code Changes Summary

### ✅ Stage 1 (stage1_retrieval.py)
- **Already correct**: Per query selection (20→5), variable per skeleton
- Updated docstring to clarify variable chunks

### ✅ Stage 3 (stage3_generation.py)
- **Removed**: Incorrect `[:5]` filtering
- **Updated**: Use all chunks from Stage 1 as-is
- **Added**: Logging showing variable chunk counts per skeleton

### ✅ Pipeline (pipeline.py)
- **Updated**: Batch logging to show variable total chunks
- **Clarified**: Logging shows (queries × 5) per skeleton

---

## Logging Output Expected

```
[Stage1] sk_001 | Pinecone retrieval complete: 10 chunks from 2 queries (1 structured, 1 exploratory)
[Stage1] sk_002 | Pinecone retrieval complete: 15 chunks from 3 queries (2 structured, 1 exploratory)
[Stage1] sk_003 | Pinecone retrieval complete: 5 chunks from 1 query (1 structured, 0 exploratory)
...

[Stage3][BatchPrompt] Building batch prompt for 7 skeletons (chunk count = Σ of [query_count × 5] per skeleton)
[3] Sub-batch 1/2: 7 skeletons, 75 chunks total (variable per skeleton: queries×5), temp=0.83
[Stage3][Q1/sk_001] 10 chunks from 2 queries (1 structured, 1 exploratory)
[Stage3][Q2/sk_002] 15 chunks from 3 queries (2 structured, 1 exploratory)
...
```

---

## Summary

✅ **Stage 1**: Correct. Variable chunks per skeleton (queries × 5)  
✅ **Stage 3**: Corrected. Use all chunks from Stage 1 (no re-filtering)  
✅ **Batch Size**: Variable per batch (7 or 6 skeletons)  
✅ **Total Chunks Per Batch**: Variable (sum of individual skeleton chunks)  
✅ **API Calls**: 1 per batch (not 1 per skeleton)  

**Pipeline is now ready for testing.** 🚀
