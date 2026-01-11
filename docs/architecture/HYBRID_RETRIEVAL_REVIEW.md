# Hybrid Retrieval Pipeline - Code Review & Integration Plan

## 📋 Executive Summary

The proposed `hybrid_retrieval_pipeline.py` introduces **excellent improvements** to the mock test generation retrieval system. However, it needs **integration adjustments** to work with the existing codebase architecture.

**Verdict: ✅ APPROVE with modifications**

---

## ✅ Strengths of Proposed Code

### 1. **Source Diversity Enforcement** ⭐⭐⭐⭐⭐
- **`enforce_source_diversity()`** prevents single-file dominance
- Critical for balanced question generation
- **Status**: ✅ Created in `backend/app/utils/mm_utils.py`

### 2. **Progressive Fallback Strategy** ⭐⭐⭐⭐⭐
- Sub-domain → Major-domain → General fallback
- Ensures retrieval success even with sparse data
- **Status**: ✅ Should be integrated

### 3. **Domain-Aware Retrieval** ⭐⭐⭐⭐
- Different retrieval strategies based on granularity:
  - Sub-domain: Micro-topic diversity (λ=0.65)
  - Major-domain: Cross-sub-domain diversity (λ=0.65)
  - General: Broad coverage (λ=0.6)
- **Status**: ✅ Should be integrated

### 4. **Cleaner Pipeline Structure** ⭐⭐⭐⭐
- More modular and maintainable
- Clear separation of concerns
- **Status**: ✅ Should be integrated

---

## ⚠️ Issues & Required Fixes

### 1. **Import Path Issues** 🔴
**Problem**: 
```python
from app.utils.chunk_utils import deduplicate_chunks  # ❌ Doesn't exist
from app.utils.mm_utils import enforce_source_diversity  # ❌ Doesn't exist
```

**Fix**: ✅ Created `backend/app/utils/mm_utils.py` with `enforce_source_diversity()`

**For deduplication**: Use existing `deduplicate_chunks()` from `query.py` (but it returns string, not list)

---

### 2. **Method Name Mismatch** 🟡
**Problem**: 
```python
retriever = pinecone_handler.get_retriever(...)  # ❌ Method doesn't exist
```

**Current codebase uses**: `get_retriever_for_mode(mode, use_content_store=True)`

**Fix**: 
```python
# Use existing method
retriever = pinecone_handler.get_retriever_for_mode("prelims", use_content_store=True)

# OR create wrapper that calls get_retriever() with custom params
# (Need to check if get_retriever() exists in PineconeHandler)
```

---

### 3. **Missing PYQ Filtering Logic** 🟡
**Problem**: Proposed code doesn't filter PYQ files vs content files

**Current code has**:
- `is_pyq_chunk()` - checks filename patterns
- `is_actual_question_chunk()` - filters out index/contents pages

**Fix**: Integrate these functions into the pipeline

---

### 4. **Deduplication Function Mismatch** 🟡
**Problem**: 
```python
pyq_chunks = deduplicate_chunks(pyq_chunks)  # Returns string, not list!
```

**Current `deduplicate_chunks()` signature**:
```python
def deduplicate_chunks(docs: List[Any], ...) -> str:  # Returns combined text
```

**Fix**: Create chunk-level deduplication OR adapt to work with Document objects

---

### 5. **Prompt System Too Simple** 🔴
**Problem**: Proposed prompt is very basic compared to existing comprehensive system

**Current system includes**:
- Difficulty guides (easy/medium/hard)
- Pattern diversity framework (6 UPSC patterns)
- Current affairs integration
- Diversity checklist (5 semantic dimensions)
- Pattern plan injection

**Fix**: ✅ **DO NOT replace prompt** - integrate retrieval improvements while keeping existing prompt system

---

### 6. **Missing Domain Extraction** 🟡
**Problem**: Function signature expects `major_domain` and `sub_domain` but current code uses `topics` list

**Current**: `MockTestRequest.topics: List[str]`

**Fix**: Extract domain/sub-domain from topics using existing `map_topics_to_domains()` function

---

## 🔧 Recommended Integration Approach

### Phase 1: Create Utility Functions ✅
- ✅ Created `backend/app/utils/mm_utils.py` with `enforce_source_diversity()`

### Phase 2: Create Hybrid Retrieval Function
Create `hybrid_retrieve_for_mock_test()` that:
1. ✅ Uses progressive fallback for PYQ retrieval
2. ✅ Uses domain-aware retrieval strategies
3. ✅ Integrates `enforce_source_diversity()`
4. ✅ Uses existing `is_pyq_chunk()` and `is_actual_question_chunk()`
5. ✅ Uses existing `get_retriever_for_mode()` API
6. ✅ Returns chunks in format expected by `generate_question_paper()`

### Phase 3: Integrate into Existing Endpoint
Modify `generate_mock_test()` endpoint to:
1. Extract `major_domain` and `sub_domain` from `test_request.topics`
2. Call new hybrid retrieval function
3. Pass results to existing `generate_question_paper()` (keep existing prompt system)

