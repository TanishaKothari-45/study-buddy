# Pipeline Transformation: Old (0→2→3→4) → New (0→1→3→4)

**Date**: 2026-04-03 (Implementation Complete)

---

## Executive Summary

**Removed:** Stage 2 (pure data wrapping, redundant trap lookup)  
**Result:** Cleaner, faster, more transparent pipeline  

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Stages | 4 | 3 | -1 stage |
| Data Transformations | 5 | 4 | Removed wrapper |
| Trap Lookups | 2 | 1 | Consolidated in Stage 3 |
| API Calls | Same | Same | No perf loss |
| Context Available | Split | Unified | Better debugging |
| **Code Complexity** | **Higher** | **Lower** | **Cleaner** |

---

## Old Pipeline: Stage 0 → Stage 2 → Stage 3 → Stage 4

```
Stage 0 (v4.5 Controlled)
  ↓
  QuestionSkeleton {concept, sub_concepts, difficulty_type, trap_strategy, ...}

Stage 1 (LLM-Gen Retrieval)
  ↓
  RetrievalResult {static_chunks (65), ca_context, ca_queries}

Stage 2 (Difficulty Injection) ← REMOVED
  ├─ Load trap registry
  ├─ Look up trap_strategy
  ├─ Build difficulty_instruction prose block
  └─ Wrap in DifficultyBundle {skeleton, trap_rule, difficulty_instruction}
  ↓
  DifficultyBundle (data wrapper, nothing else)

Stage 3 (Generation)
  ├─ Load trap registry AGAIN (already loaded in Stage 2!)
  ├─ Assemble prompt
  └─ Call Gemini
  ↓
  List[GeneratedQuestion]

Stage 4 (Quality Gate)
  ├─ Trap presence check
  ├─ CA in stem check
  └─ Distractor quality
  ↓
  List[V2GeneratedQuestion] (final validated questions)
```

**Problem:** Stage 2 was a thin wrapper doing work that Stage 3 already does.

---

## New Pipeline: Stage 0 → Stage 1 → Stage 3 → Stage 4

```
Stage 0 (v4.5 Controlled)
  ↓
  QuestionSkeleton {concept, sub_concepts, difficulty_type, trap_strategy, 
                    available_trap_ids, available_question_types, ...}

Stage 1 (LLM-Gen Exploratory Retrieval)
  ├─ 70% Structured queries (from sub_concepts)
  ├─ 30% Exploratory queries (LLM-generated novel angles)
  ├─ Pinecone: 13 queries × 20 over-fetch × MMR-select-5 → 65 chunks
  ├─ CA Search: 4 queries (2 structured + 2 exploratory)
  └─ Track query_metadata: {query_text, is_exploratory, mmr_lambda, chunk_count}
  ↓
  RetrievalResult {skeleton_id, static_chunks (65), ca_context, ca_queries, query_metadata}

Stage 3 (Generation) ← DIRECT
  ├─ Input: skeletons + retrieval_map (NO intermediate wrapper)
  ├─ On-demand trap lookup (single load, cached)
  ├─ Assemble batch prompt with:
  │   ├─ Trap details (from registry)
  │   ├─ 65 chunks per skeleton (structured + exploratory)
  │   ├─ CA context (70/30)
  │   ├─ Difficulty rules
  │   ├─ Cross-concept instructions
  │   └─ v4.5 Controlled constraints (available_trap_ids, available_question_types)
  ├─ Call Gemini with structured output schema
  └─ Parse response with fallback logic
  ↓
  List[GeneratedQuestion]

Stage 4 (Quality Gate)
  ├─ v4.5 Controlled constraints validation
  ├─ Trap presence check
  ├─ CA in stem check
  └─ Distractor plausibility
  ↓
  List[V2GeneratedQuestion] (final validated questions)
```

**Benefit:** Single trap lookup, unified data flow, fewer intermediate objects.

---

## What Removed Stage 2 Reveals

### Stage 2 Was Doing:
```python
# Stage 2: trap_lookup + prose generation
trap = lookup_trap_in_registry(skeleton.trap_strategy)
instruction = build_prose_instructions(skeleton, trap)
return DifficultyBundle(skeleton, trap, instruction)

# Stage 3: trap_lookup AGAIN (redundant!)
trap = lookup_trap_in_registry(skeleton.trap_strategy)  # ← Same lookup!
prompt = format_prompt_with_trap(trap, ...)
```

### After Removal:
```python
# Stage 3 directly:
trap = lookup_trap_in_registry(skeleton.trap_strategy)  # ← Single lookup
prompt = format_prompt_with_trap(trap, ...)             # ← Use immediately
```

