# UPSC Prelims V2 Pipeline — Complete Flow (v4)

> Subject: Geography → Climatology | `num_questions = 5`  
> All numbers are **exact** for a typical 5-question run.

---

## Architecture Overview

```
POST /mock-test/generate-async  →  Arq worker  →  run_v2_pipeline()

  ┌─────────────────────────────────────────────────────────────────────┐
  │ Pre-pipeline: Load user concept ledger from Redis (if user_id)     │
  └─────────────────────────────────────────────────────────────────────┘
            ↓
  ┌─ Stage 0 ──────────────────────────────────────────────────────────┐
  │ Blueprint (v4 — Python pre-sampling + LLM slot completion)        │
  │   Step 1: Python pre-samples concept, sub_concepts, trap, diff    │
  │   Step 2: Gemini Flash assigns question_type + ca_event only      │
  │   Fallback: rule-based fallback reuses pre-sampled slots          │
  └─────────────────────────────────────────────────────────────────────┘
            ↓  5 QuestionSkeletons
  ┌─ Stage 1 ──────────────────────────────────────────────────────────┐
  │ Retrieval (3-phase: over-fetch → re-rank → MMR)                   │
  │   1. Batch embed all queries in 1 API call                        │
  │   2. Over-fetch 3x from Pinecone per query                        │
  │   3. Cross-encoder re-ranks to target_k                           │
  │   4. Client-side MMR (λ=0.6) selects diverse final set            │
  │   5. SQLite full-text enrichment                                  │
  │   + Google Search for CA-flagged skeletons                        │
  └─────────────────────────────────────────────────────────────────────┘
            ↓  5 RetrievalResults (≤10 chunks each)
  ┌─ Stage 2 ──────────────────────────────────────────────────────────┐
  │ Difficulty + Trap Injection (pure Python, 0 API calls)            │
  └─────────────────────────────────────────────────────────────────────┘
            ↓  5 DifficultyBundles
  ┌─ Stage 3 ──────────────────────────────────────────────────────────┐
  │ Generation — 5 parallel Gemini Pro calls                          │
  │   Temperature: easy=0.50, medium=0.75, hard=0.90                  │
  └─────────────────────────────────────────────────────────────────────┘
            ↓  5 V2GeneratedQuestions
  ┌─ Stage 4 ──────────────────────────────────────────────────────────┐
  │ Quality Gate (5 checks, embedding-powered)                        │
  │   1. Structural   2. Trap presence   3. CA in stem                │
  │   4. Distractor plausibility (cosine range 0.40–0.92)             │
  │   5. Semantic dedup (cosine < 0.85)                               │
  └─────────────────────────────────────────────────────────────────────┘
            ↓
  ┌─ Stage 5 ──────────────────────────────────────────────────────────┐
  │ Gap Fill — regenerate failed questions, shuffle, return            │
  └─────────────────────────────────────────────────────────────────────┘
            ↓
  ┌─ Post-pipeline: Save updated concept ledger to Redis              │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## Pre-Pipeline: User Concept Ledger

If `user_id` is present in the request, loads `ledger:{user_id}:{subject}:{subdomain}` from Redis.

```json
{
  "concepts_seen": {
    "Monsoon": {"count": 3, "traps_used": ["GEO_T04","GEO_T06"], "sub_concepts_used": ["SW monsoon onset"], "last_seen": "2026-03-30"}
  },
  "traps_exhausted": ["GEO_T04"],
  "total_questions_seen": 15
}
```

**Effect on Stage 0:**
- Heavily-tested concepts (`count ≥ 2`) → weight reduced in random selection
- Exhausted traps → excluded from trap candidate pool
- Fresh concepts → boosted in weighted pool
- TTL: 30 days, refreshed on every read/write

---

## Stage 0 — Blueprint (v4: Pre-Sampled Slots)

### What changed in v4
Previously, the LLM chose everything (concept, sub_concepts, trap, question_type, difficulty). Now **Python controls diversity**, and the LLM only decides question_type + ca_event.

### Step 1: Python Pre-Sampling (`_pre_sample_slots`)

**Input:**
```
concept_pool  : geography_climatology.json (14 concepts, dict-keyed, auto-normalised)
trap_registry : traps_geography.json (10 traps)
ledger        : user's past test history (optional)
num_questions : 5
```

**What Python samples for each slot:**

| Ingredient | How it's chosen |
|---|---|
| **Concept** | Priority-weighted random pool (`high=3x`, `medium=2x`, `low=1x`). Ledger downgrades heavily-seen concepts. Each concept capped at max 3 uses. Min 5 unique concepts enforced. |
| **Difficulty** | Exact ratio from `SubjectConfig` (e.g. easy=1, medium=3, hard=1). Shuffled randomly. |
| **Sub-concepts** | 2 random own sub_concepts per slot. Plus 0–1 linked sub_concept from a connected concept (probability: easy=0%, medium=40%, hard=80%). |
| **Trap** | Filtered by concept's `trap_affinity`. Exhausted traps excluded. Least-used-this-session preferred. |
| **CA flag** | `ca_linkage_rate` from config → typically 1–2 of 5 slots flagged. |

**Output:** 5 slot dicts with all ingredients pre-assigned.

### Step 2: LLM Completion (1 Gemini Flash call)

The LLM receives a compact prompt showing pre-assigned slots and only fills:

```json
{
  "completions": [
    {
      "id": "Q1",
      "question_type": "multi_statement",
      "ca_event": "IMD issued below-normal monsoon forecast for 2024...",
      "linked_concept": null,
      "swap_sub_concept": null
    }
  ]
}
```

The LLM **can** swap one sub_concept if the combination is incoherent, but cannot add concepts or traps.

### Fallback
If Flash fails → `_rule_based_fallback()` reuses the **same pre-sampled slots**, assigns question_type by difficulty heuristic. Diversity is preserved even without LLM.

**API calls: 1** (Gemini Flash) | **Output: 5 `QuestionSkeleton` objects**

---

## Stage 1 — Retrieval (3-Phase Pipeline)

### Phase 1: Batch Embedding

All query texts across all sub-queries for a skeleton are embedded in **1 `embed_documents()` call**.

```
Skeleton sk_001 (Monsoon, 2 source_concepts):
  Query 1: "Monsoon Monsoon Onset Monsoon Variability" (own, k=5)
  Query 2: "Jet Streams Subtropical Jet"               (borrowed, k=3)
  → embed_documents(["query1", "query2"]) → 2 vectors in 1 API call
