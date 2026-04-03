# Stage 1 v2: LLM-Driven Exploratory Retrieval

## Overview: 70% Structured + 30% Exploratory

Stage 1 now combines **rule-based structured queries** (70%) with **LLM-generated exploratory queries** (30%) to ensure both quality and corpus discovery.

---

## Architecture

### Input
- `QuestionSkeleton` from Stage 0 v4.5 Controlled
- `PineconeHandler` for vector retrieval
- `GeminiClient` for LLM query generation
- `Subject` for domain filtering

### Output
```python
RetrievalResult {
  skeleton_id: str,
  static_chunks: List[Dict],          # 65 chunks total
  ca_context: str,                    # Current affairs context
  ca_queries: List[str],              # Queries used for CA search
  retrieval_mode: str,
  query_metadata: List[Dict],         # Metadata for each query
}
```

---

## 70/30 Split Strategy

### 70% STRUCTURED (Rule-Based)
**Purpose:** Respect Stage 0 skeleton constraints

**Source:** `skeleton.sub_concepts`

**Queries:** ~10 queries
```
For each unique source_concept in sub_concepts:
  Query: "{concept} {topic1} {topic2} ... {topicN}"
  Example: "Monsoon mechanism distribution precipitation"
```

**Process:**
1. Group sub_concepts by source_concept
2. Build query text from concept + topic concatenation
3. Mark as `is_exploratory=False`

---

### 30% EXPLORATORY (LLM-Generated)
**Purpose:** Discover corpus angles NOT in skeleton

**Source:** Gemini LLM (generic, no JSON dependency)

**Queries:** ~3 queries
```
LLM Input:
  - Concept: "Monsoon"
  - Sub-concepts tested: ["SW monsoon tracking", "precipitation patterns"]
  - Aspects covered: ["mechanism", "distribution"]
  - Difficulty: "hard_cross_domain_linking"

LLM Output (3 novel queries):
  1. "Monsoon climate change extreme rainfall patterns"
  2. "Southwest monsoon agriculture production impact India"
  3. "Monsoon weakening ENSO relationship warm current"
```

**Query Generation Logic:**
```python
async def _generate_exploratory_queries(skeleton, gemini_client):
    prompt = """
Given this question skeleton:
  Concept: {concept}
  Sub-concepts: {sub_concept_topics}
  Aspects: {aspects_covered}
  Difficulty: {difficulty_type}

Generate 3 NOVEL Pinecone queries exploring DIFFERENT angles:
- Different aspects (economic, historical, climate, policy)
- Inter-domain connections (concept + agriculture, concept + migration)
- New angles (extreme cases, case studies, recent events)
Avoid repeating sub_concepts above.

Return JSON: {"queries": ["query1", "query2", "query3"]}
"""
    response = await gemini_client.generate_response(
        user_prompt=prompt,
        response_schema=ExploratoryQueriesResponse,
        temperature=0.7
    )
    return response.queries
```

**Advantages:**
- Generic — works for ANY subject/concept
- Context-aware — LLM sees skeleton constraints
- Creative — finds angles we wouldn't hardcode
- No JSON dependency — just concept + skeleton

---

## Retrieval Pipeline

### Per Query (13 total: 10 structured + 3 exploratory)

```
Query Text
  ↓
Pinecone Query:
  - fetch_k = 20 (over-fetch for high recall)
  - k = 5 (final selection)
  - re_rank = True (cross-encoder)
  - filter: remove PYQ
  ↓
Cross-Encoder Re-Ranking:
  All 20 candidates scored by relevance
  ↓
MMR with RANDOMIZED Lambda:
  - 30% probability: lambda=0.7 (high relevance, tight)
  - 40% probability: lambda=0.5 (balanced)
  - 30% probability: lambda=0.3 (high diversity, exploratory)
  ↓
Final Selection:
  5 chunks per query
  Tracked with source query metadata
  ↓
SQLite Enrichment:
  Full text content retrieval (if available)
```

### Chunk Budget

```
Structured queries:  10 × 5 chunks = 50 chunks
Exploratory queries: 3 × 5 chunks = 15 chunks
────────────────────────────────────────────────
TOTAL:              65 chunks
```

**Why 65, not deduplicate?**
- Rich context for Stage 3 LLM
- Semantic dedup already happened per-query (via MMR)
- Structured + exploratory diversity is intentional
- Reduces risk of missing relevant angles

---

## CA (Current Affairs) Handling

### 70% Structured CA Queries
```
Query 1: skeleton.ca_event (if present)
         "{ca_event} {concept} India 2024 2025 official"

Query 2: Government source anchor
         "site:pib.gov.in OR site:indiabudget.gov.in {concept} {topic}"
```

