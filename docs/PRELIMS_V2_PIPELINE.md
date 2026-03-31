# UPSC Prelims V2 Pipeline — Exact Flow for 5 Questions

> Subject: Geography → Climatology | `num_questions = 5`  
> All numbers below are **exact** for a typical 5-question run.

---

## High-Level Sequence

```
User clicks "Start Mock Test"
        ↓
POST /mock-test/generate-async
        ↓  (enqueues ARQ job)
generate_mock_test_v2_task (worker.py)
        ↓
run_v2_pipeline (pipeline.py)
        ├── Stage 0  Blueprint       — 1 Gemini Flash call
        ├── Stage 1  Retrieval       — 1 embed batch + 5–10 Pinecone calls + 0–2 Google Search calls
        ├── Stage 2  Difficulty      — pure Python, 0 API calls
        ├── Stage 3  Generation      — 5 Gemini Pro calls (parallel, semaphore=5)
        ├── Stage 4  Quality Gate    — cosine similarity, 0 API calls
        └── Stage 5  Gap Fill        — 0–N Gemini Pro calls for failed questions
```

---

## Stage 0 — Blueprint (1 Gemini Flash call)

### Input
```
num_questions : 5
subject       : Geography
domain        : Physical Geography
subdomain     : Climatology
concept_pool  : geography_climatology.json  (15 concepts, each with sub_concepts + trap_affinity + links_to)
trap_registry : traps_geography.json        (10 traps: GEO_T01–GEO_T10)
```

### What the LLM receives
A single system prompt (~3000 tokens) structured as:

```
CONCEPT: Monsoon
  own sub_concepts: "Southwest monsoon onset mechanism" [aspect=process] ...
  borrowable sub_concepts from other concepts:
    FROM "Jet Streams" (set source_concept="Jet Streams"):
      - "Subtropical westerly jet stream in winter over India" [aspect=process]
      ...
  VALID trap_ids for this concept: GEO_T06, GEO_T04
  ca_trigger_types: "IMD below-normal monsoon forecast 2024"

CONSTRAINTS:
  num_questions: 5
  difficulty: easy=1, medium=3, hard=1
  ca_linked: exactly 1 question must have ca_linked=true

RULES:
  - trap_id MUST come from that concept's valid list
  - Sub_concepts: pick 2–3, can borrow from any listed concept, set source_concept
  ...
```

### Output — 5 `QuestionSkeleton` objects
```json
[
  {
    "skeleton_id": "sk_001",
    "concept": "Monsoon",
    "question_type": "multi_statement",
    "difficulty": "medium",
    "trap_strategy": "GEO_T06",
    "ca_flag": false,
    "ca_event": "",
    "sub_concepts": [
      {"topic": "Southwest monsoon onset mechanism",          "aspect": "process",  "source_concept": ""},
      {"topic": "Subtropical westerly jet stream in winter", "aspect": "impact",   "source_concept": "Jet Streams"}
    ],
    "linked_concept": null
  },
  {
    "skeleton_id": "sk_003",
    "concept": "Tropical Cyclones",
    "question_type": "multi_statement",
    "difficulty": "medium",
    "trap_strategy": "GEO_T03",
    "ca_flag": true,
    "ca_event": "Named cyclone landfall in Bay of Bengal with damage data 2024",
    "sub_concepts": [
      {"topic": "Sea surface temperature above 26°C",        "aspect": "mechanism","source_concept": ""},
      {"topic": "Positive IOD enhancing Indian monsoon",     "aspect": "impact",   "source_concept": "Indian Ocean Dipole (IOD)"}
    ]
  }
  // ... 3 more skeletons
]
```

**API calls: 1** (Gemini Flash, ~3000 token prompt, ~800 token output)

---

## Stage 1 — Retrieval

### Step 1a: PYQ Style Examples (1 Pinecone call, shared)
```
query  : "UPSC Geography previous year questions"
filter : {source_type: "pyq", subject: "Geography"}
k      : 10
fetch_k: 10   (no re-ranking)
result : ~5–10 PYQ chunk objects (question + answer + explanation)
```
These are passed as style reference to EVERY question's generation prompt.

---

### Step 1b: Per-Skeleton Pinecone Retrieval

For **each skeleton**, we build one Pinecone query per unique `source_concept`:

#### Example: `sk_001` (Monsoon, 2 source_concepts)