---

## Data Flow Comparison

### Before (with Stage 2)

```
Stage 0         Stage 1            Stage 2              Stage 3           Stage 4
┌──────────┐    ┌─────────────┐    ┌──────────────┐     ┌───────────┐     ┌──────┐
│Skeleton  │───→│Retrieval    │───→│Difficulty    │────→│Generation │────→│QGate │
│{concept, │    │Result       │    │Bundle        │     │(re-lookup │     │{pass}│
│sub...,   │    │{chunks,     │    │{skeleton,    │     │trap)      │     │      │
│trap_id}  │    │ca_context}  │    │trap_rule,    │     │           │     │      │
└──────────┘    └─────────────┘    │instruction}  │     └───────────┘     └──────┘
                                   └──────────────┘
                                   (wrapper only)
```

### After (direct)

```
Stage 0         Stage 1                        Stage 3           Stage 4
┌──────────┐    ┌──────────────────────────┐   ┌───────────┐     ┌──────┐
│Skeleton  │───→│Retrieval with metadata   │──→│Generation │────→│QGate │
│{concept, │    │{chunks, ca_context,      │   │(direct    │     │{pass}│
│sub...,   │    │query_metadata}           │   │lookup     │     │      │
│trap_id}  │    │(70%struct + 30%expl)     │   │trap)      │     │      │
└──────────┘    └──────────────────────────┘   └───────────┘     └──────┘
```

---

## Benefits of Removal

### 1. **Simpler Code Path** ✅
- 3 stages instead of 4
- No DifficultyBundle wrapper
- Direct dict/dataclass passing

### 2. **Single Trap Lookup** ✅
- Load trap registry once
- Cache reused across all skeletons
- No redundant file I/O

### 3. **Better Debugging** ✅
- Full context at generation time
- Query metadata visible in logs
- Chunk sources traceable

### 4. **Unified Data Flow** ✅
- All context (skeleton + chunks + metadata) available together
- No intermediate transformation layer
- Easier to reason about

### 5. **Faster Execution** ✅
- One less stage to run
- No wrapper instantiation
- Direct retrieval_map lookup

---

## Stage 3 Changes: Key Modifications

### Input Contract (Was)
```python
async def generate_for_bundles(
    bundles: List[DifficultyBundle],  # ← Wrapped data
    retrieval_map: Dict,               # ← Separate
    gemini_client,
    ...
)
```

### Input Contract (Now)
```python
async def generate_questions_batch(
    skeletons: List[QuestionSkeleton],  # ← Direct
    retrieval_map: Dict,                # ← Direct
    gemini_client,
    ...
)
```

### Prompt Assembly (Was)
```python
def assemble_batch_prompt(
    skeletons,
    retrieval_map,
    bundle_map,  # ← DifficultyBundle lookup (redundant)
    trap_registry_path,
    ...
)
```

### Prompt Assembly (Now)
```python
def assemble_batch_prompt(
    skeletons,           # ← Contains v4.5 Controlled metadata
    retrieval_map,       # ← Contains 65 chunks + query_metadata
    trap_registry_path,  # ← Loaded on-demand, cached
    ...
)
```

---

## Stage 1 → 3 Context: What Stage 3 Now Sees

### Per Skeleton:

**From Stage 0:**
```python
skeleton = QuestionSkeleton(
    skeleton_id: str,
    question_type: str,           # Must use this type
    concept: str,
    sub_concepts: List[SubConceptItem],
    difficulty: str,              # easy | medium | hard
    difficulty_type: str,         # 15 specific types for retrieval
    ca_flag: bool,
    ca_event: str,
    trap_strategy: str,           # Must use this trap
    available_trap_ids: List[str],        # All valid traps for concept
    available_question_types: List[str],  # All valid types for difficulty
)
```

**From Stage 1:**
```python
retrieval_result = RetrievalResult(
    skeleton_id: str,
    static_chunks: List[Dict],    # 65 chunks!
                                  # - 50 from structured queries
                                  # - 15 from exploratory queries
    ca_context: str,              # From 4 CA searches
    ca_queries: List[str],        # Queries that generated CA context
    query_metadata: List[Dict],   # {query_text, is_exploratory, mmr_lambda, chunk_count}
)
```

