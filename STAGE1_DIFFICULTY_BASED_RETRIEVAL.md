# Stage 1: Difficulty-Based Retrieval (Deterministic)

**Date**: 2026-04-04  
**Status**: ✅ Design specified, implementation in progress  

---

## Problem: Query Explosion

**Current approach:**
- Every skeleton gets 10 structured + 3 exploratory = 13 queries
- 100 skeletons × 13 = 1,300 queries
- 1,300 × 20 chunks = 26,000 Pinecone calls
- Cost & time: Excessive

**Solution:**
- Make exploratory queries **optional** based on difficulty
- Define deterministic exploratory **dimensions** (not LLM-generated)
- Allocate intelligently: Easy=1, Medium=1-2, Hard=2-3 queries total

---

## Query Allocation by Difficulty

### Easy (1 query total)
```
Structured: 1 query
  - Main concept only
  - Direct from skeleton.concept
  
Exploratory: 0 queries
  - Easy questions need clarity, not exploration
  
Total chunks: 5
```

### Medium (1-3 queries total)
```
Structured: 1-2 queries
  - If 1 sub_concept: 1 query (concept + aspect)
  - If 2+ sub_concepts: flexible
    * Option A: 1 combined query (concept + both aspects)
    * Option B: 2 separate queries (one per aspect)
  
Exploratory: 0-1 query (if has linked_concept)
  - 50% chance if source_concept exists
  - Choose 1 dimension randomly
  
Total chunks: 5-15
```

### Hard (3-5 queries total)
```
Structured: 2-3 queries
  - Concept + source_concept (linked)
  - Can go 3 deep if complex linking
  - Example: Monsoon → sub_concept + El Nino aspect + Climate impact
  
Exploratory: 1-2 queries
  - Always included for hard
  - Choose 1-2 dimensions from array:
    * cross_domain (how concept links to other subjects)
    * temporal (historical or recent angle)
    * anomaly (edge cases, exceptions)
    * extreme (extreme conditions)
    * linked_concept (deep concept linking)
    * application (real-world impact)
    * comparison (contrast with similar)
    * policy (policy implications)
  - Randomize which dimensions, but deterministic count
  
Total chunks: 15-25
```

---

## Exploratory Dimensions (Deterministic, UPSC-Relevant)

Each dimension is a **predefined query template**, not LLM-generated:

```python
EXPLORATORY_DIMENSIONS = {
    "cross_domain": 
      "{concept} relationship with [history|economics|polity]",
    
    "temporal":
      "{concept} historical evolution from ancient to modern",
    
    "anomaly":
      "{concept} exceptions, edge cases, unusual patterns",
    
    "extreme":
      "{concept} extreme conditions, magnitudes, worst-case scenarios",
    
    "linked_concept":
      "{concept} deep connection with {source_concept} [causes|impacts|relationships]",
    
    "application":
      "{concept} real-world applications, practical use, impact on society",
    
    "comparison":
      "{concept} similarities and differences with [related concept]",
    
    "policy":
      "{concept} government policy responses, regulations, frameworks",
}
```

**Selection:** For hard questions, randomly pick 1-2 dimensions, fill template with skeleton data.

---

## Implementation Changes

### 1. Query Allocation Function

```python
def _get_query_counts(difficulty: str, sub_concept_count: int) -> tuple[int, int]:
    """
    Return (structured_count, exploratory_count) based on difficulty.
    
    Deterministic rules:
      - Easy: 1 structured, 0 exploratory
      - Medium: 1-2 structured (based on sub_concepts), 0-1 exploratory
      - Hard: 2-3 structured, 1-2 exploratory
    """
    allocation = _QUERY_ALLOCATION.get(difficulty, _QUERY_ALLOCATION["medium"])
    
    if difficulty == "easy":
        return 1, 0
    
    elif difficulty == "medium":
        struct_count = min(
            sub_concept_count,  # One per unique concept group
            allocation["structured_max"]
        )
        struct_count = max(struct_count, allocation["structured_min"])
        expl_count = 1 if sub_concept_count >= 2 else 0  # Only if linked
        return struct_count, expl_count
    
    elif difficulty == "hard":
        struct_count = random.randint(
            allocation["structured_min"],
            min(3, allocation["structured_max"])
        )
        expl_count = random.randint(1, 2)  # 1-2 exploratory dimensions
        return struct_count, expl_count
    
    return 1, 0
```

### 2. Exploratory Query Builder (Deterministic)

