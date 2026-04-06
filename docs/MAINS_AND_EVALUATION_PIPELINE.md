# UPSC Mains Answer Generation & Evaluate Answer — Complete Pipeline

> Two fully-documented pipelines in this file:
> - **Pipeline A:** Mains Answer Generation (`POST /mains-answer/generate`)
> - **Pipeline B:** Answer Evaluation (`POST /evaluate-answer/`) + Improved Answer Generation (`POST /evaluate-answer/generate-improved`)

---

## Architecture Overview

Both pipelines use the same **Arq + Redis job queue** pattern:

```
Client  ──POST──►  FastAPI Route  ──enqueue──►  Arq Worker  ─────────────────────────────────────────────────────────────────────────────────────┐
                                                                                                                                                   │
   ◄── {job_id, status: "queued"} ──────────────────────────────────────────────────────────────────────────────────────────────────────────────── │
                                                                                                                                                   │
Client  ──GET── /status/{job_id}  ──Redis poll──►  job_status:{job_id}  ──────────► "queued" → "processing" → "completed" / "failed"             │
                                                                                                                                                   ▼
                                                                                               Worker runs pipeline task asynchronously
```

### Shared Infrastructure

| Component | Details |
|---|---|
| **Queue** | Arq (Python async job queue) |
| **Status store** | Redis keys: `job_status:{job_id}`, `job_result:{job_id}`, `job_error:{job_id}` |
| **Job TTL** | 1 hour (3600 s) |
| **Job timeout** | 15 min max (`job_timeout = 900`) |
| **Max retries** | 1 (no automatic retry on failure) |
| **Concurrency** | `max_jobs = 20`, user-level Redis lock (`lock:user:{user_id}`, timeout=600s) |
| **Gemini client** | Cached per `(api_key_prefix, model_name)` — avoids re-initialisation across jobs |
| **LangSmith** | `@trace_chain`, `@trace_gemini`, `@trace_retriever` decorators on all major functions |

---

## Pipeline A — Mains Answer Generation

```
POST /mains-answer/generate
        │
        ├─ Cache check (CacheManager)
        │      └─ HIT: return synthetic "completed" job instantly + write to Redis
        │      └─ MISS: continue
        │
        ├─ API key resolution (user key → system fallback)
        │
        └─ enqueue_job("generate_mains_answer_task")
                 │
                 └─ Arq Worker: generate_mains_answer_task()
                          │
                    ┌─────▼──────────────────────────────────────────────┐
                    │ Phase 1: Subject Blacklist Check (0 API calls)     │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Phase 2: Parallel Enriched Pipeline ──────────────┐
                    │  asyncio.gather(                                    │
                    │    timed_health_check()       ─ Map service         │
                    │    timed_retrieval()          ─ Pinecone + SQLite   │
                    │    fetch_news_dimension_research() ─ Gemini Search  │
                    │  )                                                  │
                    └─────────────────────────────────────────────────────┘
                             ↓  smart_truncate_with_token_budget(max=32k)
                    ┌─ Phase 3: Prompt Assembly ──────────────────────────┐
                    │  assemble_mains_prompt()                            │
                    │  + subject overlay + GS paper overlay               │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Phase 4: Gemini 2.5 Pro (User Locked) ─────────── ┐
                    │  temperature = 0.15, max_retries = 2, timeout 600s  │
                    │  cancellation watcher runs in parallel              │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Phase 5: Map Processing ───────────────────────────┐
                    │  parse_and_generate_maps() (if map service healthy) │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Phase 6: Compression (optional) ──────────────────┐
                    │  compress_answer()  ─ triggers at 1.5× word target  │
                    │  compresses to 1.3× word target via Gemini Flash    │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Phase 7: Cache & Save ─────────────────────────────┐
                    │  CacheManager.set_cached_answer()                   │
                    │  CacheManager.add_user_history()                    │
                    │  Redis: job_result:{job_id}                         │
                    └─────────────────────────────────────────────────────┘
```

---

### Pre-Pipeline: Cache Check (Route Level)