---

## 📝 Proposed Integration Code Structure

```python
# In backend/app/routes/mock_test.py

def hybrid_retrieve_for_mock_test(
    pinecone_handler: PineconeHandler,
    topics: List[str],
    num_questions: int = 10
) -> tuple[List[Dict], List[Dict]]:
    """
    Hybrid retrieval with progressive fallback and source diversity.
    
    Returns:
        (pyq_chunks, content_chunks) tuple
    """
    from ..utils.mm_utils import enforce_source_diversity
    from ..utils.metadata_enricher import GEOGRAPHY_DOMAINS
    
    # Extract domains from topics
    domain_mapping = map_topics_to_domains(topics)
    major_domains = domain_mapping.get("major_domains", [])
    sub_domains = domain_mapping.get("sub_domains", [])
    
    major_domain = major_domains[0] if major_domains else None
    sub_domain = sub_domains[0] if sub_domains else None
    
    # 1. Progressive PYQ retrieval
    pyq_chunks = []
    
    def retrieve_pyqs(query_text: str, k: int = 5):
        retriever = pinecone_handler.get_retriever_for_mode("prelims", use_content_store=True)
        docs = retriever.get_relevant_documents(query_text)
        chunks = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
        return [c for c in chunks if is_pyq_chunk(c) and is_actual_question_chunk(c)]
    
    # Progressive fallback
    if sub_domain:
        pyq_chunks.extend(retrieve_pyqs(f"UPSC prelims {sub_domain} questions"))
    if len(pyq_chunks) < 2 and major_domain:
        pyq_chunks.extend(retrieve_pyqs(f"UPSC prelims {major_domain} questions"))
    if len(pyq_chunks) < 2:
        pyq_chunks.extend(retrieve_pyqs("UPSC prelims geography questions"))
    
    pyq_chunks = pyq_chunks[:5]  # Limit for prompt focus
    
    # 2. Domain-aware content retrieval
    if sub_domain:
        query = f"UPSC {sub_domain} important concepts"
        k, lambda_mult = 10, 0.65
    elif major_domain:
        query = f"UPSC {major_domain} major subtopics"
        k, lambda_mult = 10, 0.65
    else:
        query = "UPSC Geography static and current topics"
        k, lambda_mult = 10, 0.6
    
    content_retriever = pinecone_handler.get_retriever_for_mode("prelims", use_content_store=True)
    content_docs = content_retriever.get_relevant_documents(query)
    content_chunks = [
        {"content": d.page_content, "metadata": d.metadata}
        for d in content_docs
        if not is_pyq_chunk({"metadata": d.metadata})
    ]
    
    # Apply source diversity
    content_chunks = enforce_source_diversity(content_chunks, max_per_file=2)
    
    # 3. Final MMR re-ranking (existing logic)
    combined_chunks = pyq_chunks + content_chunks
    diverse_chunks = pinecone_handler.mmr_select_from_chunks(
        chunks=combined_chunks,
        query_text=query,
        k=min(12, len(combined_chunks)),
        lambda_mult=0.6
    )
    
    # Separate back
    pyq_final = [c for c in diverse_chunks if c.get("metadata", {}).get("source") == "pyq"]
    content_final = [c for c in diverse_chunks if c.get("metadata", {}).get("source") == "content"]
    
    return pyq_final or pyq_chunks[:3], content_final or content_chunks[:8]
```

---

## ✅ Final Recommendations

### DO:
1. ✅ **Integrate `enforce_source_diversity()`** - Already created
2. ✅ **Use progressive fallback** for PYQ retrieval
3. ✅ **Use domain-aware retrieval** strategies
4. ✅ **Keep existing prompt system** - It's comprehensive and working well
5. ✅ **Integrate with existing functions** (`is_pyq_chunk`, `map_topics_to_domains`, etc.)

### DON'T:
1. ❌ **Don't replace the prompt system** - It's critical for quality
2. ❌ **Don't remove existing filtering logic** - PYQ detection is important
3. ❌ **Don't change method signatures** - Keep compatibility with existing code
4. ❌ **Don't simplify too much** - Current system has good error handling

---

## 🎯 Next Steps

1. ✅ **DONE**: Create `mm_utils.py` with `enforce_source_diversity()`
2. **TODO**: Create `hybrid_retrieve_for_mock_test()` function (see structure above)
3. **TODO**: Integrate into `generate_mock_test()` endpoint
4. **TODO**: Test with various domain/sub-domain combinations
5. **TODO**: Compare quality before/after integration

---

## 📊 Expected Benefits

After integration, you should see:
- ✅ **Better source diversity** (no single file dominating)
- ✅ **More reliable retrieval** (progressive fallback)
- ✅ **Domain-aware quality** (better chunks for specific domains)
- ✅ **Maintained quality** (existing prompt system preserved)

---

**Status**: Ready for integration with modifications ✅