```

### Phase 2: Over-Fetch → Cross-Encoder Re-Rank (local model)

For each query:
1. **Over-fetch 3x:** `fetch_k = target_k × 3` (e.g. k=5 → fetch 15 candidates)
2. **Cross-encoder re-rank:** `re_rank=True` → local `cross-encoder/ms-marco-MiniLM-L-6-v2` scores all 15 by relevance, returns top 5. **0 API calls — runs on CPU.**
3. **Pre-computed vector:** `query_vector=vec` passed to handler → skips re-embedding

```
Query: "Monsoon Monsoon Onset Monsoon Variability"
  Pinecone fetch_k=15 → 15 candidates
  Cross-encoder re-rank → top 5 returned
  Filter: {source_type: {$ne: "pyq"}, major_domain: {$in: ["Monsoon", "Geography"]}}
```

**Fuzzy fallback:** If < half target returned, retry without `major_domain` filter.

### Phase 3: Client-Side MMR

After all sub-queries complete, if total chunks > 10 (`_MAX_CHUNKS_TOTAL`):

```python
pinecone_handler.mmr_select_from_chunks(
    chunks      = all_chunks,      # e.g. 13 chunks from 2 queries
    query_text  = combined_query,  # joined query texts
    k           = 10,              # hard cap
    lambda_mult = 0.6,             # 60% relevance, 40% diversity
)
```

This ensures the final 10 chunks are both relevant **and** diverse (no duplicate-ish chunks from overlapping queries).

### Phase 4: SQLite Enrichment

Each chunk → `content_store.get_chunk(chunk_id, filename)` → replaces `content_preview` (200 chars) with full text.

### CA Search (for CA-flagged skeletons)

2 Google Search queries via `gemini_client.search_and_summarise()`:
1. Event-anchored: `"IMD below-normal monsoon forecast 2024 Monsoon India 2024 2025 official"`
2. Static grounding: `"site:ncert.nic.in OR site:gov.in Monsoon ..."`

Returns ~1500–2500 chars of synthesised factual text.

### Concrete Numbers per Skeleton

| Source | Query count | fetch_k | After re-rank | After MMR |
|---|---|---|---|---|
| Own concept (k=5) | 1 | 15 | 5 | — |
| Borrowed concept (k=3) | 1 | 9 | 3 | — |
| **Per-skeleton total** | **2** | **24** | **8** | **≤10** |

### Total API Calls Across 5 Skeletons

| Call | Count | Notes |
|---|---|---|
| Embed batch | 2–3 | One per concurrent skeleton group |
| Pinecone (with re-rank) | 6–10 | 1–2 queries per skeleton |
| PYQ fetch (shared) | 1 | k=10, `source_type=pyq` |
| CA Google Search | 0–2 | Only ca_flagged skeletons |

---

## Stage 2 — Difficulty + Trap Injection (0 API calls)

Pure Python, ~5ms total.

For each skeleton → loads `TrapRule` from `traps_geography.json` → bundles into `DifficultyBundle`:

```python
DifficultyBundle(
    skeleton = QuestionSkeleton(...),
    trap_rule = TrapRule(
        trap_id    = "GEO_T06",
        trap_name  = "False Causation",
        mechanism  = "Student knows both facts, assumes wrong causal link",
        how_to_generate = "State A and B as true, imply A→B but reason is subtly wrong",
        real_pyq_example = "UPSC 2019: ..."
    ),
    difficulty_instruction = "At least one distractor must be partially true..."
)
```

---

## Stage 3 — Generation (5 Gemini Pro calls, parallel)

All 5 run concurrently (semaphore=5).

### Temperature by Difficulty

| Difficulty | Temperature | Rationale |
|---|---|---|
| Easy | 0.50 | Clean, predictable output |
| Medium | 0.75 | Balanced |
| Hard | 0.90 | Creative trap constructions |

### Prompt Structure (~2500–4000 tokens)

```
QUESTION SPECIFICATION
  concept, question_type, difficulty, sub_concepts