Before enqueuing anything, the route checks **Redis-backed semantic cache**:

```python
cache.get_cached_answer(question, word_count, model_version="gemini-2.5-pro-v1")
```

- **HIT**: Creates a synthetic job ID (`cached-{uuid}`), writes result directly to Redis as `completed`, returns `{job_id, status: "completed"}` to the frontend immediately.
- **MISS**: Proceeds to enqueue.

**Cache key**: Hash of `(question, word_count, model_version)`.

---

### Phase 1: Subject Blacklist Check (0 API calls)

`generate_mains_answer_task` checks whether the detected `subject` is blacklisted for Pinecone retrieval:

```python
blacklist_subjects = ["science", "science & tech", "science & technology", "ethics"]
```

- If subject matches any blacklist entry → `skip_vector_search = True`
- Reason: No vector data ingested for these domains yet; retrieval would return noise.
- For all other subjects: Pinecone retrieval is **enabled** by default.

---

### Phase 2: Parallel Enriched Pipeline (`run_enriched_pipeline`)

Three async coroutines run in **parallel** via `asyncio.gather()`:

#### 2a. Map Service Health Check

```python
await check_map_service_health()  # HTTP ping to internal map-service
```

Returns `True/False` — gates map JSON block processing in Phase 5.

#### 2b. Vector Retrieval (Pinecone + Cross-Encoder + SQLite)

```python
retrieve_context_for_question(
    search_query = query,          # Raw question text
    vector_handler = pinecone_handler,
    mode = "mains",
    use_content_store = True,       # SQLite enrichment
    k = 12,                        # Final doc count
    re_rank = True,                # Cross-Encoder re-ranking
    fetch_k = 30                   # Over-fetch candidates
)
```

**Steps inside retrieval:**

| Step | Detail |
|---|---|
| Over-fetch | Pinecone returns `fetch_k=30` candidates |
| Cross-encoder re-rank | Local `ms-marco-MiniLM-L-6-v2` scores all 30, returns top 12 — **0 external API calls** |
| SQLite enrichment | `content_store.get_chunk()` replaces `content_preview` with full text for each doc |
| Deduplication | `deduplicate_chunks(min_overlap_words=20, similarity_threshold=0.6)` removes near-duplicate passages |
| Source extraction | Extracts `(filename, chapter, section)` tuples; deduped, returned as `sources[]` |

**Fallback if `skip_vector_search=True`:** Returns `("", [])` — no retrieval, no API call.

#### 2c. Current Affairs Research (Dimension Pipeline)

```python
await fetch_current_affairs_for_question(
    question_text = query,
    max_bullets = 20,
    gemini_api_key = gemini_api_key
)
```

**Research pipeline (dimension-based):**

```
                   fetch_current_affairs_for_question()
                                │
                    ┌───────────▼────────────────────────────────────────┐
                    │ Cache Check: cache.get_cached_research(question)   │
                    │   → HIT: return cached bullets immediately          │
                    │   → MISS: continue                                  │
                    └─────────────────────────────────────────────────────┘
                                ↓
                    ┌───────────▼────────────────────────────────────────┐
                    │ Settings.USE_GEMINI_SEARCH_FOR_CURRENT_AFFAIRS     │
                    │                                                     │
                    │  True  → run_gemini_search_dimension_pipeline()    │
                    │           (Gemini 2.5 with Google Search tool)     │
                    │                                                     │
                    │  False → run_dimension_pipeline()                  │
                    │           (Legacy: Map + NewsAPI multi-dimension)  │
                    └─────────────────────────────────────────────────────┘
                                ↓
                    ┌───────────▼────────────────────────────────────────┐
                    │ Returns: List[str] — 30-40 word bullet points      │
                    │ Stored in Research Cache for future reuse          │
                    └─────────────────────────────────────────────────────┘
```

Results are formatted via `format_bullets_for_context()`:
```
**LATEST CURRENT AFFAIRS** (Recent developments - last 3 months):
• India launched National Forest Policy 2024 targeting 33% forest cover...
• Supreme Court ruled on compensatory afforestation guidelines...
```