**Stage 3 Prompt Sees:**
```
═══════════════════════════════════════════════
QUESTION SPECIFICATION (v4.5 Controlled)
  concept       : Monsoon
  question_type : multi_statement (MUST use this type)
  difficulty    : hard
  difficulty_type: hard_cross_domain_linking
  trap_strategy : GEO_T01 (MUST use this trap)
  Valid question_types: [multi_statement, assertion_reason]
  Valid trap_ids: [GEO_T01, GEO_T02, GEO_T03]
  sub_concepts to test:
    - SW monsoon tracking [aspect=mechanism]
    - Precipitation patterns [aspect=distribution]
    - Jet streams [aspect=mechanism, from=Atmospheric Circulation]

═══════════════════════════════════════════════
STATIC CONTENT (65 chunks from Stage 1):
[Chunk 1 — Monsoon] From structured query "Monsoon mechanism distribution"
[Chunk 2 — Monsoon] From exploratory query "Monsoon climate change rainfall"
...
[Chunk 50] Last structured chunk
[Chunk 51] First exploratory chunk
...
[Chunk 65] Last exploratory chunk (LLM-discovered angle)
```

---

## Comparison: Old vs New Pipeline

| Aspect | Old | New | Winner |
|--------|-----|-----|--------|
| **Stages** | 4 | 3 | New ✅ |
| **Wrapper Objects** | DifficultyBundle | None | New ✅ |
| **Trap Lookups** | 2 per skeleton | 1 cached | New ✅ |
| **Code Clarity** | Harder to follow | Direct flow | New ✅ |
| **Debugging** | Intermediate objects | Full context visible | New ✅ |
| **Data Accessibility** | Split across stages | Unified in Stage 3 | New ✅ |
| **Query Metadata** | Not visible | Full transparency | New ✅ |
| **Performance** | Baseline | Slightly faster | New ✅ |
| **API Calls** | Same | Same | Tie |
| **Context Quality** | 65 chunks | 65 chunks (70/30) | New ✅ |

---

## Architecture Lesson

### What We Learned

```
❌ ANTI-PATTERN: Data wrapper stages
  Stage A → Wrap(data) → Stage C → Unwrap(data)
  Problem: Intermediate objects, redundant work, harder to debug

✅ PATTERN: Direct data passing
  Stage A → {data} → Stage C
  Benefit: Transparent flow, single transformation, easier to follow
```

### This Pipeline Applies Learning

```
✅ Stage 0 (v4.5 Controlled)
  → Intelligent pre-sampling with constraints

✅ Stage 1 (LLM-Gen Exploratory Retrieval)
  → Rich context with 70% structured + 30% exploratory

✅ Stage 3 (Direct Generation)
  → Single trap lookup, full context available
  → No wrapper stage between 1 and 3

✅ Stage 4 (Quality Gate)
  → Final validation with v4.5 constraints
```

---

## Files Modified

### Deleted
- `stage2_difficulty.py` ← REMOVED (unnecessary wrapper)

### Modified
- `stage3_generation.py`
  - Removed `bundle_map` parameter
  - Updated docstrings (mention direct pipeline, no Stage 2)
  - Added `_get_trap()` logging
  - Added query_metadata logging in prompt assembly
  - **NEW:** `generate_questions_batch()` orchestration function
  - Updated `assemble_batch_prompt()` signature
  - Kept `parse_batch_response()` (unchanged, still works)

---

## New Orchestration Function

### `generate_questions_batch()`

**Purpose:** Single entry point for Stage 3 (Stage 0 → 1 → 3 → 4)

**Input:**
```python
skeletons: List[QuestionSkeleton]    # From Stage 0
retrieval_map: Dict[str, RetrievalResult]  # From Stage 1
```

**Output:**
```python
(passed_questions, failed_skeleton_ids)
```

**Process:**
1. Split skeletons into batches (5 per batch)
2. For each batch:
   - Assemble prompt (consolidates skeleton + retrieval context)
   - Call Gemini with structured output schema
   - Parse response with fallback logic
3. Track pass/fail
4. Return results

**Temperature Strategy:**
```python
if num_questions <= 5:
    return 0.75   # medium
elif num_questions <= 10:
    return 0.83   # medium↑
elif num_questions <= 15:
    return 0.85   # heavy hard
else:
    return 0.82   # mixed (50% hard, 25% medium, 25% easy)
```

---

## Next Steps: 10-Question Test

```
Stage 0:
  Generate 30 skeletons from v4.5 Controlled
  → Select 10 + 3 buffer = 13 skeletons

Stage 1:
  Retrieve context for all 13
  → 65 chunks each (70% structured + 30% exploratory)
  → 4 CA queries (2 structured + 2 exploratory)

Stage 3 (NEW):
  Call generate_questions_batch(skeletons[0:10], retrieval_map)
  → Generate 10 questions
  → Batch temperature: 0.83 (for 10 questions)

Stage 4:
  Validate 10 questions
  → Check v4.5 Controlled constraints
  → Trap presence
  → CA in stem
  → Distractor quality

METRICS:
  - Pass rate (should be >80%)
  - Question type distribution (diversity)
  - Trap enforcement (should be 100%)
  - CA integration (should be 30%)
  - Avg chunks per question (should be 65)
  - Structured vs exploratory balance (should be ~70/30)
```