| source_concept | topics joined | k | fetch_k |
|---|---|---|---|
| `Monsoon` (own) | `"Monsoon Southwest monsoon onset mechanism"` | 5 | 5 |
| `Jet Streams` (borrowed) | `"Jet Streams Subtropical westerly jet stream in winter"` | 3 | 3 |

**Batch embedding:** Both query texts embedded in **1 API call** (`embed_documents([q1, q2])` → 2 vectors from OpenAI).

**Pinecone calls:** 2 calls (one per query), each with pre-computed vector so no re-embedding inside the handler.

**Filter applied:**
```python
{"source_type": {"$ne": "pyq"}, "major_domain": {"$in": ["Monsoon", "Geography"]}}
```

**SQLite enrichment:** For each returned chunk, `content_store.get_chunk(chunk_id, filename)` fetches full text from local SQLite DB. Without this, only `content_preview` (first 200 chars) is available.

**Result for sk_001:**
```
8 chunks total (5 from Monsoon + 3 from Jet Streams)
All 8 enriched with full text from SQLite
```

---

#### Total Pinecone calls across 5 skeletons

| Skeleton | Concept | # source_concepts | Pinecone calls | Chunks fetched |
|---|---|---|---|---|
| sk_001 | Monsoon | 2 | 2 | 8 |
| sk_002 | Jet Streams | 1 | 1 | 5 |
| sk_003 | Tropical Cyclones | 2 | 2 | 8 |
| sk_004 | Rainfall Types | 2 | 2 | 8 |
| sk_005 | El Niño / La Niña | 1 | 1 | 5 |
| **Total** | | | **8** | **34** |

**Embedding API calls: 3** (batch per concurrent skeleton group — semaphore=10 so usually 1–3 batches)  
**Pinecone API calls: 8** (same as above)

---

### Step 1c: CA Search (0–2 Google Search calls)

Only for skeletons where `ca_flag = true`. In 5Q, typically **1–2 skeletons** are CA-flagged.

#### Example: `sk_003` (Tropical Cyclones, ca_flag=true)

Queries built from `ca_event`:
```
[1] "Named cyclone landfall Bay of Bengal with damage data 2024 Tropical Cyclones India 2024 2025 official"
[2] "site:ncert.nic.in OR site:gov.in Tropical Cyclones Sea surface temperature above 26°C UPSC"
```

`gemini_client.search_and_summarise(queries)` fires:
- 1 Gemini Pro call (`use_google_search=True`)
- Gemini fetches 15–18 web results internally, synthesises them
- Returns ~1500–2500 chars of summarised factual text

**Output stored in `RetrievalResult.ca_context`.**

---

## Stage 2 — Difficulty + Trap Injection (0 API calls)

Pure Python. For each skeleton:

1. Loads `traps_geography.json` once (cached in `_trap_cache`)
2. Looks up `skeleton.trap_strategy` → finds the full `TrapRule` object
3. Creates `DifficultyBundle(skeleton=sk, trap_rule=trap, difficulty_instruction=<prose>)`

### What gets added

```python
TrapRule(
    trap_id   = "GEO_T06",
    trap_name = "False Causation",
    mechanism = "Student knows both facts but assumes one causes the other",
    how_to_generate = "State A and B as true, imply A→B but make the reason subtly wrong",
    real_pyq_example = "UPSC 2019: Monsoon and IOD question..."
)
```

**No API calls. ~5ms total.**

---

## Stage 3 — Question Generation (5 Gemini Pro calls)

One LLM call per skeleton. All 5 run concurrently (semaphore=5).

### Prompt structure per question (~2500–4000 tokens)

```
═══════════════════════════════════
QUESTION SPECIFICATION
  concept       : Monsoon
  question_type : multi_statement
  difficulty    : medium
  sub_concepts to test:
    - Southwest monsoon onset mechanism [aspect=process, own]
    - Subtropical westerly jet stream in winter [aspect=impact, from Jet Streams]

═══════════════════════════════════
SUBJECT FRAMEWORK
  [Geography cognitive framework: spatial, causal, process-based reasoning...]

═══════════════════════════════════
DIFFICULTY: MEDIUM
  - At least one distractor must be partially true
  - Use qualifier traps: "always" vs "usually"...

═══════════════════════════════════
TRAP STRATEGY TO USE: False Causation
  Mechanism: Student knows both facts, assumes wrong causal link
  How to build: State A and B as true, imply A→B but reason is subtly wrong
  Real UPSC example: [...]

═══════════════════════════════════
STATIC CONTENT (factual grounding):
[Chunk 1 — Monsoon]
  The southwest monsoon arrives in Kerala typically in late May or early June...
[Chunk 2 — Monsoon]
  The ITCZ shifts northward during summer, the subtropical jet stream retreats...
[Chunk 3 — Jet Streams]
  The subtropical westerly jet stream at ~200 hPa level plays a critical role...
...
[8 chunks total, each SQLite-enriched, ~400–600 chars each]

═══════════════════════════════════
PYQ STYLE REFERENCE:
  [2 PYQ examples matching multi_statement type]

═══════════════════════════════════
OUTPUT FORMAT:
{ "question": "...", "options": [...], "correct_answer": "B", "explanation": "..." }
```