#### Smart Truncation (Token Budget)

After `asyncio.gather()` completes, both context and current affairs are **token-budget truncated**:

```python
context_trim, current_trim = truncate_with_token_budget(
    static_context     = raw_context,
    current_affairs    = current_affairs_text,
    question           = query,
    system_prompt_tokens = 1500,    # Estimated system prompt
    max_total_tokens   = 32_000     # Conservative context window limit
)
```

Priority: question > current\_affairs > static\_context (trimmed last).

---

### Phase 3: Prompt Assembly

```python
prompt_pair = assemble_mains_prompt(
    question = query,
    context  = context,          # Static knowledge (Pinecone + SQLite)
    current_bullets = current_affairs_section,  # ≤20 bullets
    word_count = word_count,
    gs_paper = gs_paper,         # e.g. "GS1", "GS3"
    subject  = subject           # e.g. "Geography", "Polity"
)
# Returns: {"system": str, "user": str}
```

**System Prompt layers (via `prompt_assembler.py`):**

```
Base UPSC system prompt (IBC format, directive decoder, cognitive framework)
  + GS Paper overlay (gs_overlays/{gs_paper}.txt — maps, governance, economy rules)
  + Subject overlay (subject_overlays/{subject}.txt — domain-specific instructions)
```

**Directive decoder** (mandatory – always injected):

| Directive | Examiner expectation |
|---|---|
| Analyse | Break into components; show interconnections |
| Critically examine | Strengths + weaknesses; assess implications |
| Discuss | Balanced multi-dimensional treatment |
| Evaluate | Weigh positives/negatives; arrive at reasoned judgement |
| To what extent | Graded judgement (fully/partly/marginally) with justification |

**User message structure:**

```
QUESTION: {question}

━━━━━━━━━━━━━━━━━━
REFERENCE KNOWLEDGE BASE
━━━━━━━━━━━━━━━━━━
FOUNDATIONAL CONTEXT (Core concepts, mechanisms, theory):
{context_trim}

CURRENT AFFAIRS (Recent data, examples):
{current_trim}

ANSWER REQUIREMENTS:
- WORD COUNT: Target ~{word_count} words. Acceptable range: 80%–140%
- Format: IBC (Introduction → Body → [Way Forward] → Conclusion)
- At least ONE Mermaid diagram in body
- Each key point must cite report/data/example
```

---

### Phase 4: Gemini 2.5 Pro (User Locked Generation)

```python
async with redis.lock(f"lock:user:{user_id}", timeout=600, blocking_timeout=70):
    gemini_task = asyncio.create_task(
        gemini_client.generate_response(
            user_prompt    = prompt_pair["user"],
            system_prompt  = prompt_pair["system"],
            temperature    = 0.15,    # Low – consistency over creativity
            max_retries    = 2
        )
    )
    cancel_task = asyncio.create_task(watch_for_cancel())  # Polls cancel:{job_id}

    done, pending = await asyncio.wait(
        [gemini_task, cancel_task],
        return_when = asyncio.FIRST_COMPLETED
    )
```

- **User lock** (`lock:user:{user_id}`): prevents concurrent Gemini calls for same user (API quota/budget protection).
- **Cancellation watcher** checks `cancel:{job_id}` flag every 1 second during generation.
- If user calls `POST /mains-answer/cancel/{job_id}` → Redis flag set → watcher raises `CancelledError`.
- **Temperature 0.15**: low for consistent, exam-focused responses.

**Model**: `gemini-2.5-pro` (configured via `settings.GEMINI_MODEL_PRO`).

---

### Phase 5: Map Processing

If `map_service_healthy = True`:

```python
answer_text = await parse_and_generate_maps(answer_text)
```

- Scans answer for `\`\`\`map-json ... \`\`\`` blocks from Gemini output.
- Calls internal **map-service** to generate base64 PNG/SVG images.
- Replaces JSON spec blocks with `![Map](data:image/png;base64,...)` markdown.
- If map service down: replaces block with `*[Map generation unavailable]*` message.