SUBJECT COGNITIVE FRAMEWORK
  [Geography: spatial, causal, process-based reasoning]

DIFFICULTY INSTRUCTION
  [Prose rules matching the difficulty tier]

TRAP STRATEGY
  [Full TrapRule: mechanism + how_to_generate + real_pyq_example]

STATIC CONTENT (≤10 chunks, SQLite-enriched)
  [Chunk 1 — Monsoon: "The southwest monsoon..."]
  [Chunk 2 — Jet Streams: "The subtropical jet..."]
  ...

CA CONTEXT (if ca_flag)
  [Google Search summary: 1500–2500 chars]

PYQ STYLE REFERENCE
  [2 matching PYQ examples from Pinecone]

OUTPUT FORMAT
  {question, options, correct_answer, explanation, source}
```

### Output per skeleton
```json
{
  "question": "Consider the following statements regarding Indian monsoon...",
  "options": ["(a) 1 only", "(b) 1 and 2 only", "(c) 2 and 3 only", "(d) 1, 2 and 3"],
  "correct_answer": "B",
  "explanation": "Statement 1 is correct... The trap here is Statement 3 (False Causation)...",
  "source": {"concept": "Monsoon", "sub_domain": "Climatology", "trap_used": "GEO_T06"}
}
```

---

## Stage 4 — Quality Gate (5 checks)

### Check 1–3: Structural + Soft Checks (no API)

| Check | Type | Fails pipeline? |
|---|---|---|
| **Structural** | 4 options, valid answer letter, question >30 chars, explanation >20 chars | **Hard fail** |
| **Trap presence** | Trap keywords found in wrong options or explanation | Soft (marks `trap_verified`) |
| **CA in stem** | CA event keywords appear in question stem | Soft (marks `ca_in_stem`) |

### Check 4: Distractor Plausibility (local SBERT embeddings)

Embeds all correct answers + all wrong options using local SentenceTransformer, then checks cosine similarity:

```
For each question:
  correct_answer embedding ↔ each wrong option embedding
  
  sim > 0.92 → "near-copy" (bad: lazy copy-paste distractor)     → HARD FAIL
  sim < 0.40 → "unrelated filler" (only if option ≥ 5 words)     → HARD FAIL
  0.40–0.92  → "plausible but wrong" (good UPSC distractor)      → PASS ✅