### Output per skeleton
```json
{
  "question": "Consider the following statements regarding Indian monsoon:\n1. The onset of SW monsoon over Kerala is influenced by...\n2. The subtropical westerly jet stream shifts poleward before...\n3. ...\nWhich of the statements given above is/are correct?",
  "options": ["(a) 1 only", "(b) 1 and 2 only", "(c) 2 and 3 only", "(d) 1, 2 and 3"],
  "correct_answer": "B",
  "explanation": "Statement 1 is correct because... Statement 2 is correct because... The trap here is Statement 3: students assume the jet stream causes monsoon onset directly (False Causation trap), but the actual mechanism is...",
  "source": {"concept": "Monsoon", "sub_domain": "Climatology", "trap_used": "GEO_T06"}
}
```

**API calls: 5** (Gemini Pro, ~2500–4000 token prompt, ~500–800 token output each)

---

## Stage 4 — Quality Gate (0 API calls)

For each generated question:
- Checks `len(question) > 50`
- Checks `correct_answer in {A, B, C, D}`
- Checks `len(options) == 4`
- (Optional) cosine similarity between question embedding and skeleton concept — flags if score < 0.3

Passes: ~4–5 of 5  
Failed IDs collected for Stage 5.

---

## Stage 5 — Gap Fill (0 to N Gemini Pro calls)

If Stage 4 passes ≥ `num_questions` → shuffles and returns.  
If some failed → regenerates failed questions with a simpler prompt (no cross-concept borrowing, easy fallback).

For a healthy run: **0 additional calls**.

---

## Total API Calls for 5 Questions

| API | Provider | Count | Notes |
|---|---|---|---|
| Blueprint | Gemini Flash | **1** | ~3000 token in, ~800 token out |
| Embed (Pinecone queries) | OpenAI | **2–3** | Batch embed per concurrent group |
| PYQ fetch | Pinecone | **1** | k=10, filter by source_type=pyq |
| Chunk retrieval | Pinecone | **6–10** | 1–2 queries per skeleton |
| SQLite enrichment | Local DB | **34** | One read per chunk, ~zero latency |
| CA search | Gemini Pro + Google | **0–2** | Only for ca_flagged skeletons |
| Question generation | Gemini Pro | **5** | One per skeleton, parallel |
| **Total external calls** | | **15–22** | |

---

## Token budget per question (Stage 3)

| Section | Approx tokens |
|---|---|
| Specification + difficulty rules | ~300 |
| Subject cognitive framework | ~400 |
| Trap injection block | ~300 |
| Static chunks (8 × 500 chars) | ~1000 |
| CA context (if ca_flag) | ~400 |
| PYQ style examples (2 × 300) | ~200 |
| Output format template | ~150 |
| **Total prompt** | **~2350–3000** |
| Output (question + explanation) | ~500–800 |

---

## Key Areas for Improvement

| Area | Current | Improvement |
|---|---|---|
| **Chunk quality** | Filter by major_domain only | Add sub_domain + aspect-aware filter |
| **Cross-concept retrieval** | Fetches 3 chunks from borrowed concept | Could rank by semantic overlap with the specific sub_concept topic |
| **CA context quality** | Google search summary | Could cache by ca_event hash to avoid re-fetching same event |
| **Generation temperature** | 0.85 | Could lower for easy questions, raise for hard A/R |
| **Quality gate** | Basic structural checks | Add semantic dedup — reject if cosine(question, previous_question) > 0.85 |
| **Concept pool** | Climatology done | Polity, History, Economy concept pools needed |
| **Fallback chunks** | content_preview if no SQLite | Improve SQLite coverage to reduce fallbacks |