---

### Phase 6: Answer Compression (Conditional)

```python
compressed = await compress_answer(
    original_answer         = answer_text,
    target_word_count       = word_count,
    gemini_client           = gemini_client,
    threshold_ratio         = 1.5,   # Trigger: answer > 150% of target
    compression_target_ratio = 1.2   # Compress to: 120% of target
)
```

**Compression pipeline:**

```
answer_text (e.g. 600 words, target 350)
    │
    ├─ Is 600 > 350 × 1.5 = 525?  YES → compress
    │
    ├─ Extract visuals → replace with <<MERMAID_0>>, <<MAP_JSON_0>>, <<IMAGE_0>> placeholders
    │      (saves ~40-60% tokens from base64 images)
    │
    ├─ Build COMPRESSION_PROMPT (target: 350 × 1.2 = 420 words)
    │      Rules: preserve IBC structure, keep bold formatting, keep domain keywords,
    │             shorten state names (UP, MP), remove filler phrases
    │
    ├─ Gemini 2.5 Pro call (temperature=0.1, timeout=60s)
    │
    └─ Restore placeholders back → final compressed answer
```

**Result storage:**
- If compressed: `job_result.answer = compressed_answer`, `job_result.compressed_answer = original_answer`
- If not compressed: `job_result.answer = original_answer`, `job_result.compressed_answer = None`

---

### Phase 7: Cache & Save

```python
cache.set_cached_answer(question, word_count, answer, sources, word_count_actual, model_version)
cache.add_user_history(user_id, question, word_count, answer_preview)
await set_job_result(redis, job_id, result)
```

**Final `job_result:{job_id}` payload:**
```json
{
  "question": "Discuss the role of geography in shaping India's monsoon...",
  "answer": "...(compressed or original)...",
  "compressed_answer": "...(original if compression happened, else null)...",
  "sources": [
    {"filename": "NCERT_Geography.pdf", "chapter": "4", "section": "Monsoon"},
    ...
  ],
  "word_count_actual": 389,
  "word_count_compressed": null
}
```

---

### API Calls Summary — Mains Answer Generation

| Step | Provider | Count | Notes |
|---|---|---|---|
| Cache check | Redis | **1** | GET before enqueue |
| Map health check | Internal HTTP | **1** | Parallel |
| Vector retrieval | Pinecone | **1** | Over-fetch k=30 |
| Cross-encoder re-rank | Local CPU | **0** | `ms-marco-MiniLM-L-6-v2` |
| SQLite enrichment | SQLite (local) | **0** | No external call |
| Current affairs | Gemini + Google Search | **1–2** | Dimension pipeline |
| Answer generation | Gemini 2.5 Pro | **1** | Core call |
| Compression (if needed) | Gemini 2.5 Pro | **0–1** | Triggered at 1.5× target |
| Map generation | Internal map-service | **0–N** | Per map-json block |
| Cache save + history | Redis | **2** | SET operations |
| **Total external API** | | **~5–8** | |

---