---

## Other Suggestions

### 1. **Cache Exploratory Queries Per Concept** (Optimization)
```python
# Currently: LLM generates 3 exploratory queries per skeleton
# Suggestion: Cache by concept, reuse for all skeletons with same concept

_exploratory_query_cache = {}

async def _generate_exploratory_queries(skeleton, gemini_client):
    concept = skeleton.concept
    if concept in _exploratory_query_cache:
        return _exploratory_query_cache[concept]
    
    queries = await gemini_client.generate(...)
    _exploratory_query_cache[concept] = queries
    return queries
```

**Benefit:** Reduce Gemini calls by ~10x (one per concept, not per skeleton)

---

### 2. **Add Query Metadata to Prompt (Transparency)** (Enhancement)
```python
# Current: Chunks don't show which query generated them
# Suggestion: Mark chunks in prompt

STATIC CONTENT (65 chunks):
  [STRUCTURED - Query: "Monsoon mechanism distribution"]
  [Chunk 1 — Monsoon] ...
  
  [EXPLORATORY - Query: "Monsoon climate change rainfall"]
  [Chunk 51 — Monsoon] ...
```

**Benefit:** LLM can see which chunks are "safe" vs "exploratory"

---

### 3. **Difficulty-Type Aware MMR Lambda (Already Implemented)** ✅
```python
# Implemented in Stage 1:
# - Easy types: prefer relevance (0.7-0.8)
# - Hard types: prefer diversity (0.3-0.5)
# - Randomized: 30% high, 40% balanced, 30% low

# Already good! No change needed.
```

**Status:** Complete in Stage 1

---

### 4. **Batch Size Optimization** (Tuning)
```python
# Current: split_into_batches() uses fixed batch_size=5

# Suggestion: Adaptive batch size based on temperature strategy
# - For 10 questions: use 2 batches of 5 (temp 0.75, 0.90)
# - For 20 questions: use 4 batches of 5 (temp 0.90, 0.90, 0.75, 0.50)

def get_optimal_batch_size(num_questions: int) -> int:
    if num_questions <= 5:
        return num_questions  # 1 batch
    elif num_questions <= 10:
        return 5              # 2 batches
    else:
        return 5              # N batches of 5
```

**Status:** Already implemented (fixed 5)

---

### 5. **Semantic Dedup Across Batches** (Enhancement)
```python
# Current: Stage 4 dedup works per-batch
# Suggestion: Track embeddings across all batches

class GenerationOrchestrator:
    def __init__(self):
        self.all_embeddings = []
        self.dedup_threshold = 0.85
    
    async def generate_batch(self, batch):
        questions = await generate_questions_batch(...)
        # Embed and dedup against prior batches
        for q in questions:
            embedding = embed(q.question)
            is_dup = any(cosine_sim(embedding, e) > self.dedup_threshold for e in self.all_embeddings)
            if is_dup:
                # Mark for regeneration in Stage 4 gap fill
```

**Benefit:** Cross-batch dedup avoids generating same question twice

---

### 6. **Trap Diversity Enforcement** (Quality Improvement)
```python
# Current: Each skeleton picks trap from available_trap_ids (random)
# Suggestion: Track trap usage across batch, ensure diversity

class TrapDiversityTracker:
    def __init__(self):
        self.trap_counts = Counter()
    
    def get_trap_for_concept(self, concept, available_traps):
        # Prefer traps we haven't used yet
        preferred = [t for t in available_traps if self.trap_counts[t] == 0]
        if preferred:
            trap = random.choice(preferred)
        else:
            trap = min(available_traps, key=lambda t: self.trap_counts[t])
        self.trap_counts[trap] += 1
        return trap
```

**Benefit:** Questions don't all use the same trap for a concept

---

## Summary: New Pipeline Wins

✅ **Cleaner architecture** (3 stages, no wrapper)  
✅ **Faster execution** (single trap lookup, no intermediate objects)  
✅ **Better debugging** (full context visible at generation)  
✅ **Rich context** (65 chunks with 70% structured + 30% exploratory)  
✅ **Transparent data flow** (Stage 1 metadata tracked to Stage 3)  
✅ **Constraint enforcement** (v4.5 Controlled constraints applied at generation + validation)  

**Ready for 10-question test!** 🚀