### 30% Exploratory CA Queries
```
Query 3: Recent developments
         "{concept} latest developments 2024 2025 news India"

Query 4: Policy impact
         "{concept} policy impact implementation India current"
```

**Total CA context:** Merged summaries from 4 queries

---

## Randomized MMR Lambda

### Why Randomize?
- **Structured queries (70% structured)** benefit from tight relevance (0.7-0.8)
- **Exploratory queries (30% exploratory)** benefit from diversity (0.3-0.5)
- Randomization adds variation without fixed rules

### Distribution
```python
def _pick_random_mmr_lambda():
    r = random.random()
    if r < 0.30:
        return 0.7  # High relevance (tight)
    elif r < 0.70:
        return 0.5  # Balanced
    else:
        return 0.3  # High diversity (exploratory)
```

### Per Query Metadata Tracking
```python
query_metadata = [
    {
        "query_text": "Monsoon mechanism distribution",
        "is_exploratory": False,
        "mmr_lambda": 0.5,
        "chunk_count": 5,
        "enriched_count": 4,
    },
    ...
]
```

---

## Data Flow

```
┌─ Stage 0 (v4.5 Controlled) ──────────────────┐
│ Output: QuestionSkeleton                     │
│   - concept, sub_concepts, difficulty_type   │
│   - available_trap_ids, available_question_types
└──────────────────────────────────────────────┘
       ↓
┌─ QUERY GENERATION ───────────────────────────┐
│ 70% Structured:                              │
│   _build_structured_queries(skeleton)        │
│   → ~10 queries from sub_concepts            │
│                                              │
│ 30% Exploratory:                             │
│   _generate_exploratory_queries(skeleton)    │
│   → LLM generates 3 novel queries            │
└──────────────────────────────────────────────┘
       ↓ (13 queries total)
┌─ PINECONE RETRIEVAL ─────────────────────────┐
│ For each query:                              │
│   1. Embed query (batch: 1 API call for all) │
│   2. Fetch 20 candidates (over-fetch)        │
│   3. Cross-encode re-rank                    │
│   4. MMR select 5 (randomized lambda)        │
│   5. Enrich from SQLite content_store        │
│                                              │
│ Result: 13 × 5 = 65 chunks                  │
└──────────────────────────────────────────────┘
       ↓
┌─ DEDUPLICATION ──────────────────────────────┐
│ NO FINAL DEDUP — keep all 65 chunks          │
│ (per-query MMR already ensured diversity)    │
└──────────────────────────────────────────────┘
       ↓
┌─ CA SEARCH (if ca_flag) ─────────────────────┐
│ Query 1-2: Structured (event + gov sources)  │
│ Query 3-4: Exploratory (news + policy)       │
│                                              │
│ Result: ca_context (merged summaries)        │
└──────────────────────────────────────────────┘
       ↓
┌─ OUTPUT ─────────────────────────────────────┐
│ RetrievalResult:                             │
│   - 65 static_chunks (rich context)          │
│   - ca_context (if applicable)               │
│   - query_metadata (trace which query)       │
└──────────────────────────────────────────────┘
       ↓
Stage 3 Generation (LLM receives rich, diverse context)
```

---

## Code Changes Summary

### New Functions
1. **`_generate_exploratory_queries(skeleton, gemini_client)`**
   - LLM generates 3 novel queries
   - Generic, no JSON dependency
   - Returns `List[str]`

2. **`_pick_random_mmr_lambda()`**
   - Randomize MMR lambda (0.7 | 0.5 | 0.3)
   - Adds diversity without fixed rules

3. **`_build_structured_queries(skeleton)`**
   - Renamed from `_build_pinecone_queries`
   - Marks queries as `is_exploratory=False`

### Modified Functions
1. **`_retrieve_from_pinecone(...)`**
   - Now handles mixed structured + exploratory queries
   - Returns `(chunks, query_metadata)` tuple
   - Randomizes MMR lambda per query
   - Keeps all 65 chunks (no final dedup)

2. **`retrieve_for_skeleton(...)`**
   - Calls both `_build_structured_queries` and `_generate_exploratory_queries`
   - Combines queries before retrieval
   - Updates CA search to be 70/30 as well

3. **`_build_ca_search_queries(...)`**
   - Now generates 4 queries (2 structured, 2 exploratory)
   - Latest news + policy impact angles

### New Data Class Fields
1. **`RetrievalResult.query_metadata`**
   - List of metadata dicts per query
   - Tracks: query_text, is_exploratory, mmr_lambda, chunk_count, enriched_count