```python
def _build_exploratory_queries_deterministic(
    skeleton,
    difficulty: str,
    expl_count: int,
) -> List[Dict]:
    """
    Build exploratory queries by selecting dimensions + template + skeleton data.
    
    NO LLM CALL — purely deterministic.
    """
    if expl_count == 0:
        return []
    
    # Randomly select dimensions (without replacement)
    selected_dims = random.sample(_EXPLORATORY_DIMENSIONS, min(expl_count, len(_EXPLORATORY_DIMENSIONS)))
    
    exploratory_queries = []
    for dim in selected_dims:
        # Build query text from template + skeleton
        if dim == "cross_domain":
            other_domains = random.choice(["history", "economics", "polity"])
            query_text = f"{skeleton.concept} relationship with {other_domains}"
        
        elif dim == "temporal":
            query_text = f"{skeleton.concept} historical evolution ancient to modern India"
        
        elif dim == "anomaly":
            query_text = f"{skeleton.concept} exceptions edge cases unusual patterns"
        
        elif dim == "extreme":
            query_text = f"{skeleton.concept} extreme conditions magnitudes worst-case"
        
        elif dim == "linked_concept" and skeleton.sub_concepts:
            linked = skeleton.sub_concepts[0].source_concept or skeleton.concept
            query_text = f"{skeleton.concept} {linked} deep connection causes impacts"
        
        elif dim == "application":
            query_text = f"{skeleton.concept} real-world applications practical impact"
        
        elif dim == "comparison":
            query_text = f"{skeleton.concept} similarities differences related concepts"
        
        elif dim == "policy":
            query_text = f"{skeleton.concept} government policy responses regulations India"
        
        else:
            continue  # Skip if template doesn't match
        
        exploratory_queries.append({
            "query_text": query_text,
            "concept_filter": skeleton.concept,
            "is_exploratory": True,
            "dimension": dim,
        })
    
    return exploratory_queries
```

### 3. Modified retrieve_for_skeleton

```python
async def retrieve_for_skeleton(skeleton, ...):
    
    # Determine structured query count
    struct_count, expl_count = _get_query_counts(
        skeleton.difficulty,
        len(skeleton.sub_concepts)
    )
    
    # Build structured queries (existing logic, but with count limit)
    structured_queries = _build_structured_queries(skeleton)[:struct_count]
    
    # Build exploratory queries (deterministic, no LLM)
    exploratory_queries = _build_exploratory_queries_deterministic(
        skeleton,
        skeleton.difficulty,
        expl_count
    )
    
    # Combine and retrieve
    all_queries = structured_queries + exploratory_queries
    
    # Log: Clear indication of query allocation
    logger.info(
        f"[Stage1] {skeleton.skeleton_id} | "
        f"Difficulty: {skeleton.difficulty} | "
        f"Queries: {len(structured_queries)} structured, {len(exploratory_queries)} exploratory "
        f"({', '.join(q.get('dimension', 'N/A') for q in exploratory_queries)}) | "
        f"Total chunks: {len(all_queries) * 5}"
    )
    
    # Retrieve from Pinecone...
```

---

## Example Query Counts

### 100-Question Test

**Easy (15 questions):**
- 15 × 1 query = 15 queries
- 15 × 5 chunks = 75 chunks

**Medium (25 questions):**
- 25 × 1.5 avg = 37-38 queries
- 37 × 5 chunks = 185 chunks

**Hard (40 questions):**
- 40 × 2.5 avg = 100 queries
- 100 × 5 chunks = 500 chunks

**Pure CA (15 questions):**
- 0 queries (no Pinecone)

**TOTAL: ~150 queries (vs 1,300 before!)**
- 150 × 20 fetches = 3,000 Pinecone calls (vs 26,000 before!)
- 10x efficiency gain

---

## Prompt Updates (Clear, Concise, Direct)

### For LLM Skeleton Generation (Stage 0)
```
No changes — continues as is.
```

### For LLM in Stage 3 (Generation)
```
Prompts remain same — they see chunks from Stage 1, don't need to know allocation strategy.
```

### For CA Search (if applicable)
```
No changes — independent of retrieval strategy.
```

**Key principle:** Prompts never mention query allocation or exploratory strategy. LLM just generates based on chunks it receives.

---

## Logging Output Example

```
[Stage1] sk_001 | Difficulty: easy | Queries: 1 structured, 0 exploratory | Total chunks: 5
[Stage1] sk_002 | Difficulty: medium | Queries: 2 structured, 1 exploratory (linked_concept) | Total chunks: 15
[Stage1] sk_003 | Difficulty: hard | Queries: 3 structured, 2 exploratory (cross_domain, temporal) | Total chunks: 25
[Stage1] Total across 10 skeletons: 21 queries, 105 chunks
```

---

## Summary

✅ **Deterministic**: No LLM calls for exploratory queries  
✅ **Efficient**: 10x fewer Pinecone calls (150 vs 1,300 per 100Q test)  
✅ **UPSC-aligned**: Exploratory dimensions match real question patterns  
✅ **Flexible**: Medium allows option A (combined) vs option B (separate) for structured  
✅ **Clear allocation**: Difficulty-based rules, all hardcoded  
✅ **No prompt bloat**: LLM stays simple, doesn't see allocation strategy  

**Ready for implementation!** 🚀