### Key Routes — Mains Answer

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/mains-answer/generate` | Enqueue generation (or instant cache hit) |
| `GET` | `/mains-answer/status/{job_id}` | Poll result |
| `POST` | `/mains-answer/cancel/{job_id}` | Set cancellation flag in Redis |
| `GET` | `/mains-answer/history` | Paginated user history (Redis-backed) |
| `GET` | `/mains-answer/history/answer` | Retrieve specific cached answer |

---

---

## Pipeline B — Answer Evaluation

Two sub-pipelines:
- **B1: Single Answer Evaluation** — Handwritten PDF/image → Feedback JSON
- **B2: Batch Answer Evaluation** — Multi-answer PDF → Parallel evaluation of all answers
- **B3: Improved Answer Generation** — Evaluation feedback → AI-generated improved answer

---

### B1: Single Answer Evaluation

```
POST /evaluate-answer/
        │
        ├─ Save uploaded files to backend/data/temp/{job_id}/
        │
        ├─ Upload to GCS (Cloud Run) or keep local (dev)
        │      → Returns storage paths: local path or gs:// URI
        │
        ├─ API key resolution
        │
        └─ enqueue_job("evaluate_answer_task")
                 │
                 └─ Arq Worker: evaluate_answer_task()
                          │
                    ┌─────▼──────────────────────────────────────────────┐
                    │ Step 0: Download from GCS (if gs:// path)          │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 1: Load Few-Shot Training Examples ──────────┐
                    │  data/training_examples.json → last 3 examples     │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 2: Build Evaluation Prompt ──────────────────┐
                    │  _build_evaluation_prompt() — combined OCR +       │
                    │  evaluation (single Gemini call)                   │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 3: Gemini 2.5 Pro (User Locked) ─────────── ┐
                    │  temperature = 0.1                                  │
                    │  use_google_search = True (grounding)              │
                    │  max_retries = 3                                    │
                    │  Input: PDF or image file(s)                       │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 4: Parse JSON Response ──────────────────────┐
                    │  _parse_evaluation_response()                      │
                    │  Extracts: question, marks, word_count, feedback   │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 5: Save Result ───────────────────────────────┐
                    │  Redis: job_result:{job_id}                         │
                    │  Cleanup: delete local temp files + GCS cleanup     │
                    └─────────────────────────────────────────────────────┘
```

---

### Step 0: GCS File Download

File paths can be:
- **Local** (`/path/to/file.pdf`): used directly
- **GCS** (`gs://bucket/folder/file.pdf`): downloaded to local temp first

```python
storage = get_storage_handler()
for file_path in file_paths:
    if file_path.startswith("gs://"):
        local_path = await storage.download_file(file_path)
    else:
        local_path = file_path
```

This allows **identical code** in local dev and Cloud Run.

---

### Step 1: Few-Shot Training Examples

```python
training_examples = load_training_examples(max_examples=3)
# Loads from: data/training_examples.json → last 3 entries
```

Format of each example:
```json
{
  "question": "Discuss the role of judiciary in upholding...",
  "student_answer": "The judiciary plays a pivotal role...",
  "ideal_feedback": "..."
}
```

Injected into prompt as `**FEW-SHOT EXAMPLES**` to guide feedback quality.

---

### Step 2: Evaluation Prompt Construction

**Single mode** (file-based — Gemini performs OCR):

```
TASK:
1. First, extract the QUESTION text from the uploaded file(s)
2. Extract MARKS (10 or 15) and WORD COUNT (150 or 250 words)
   - 10 marks = 150 words | 15 marks = 250 words
3. Then evaluate the student's handwritten answer

FEW-SHOT EXAMPLES:
  Example 1: [question preview] → [ideal feedback]
  Example 2: ...

REQUIREMENTS FOR EVALUATION:
1. Extract question/marks/word_count from files
2. Identify specific strengths
3. Point out missing elements (facts, examples, structure, visuals)
4. Actionable improvement suggestions
5. Comment on IBC format adherence and evidence usage
6. Assess directive alignment (if directive word present)
7. Comment on missing visuals (maps/diagrams/tables)
8. Overall encouraging assessment
9. GROUNDING RESEARCH (Google Search Tool): perform search for recent facts (2024–2026):
   - "Latest government policies related to {topic} (2024-2026)"
   - "Recent SC/HC judgments relevant to {topic}"
   - "Key international reports or summits related to {topic}"
   - "Recent news on significant developments in {topic}"

UPSC SYLLABUS ANCHOR: [syllabus.json injected] → Gemini identifies GS Paper + domain

TASK: Read the student's handwritten answer from the uploaded file and provide detailed feedback.
      Return ONLY valid JSON. No markdown code blocks.
```

**Key design decision:** OCR + evaluation happen in **one Gemini call** (no separate OCR step) — avoids doubling API cost and latency.

---

### Step 3: Gemini Evaluation (User Locked)

```python
async with redis.lock(f"lock:user:{user_id}", timeout=600, blocking_timeout=70):
    if all_is_pdf:
        response_text = await gemini_client.generate_response(
            user_prompt    = user_prompt,
            system_prompt  = get_evaluation_system_prompt(),
            pdf_path       = local_file_paths,   # Can be list of PDFs
            temperature    = 0.1,                # Very low for consistent JSON
            use_google_search = True,            # Grounding with Google Search
            max_retries    = 3
        )
    elif all_is_image:
        response_text = await gemini_client.generate_response(
            ...
            image_path = local_file_paths,
            ...
        )
```

**Gemini roles in this single call:**
1. **Vision/OCR** — reads handwritten answer from PDF/image
2. **Question extraction** — identifies exam question from answer booklet
3. **Marks/word count detection** — infers from context (10 marks = 150 words, 15 marks = 250 words)
4. **GS Paper classification** — maps to GS1/GS2/GS3/GS4 + primary/secondary domain
5. **Evaluation** — generates structured feedback JSON
6. **Google Search grounding** — searches for recent facts to validate evaluation

---

### Step 4: Response Parsing

```python
parsed_result = _parse_evaluation_response(response_text)
```

**JSON schema Gemini must return:**
```json
{
  "question": "extracted question text",
  "marks": 15,
  "word_count": 250,
  "paper_and_subject_identification": {
    "gs_paper": "GS1",
    "primary_domain": "Geography",
    "secondary_domain": ["Climatology"]
  },
  "feedback": {
    "examiner_expectation_blueprint": {
      "key_demands_of_the_question": ["..."],
      "ideal_logical_structure": {
        "introduction": "...",
        "body": "...",
        "conclusion": "..."
      },
      "non_negotiables": ["..."]
    },
    "strengths": ["..."],
    "critical_gaps_and_remedies": [
      {"gap": "...", "remedy": "..."}
    ],
    "section_wise_assessment": {
      "introduction": "...",
      "body": "...",
      "conclusion": "..."
    },
    "directive_alignment": {
      "directive_identified": "Discuss",
      "alignment_assessment": "...",
      "how_to_improve": "..."
    },
    "evidence_feedback": "...",
    "visual_feedback": "...",
    "strategy_tip": "...",
    "current_affairs_feedback": {
      "critical_misses": ["..."],
      "how_to_fix": ["..."]
    },
    "overall_assessment": "...",
    "margin_comments": ["..."]
  }
}
```

**Normalization rules:**
- `marks` must be 10 or 15; derived from `word_count` if ambiguous
- Consistency enforced: 10 marks ↔ 150 words, 15 marks ↔ 250 words
- If JSON parse fails → fallback minimal structure returned (no crash)

---

### Step 5: Result Saved to Redis

```json
{
  "question": "...",
  "student_answer": "Answer extracted by Gemini",
  "feedback": { ... },
  "word_count": 250,
  "marks": 15,
  "paper_and_subject_identification": { ... },
  "success": true
}
```

**File cleanup (always runs in `finally`):**
- Delete local temp files
- `os.rmdir()` temp job directory
- `storage.cleanup_job(job_id)` for GCS files (Cloud Run)
- `redis.delete(f"cancel:{job_id}")`

---

### B2: Batch Answer Evaluation

Handles multi-answer PDFs (up to 20 answers in one PDF upload):

```
POST /evaluate-answer/batch
        │
        ├─ Accepts: single PDF + optional question_file or questions JSON array
        │
        └─ enqueue_job("evaluate_batch_answers_task")
                 │
                 └─ Arq Worker: evaluate_batch_answers_task()
                          │
                    ┌─────▼──────────────────────────────────────────────┐
                    │ Step 0: Download PDF from GCS (if Cloud Run)       │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 1: Answer Splitting ──────────────────────────┐
                    │  answer_splitter.split_pdf_into_answers()          │
                    │  Splits by regex patterns (Q1, Q2, Answer 1, etc.) │
                    │  Output: list of answer segments (PDF or text)     │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 2: Question Matching ─────────────────────────┐
                    │  Match segments to questions (file or text array)  │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 3: Parallel Evaluation ───────────────────────┐
                    │  asyncio.Semaphore(BATCH_CONCURRENT_LIMIT=10)       │
                    │  _evaluate_single_answer_async() per segment       │
                    │  Real-time progress: job_batch_data:{job_id}       │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 4: Aggregate Results ─────────────────────────┐
                    │  {completed: N, failed: M, answers: [...]}         │
                    │  Status: "completed" / "partial_failed" / "failed" │
                    └─────────────────────────────────────────────────────┘
```

**Batch status polling** returns richer response:
```json
{
  "job_id": "...",
  "status": "processing",
  "batch_data": {
    "total_answers": 10,
    "completed_answers": 6,
    "failed_answers": 0,
    "answers": [
      {
        "answer_id": "a1",
        "question_number": 1,
        "status": "completed",
        "evaluation": { ... },
        "error": null
      },
      ...
    ]
  }
}
```

**Fatal error handling:**
- `429 / 401 / 403` from Gemini → `batch_cancelled = True` → **stops all remaining evaluations**
- Prevents runaway API spending. Reports partial results.

**Concurrency:** `asyncio.Semaphore(10)` — max 10 simultaneous Gemini calls for batch.

---

### B3: Improved Answer Generation

After evaluation, user can request an improved answer based on the feedback:

```
POST /evaluate-answer/generate-improved
  Fields: question, feedback (JSON), student_answer (text or files), word_count, paper_and_subject_identification
        │
        └─ enqueue_job("generate_improved_answer_task")
                 │
                 └─ Arq Worker: generate_improved_answer_task()
                          │
                    ┌─────▼──────────────────────────────────────────────┐
                    │ Step 0: Extract student answer text (if files)     │
                    │  Gemini OCR call (temperature=0.0) under user lock │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 1: Retrieval Pipeline ────────────────────────┐
                    │  run_enriched_pipeline() (same as Mains pipeline)  │
                    │  skip_current_affairs = True (Gemini tool instead) │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 2: Build Improved Answer Prompt ──────────── ┐
                    │  _build_improved_answer_prompt()                    │
                    │  Injects: question, student answer, feedback,       │
                    │           context, word_count                       │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 3: Gemini 2.5 Pro (User Locked) ─────────── ┐
                    │  temperature=0.15, max_retries=3                   │
                    │  use_google_search=True (integrated tool)          │
                    │  Can include student answer PDF/image in context   │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 4: Map Processing ────────────────────────────┐
                    │  parse_and_generate_maps() (if healthy)            │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 5: Compression (DISABLED) ────────────────── ┐
                    │  compressed_answer = None (explicitly disabled)     │
                    └─────────────────────────────────────────────────────┘
                             ↓
                    ┌─ Step 6: Save Result ───────────────────────────────┐
                    │  {improved_answer, sources, word_count_actual}      │
                    └─────────────────────────────────────────────────────┘
```

**Feedback sections injected into improved answer prompt:**

| Section | Content |
|---|---|
| `examiner_expectation_blueprint` | Key demands, ideal structure, non-negotiables |
| `directive_alignment` | Directive identified, alignment assessment, how to improve |
| `critical_gaps_and_remedies` | Gap → Remedy pairs |
| `current_affairs_feedback` | Critical misses, how to integrate |

**Subject blacklist** (same as Mains): Science & Tech, Ethics → skip Pinecone retrieval.

**Compression disabled** for improved answers (intentional — full richness preferred).

---

### API Calls Summary — Evaluation Pipeline

| Step | Provider | Single | Batch (10 answers) |
|---|---|---|---|
| File upload (GCS) | GCS | **1** | **1** |
| GCS download (worker) | GCS | **0–1** | **0–1** |
| Few-shot examples | Local file | **0** | **0** |
| OCR + Evaluation | Gemini 2.5 Pro | **1** | **10** (parallel, semaphore=10) |
| Google Search grounding | Google (via Gemini) | **included** | **included × N** |
| **Total external** | | **~2–3** | **~12–15** |

| Step | Provider | Improved Answer |
|---|---|---|
| OCR (student text extraction) | Gemini 2.5 Pro | **0–1** |
| Pinecone retrieval | Pinecone | **1** |
| Cross-encoder re-rank | Local CPU | **0** |
| Current affairs | Gemini + Google | **1–2** |
| Improved answer generation | Gemini 2.5 Pro | **1** |
| Map processing | Internal | **0–N** |
| **Total external** | | **~4–7** |

---

### Key Routes — Evaluation

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/evaluate-answer/` | Upload + enqueue single evaluation |
| `POST` | `/evaluate-answer/batch` | Upload multi-PDF + enqueue batch |
| `GET` | `/evaluate-answer/status/{job_id}` | Poll status (works for single + batch) |
| `POST` | `/evaluate-answer/cancel/{job_id}` | Cancel job |
| `POST` | `/evaluate-answer/generate-improved` | Generate improved answer from feedback |

---

## Data Flow Comparison

| Dimension | Mains Generation | Single Evaluation | Improved Answer |
|---|---|---|---|
| **Input** | Question text | PDF/image file(s) | Question + Feedback + optional file |
| **Retrieval** | Pinecone k=12 + re-rank | None (feedback-only) | Pinecone k=12 + re-rank |
| **CA Source** | Dimension pipeline | Google Search (in-prompt) | Gemini Google Search tool |
| **LLM calls** | 1 (+1 compression) | 1 | 1–2 (+OCR) |
| **Temperature** | 0.15 | 0.10 | 0.15 |
| **Output** | Markdown answer | Structured JSON feedback | Markdown improved answer |
| **Cache** | Redis semantic cache | None | None |
| **Map processing** | ✅ | ❌ | ✅ |
| **Compression** | ✅ (if 1.5× target) | ❌ | ❌ (disabled) |

---

## Key Data Files

| File | Location | Purpose |
|---|---|---|
| `training_examples.json` | `data/` | Few-shot evaluation examples (FIFO, last 3 used) |
| `syllabus.json` | `web/` | UPSC GS syllabus — injected for GS paper classification |
| `content_store.db` | `data/databases/` | SQLite full-text chunk store (enriches Pinecone retrieval) |
| `mains_prompt.py` | `app/prompts/` | Mains prompt assembler with IBC + directive decoder |
| `shared_mains_prompts.py` | `app/prompts/` | Evaluation system prompt, improved answer system prompt |
| `prompt_assembler.py` | `app/prompts/` | Dynamic prompt assembly with GS + subject overlays |
| `gs_overlays/` | `app/prompts/` | Per-GS-paper prompt overlays (GS1, GS2, GS3, GS4) |
| `subject_overlays/` | `app/prompts/` | Per-subject prompt overlays (Geography, Polity, etc.) |
| `answer_compressor.py` | `app/utils/` | Compression with visual placeholder extraction |
| `smart_truncator.py` | `app/utils/` | Token-budget-aware context truncation |
| `cache_manager.py` | `app/utils/` | Redis cache: answers, research bullets, user history |

---

## Improvement Areas

| Area | Current | Potential |
|---|---|---|
| **Retrieval for evaluation** | Skipped (feedback-only) | Add optional Pinecone retrieval to ground evaluation feedback with knowledge base |
| **Evaluation caching** | None | Cache feedback by `(question_hash, answer_hash)` for identical submissions |
| **Marks auto-detection** | Heuristic (10=150w, 15=250w) | Train a small classifier on UPSC question formats |
| **Batch OCR** | Per-answer Gemini call | Batch-embed extracted text first; call Gemini only for feedback |
| **Improved answer CA** | Google Search tool (per-call) | Cache research by question; reuse from mains answer generation |
| **Compression trigger** | Fixed 1.5× ratio | Dynamic ratio by word_count target (250w=1.3×, 500w=1.5×) |
| **LangSmith coverage** | All major functions traced | Add custom spans for token counts in each pipeline |
| **Map service fallback** | Unavailability message | Retry once with exponential backoff |
| **User lock timeout** | Fixed 600s | Adaptive per task type (evaluation faster than mains) |