2. **`ExploratoryQueriesResponse` (Pydantic)**
   - LLM response schema
   - `queries: List[str]`

---

## Metrics & Logging

### Per-Query Logging
```
[Stage1] [structured] concept='Monsoon' | query='Monsoon mechanism distribution' → 5 chunks (lambda=0.5, enriched=4)
[Stage1] [exploratory] concept='Monsoon' | query='Monsoon climate change precipitation' → 5 chunks (lambda=0.3, enriched=3)
```

### Retrieval Complete Logging
```
[Stage1] {skeleton_id} | Pinecone retrieval complete: 65 chunks from 13 queries
  (10 structured, 3 exploratory, difficulty_type='hard_cross_domain_linking')
```

### CA Search Logging
```
[Stage1][CAQuery] {skeleton_id} | 4 CA search queries (2 structured, 2 exploratory):
  [1] [structured] {ca_event} {concept} ...
  [2] [structured] site:pib.gov.in OR site:indiabudget.gov.in ...
  [3] [exploratory] {concept} latest developments 2024 2025 ...
  [4] [exploratory] {concept} policy impact implementation ...
```

---

## Example: Monsoon Question

### Stage 0 Skeleton
```
concept: "Monsoon"
sub_concepts: [
  {topic: "SW monsoon tracking", aspect: "mechanism"},
  {topic: "Precipitation patterns", aspect: "distribution"}
]
difficulty_type: "hard_cross_domain_linking"
ca_flag: True
```

### Stage 1 Queries Generated

**70% Structured:**
1. "Monsoon SW monsoon tracking" (own concept, mechanism)
2. "Monsoon Precipitation patterns" (own concept, distribution)

**30% Exploratory (LLM):**
3. "Monsoon climate change extreme rainfall patterns"
4. "Southwest monsoon agriculture production impact India"
5. "Monsoon ENSO relationship warm current linkage"

### Stage 1 Output
```
65 chunks total:
  - 50 from structured queries (focused on mechanism + distribution)
  - 15 from exploratory queries (climate, agriculture, ENSO angles)

CA context (4 queries):
  - News about monsoon 2024-2025 performance
  - Government policies on monsoon monitoring
  - Recent developments in monsoon prediction
  - Policy impacts on agriculture

→ Stage 3 LLM gets RICH, DIVERSE context
  Can write questions on unexpected angles:
    "Which is the CORRECT statement about SW monsoon..."
    "Monsoon-driven migration patterns VERSUS agriculture productivity"
    "ENSO-monsoon coupling in extreme weather years"
```

---

## Benefits

✅ **Structured Quality** — 70% respects skeleton constraints
✅ **Exploratory Diversity** — 30% discovers novel corpus angles
✅ **Generic** — LLM works for ANY subject, no JSON dependency
✅ **Rich Context** — 65 chunks gives Stage 3 massive exploration room
✅ **Traceable** — Query metadata shows origin of each chunk
✅ **Controlled Randomness** — Randomized lambda adds variation
✅ **Current Affairs** — 2 structured + 2 exploratory CA queries
✅ **Cost Efficient** — 1 batch embedding call for all queries

---

## Integration Checklist

- [x] Implement `_generate_exploratory_queries` (LLM query generator)
- [x] Implement `_pick_random_mmr_lambda` (randomization)
- [x] Rename `_build_pinecone_queries` → `_build_structured_queries`
- [x] Update `_retrieve_from_pinecone` to handle mixed queries + randomized lambda
- [x] Update `retrieve_for_skeleton` to combine structured + exploratory
- [x] Update `_build_ca_search_queries` to be 70/30
- [x] Add `query_metadata` tracking
- [x] Return all 65 chunks (no final dedup)
- [ ] Test end-to-end (Stage 0 → Stage 1 → Stage 3)
- [ ] Verify LLM query generation quality
- [ ] Monitor chunk count distribution (structured vs exploratory)
- [ ] Profile API costs (Gemini LLM calls for query generation)

---

## Next Steps

1. **Test with 30 Monsoon questions**
   - Check LLM query generation quality
   - Verify 65 chunks returned
   - Inspect query_metadata distribution

2. **Compare Stage 3 output**
   - Do exploratory chunks lead to better questions?
   - Are inter-domain angles covered?
   - Question diversity vs pure structured

3. **Monitor costs**
   - Gemini LLM cost for exploratory query generation
   - Embedding costs (1 batch call savings)
   - Pinecone query cost (13 queries per skeleton)

4. **Production deployment**
   - Seed randomization for reproducibility
   - Cache exploratory queries per concept
   - Add circuit breaker if LLM fails (fallback to structured only)