```

Failed questions go to Stage 5 for regeneration.

### Check 5: Semantic Dedup

Embeds all question stems, checks pairwise cosine similarity:
- `sim ≥ 0.85` between any two → drops the duplicate, sends to gap fill

### API Calls: 0 (local SBERT model — no external API)

The `_embed_texts()` helper auto-detects embedder type:
- `Embedder` (custom class) → calls `get_embeddings()` → SBERT fallback for quality gate
- LangChain wrapper → calls `embed_documents()`

---

## Stage 5 — Gap Fill & Shuffle (0–N API calls)

If all 5 pass → shuffle and return. Otherwise:
- Downgrades failed skeletons to easier difficulty
- Drops CA requirement
- Regenerates with cached chunks (no re-retrieval)

For a healthy run: **0 additional calls**.

---

## Post-Pipeline: Save Concept Ledger

After Stage 5 completes, `merge_and_save_ledger()` writes updated history to Redis:

```
For each skeleton generated:
  concepts_seen[concept].count += 1
  concepts_seen[concept].traps_used += [trap_id]
  concepts_seen[concept].sub_concepts_used += [topics]
  
Recalculate traps_exhausted (any trap used ≥ 3 times globally)
Save to Redis: ledger:{user_id}:{subject}:{subdomain} (TTL 30 days)
```

**Next run:** Stage 0 reads this ledger → biases toward fresh concepts, excludes exhausted traps.

---

## Total API Calls for 5 Questions

| API | Provider | Count | Notes |
|---|---|---|---|
| Blueprint (slots) | Gemini Flash | **1** | Compact prompt, ~1500 token in |
| Embed (retrieval queries) | OpenAI | **2–3** | Batch per concurrent group |
| PYQ fetch | Pinecone | **1** | k=10, shared |
| Chunk retrieval | Pinecone | **6–10** | 3x overfetch, re-rank is local |
| Cross-encoder re-rank | Local (CPU) | **0** | `ms-marco-MiniLM-L-6-v2` |
| MMR selection | Local (CPU) | **0** | Client-side diversity filter |
| CA search | Gemini + Google | **0–2** | CA-flagged only |
| Question generation | Gemini Pro | **5** | Parallel, temp by difficulty |
| Distractor check | Local SBERT | **0** | Cosine range 0.40–0.92 |
| Dedup check | Local SBERT | **0** | Cosine < 0.85 |
| Ledger load/save | Redis | **2** | GET + SET |
| **Total external API** | | **~15–17** | |

---

## Key Data Files

| File | Location | Purpose |
|---|---|---|
| `geography_climatology.json` | `prelims_v2/concept_pools/` | 14 concepts with sub_concepts, trap_affinity, links_to, priority |
| `traps_geography.json` | `prelims_v2/` | 10 trap definitions (GEO_T01–T10) |
| `history_prelims_pyq_patterns.json` | `config/` | PYQ pattern data for style reference |
| `content_store.db` | `data/databases/` | SQLite full-text content (chunk enrichment) |

---

## Improvement Areas

| Area | Current | Potential |
|---|---|---|
| **Concept pools** | Geography/Climatology done | Need Polity, History, Economy pools |
| **Cross-encoder model** | Uses PineconeHandler's built-in | Could swap in a tuned cross-encoder |
| **MMR fallback** | Hard cap at 10 chunks | Could vary by difficulty (easy=6, hard=12) |
| **CA caching** | Each run re-fetches | Cache by `ca_event` hash for 24h |
| **Distractor regen** | Hard fail → gap fill | Could do targeted distractor-only regen |
| **Quality gate** | Embedding-based only | Could add an LLM judge pass for hard questions |
| **SQLite coverage** | Some chunks miss full text | Improve ingestion to eliminate fallbacks |
