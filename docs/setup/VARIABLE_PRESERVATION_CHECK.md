# Variable Preservation Check - k_target & lambda_mult

## ✅ Confirmed: All Variables Are Preserved Correctly

### Flow Trace

#### 1. **Variable Declaration** (mock_test.py lines 621-632)
```python
if sub_domain:
    k_target = 10
    lambda_mult = 0.65
elif major_domain:
    k_target = 12
    lambda_mult = 0.65
else:
    k_target = 15
    lambda_mult = 0.6
```
✅ Variables set based on granularity

#### 2. **Concept Retrieval** (mock_test.py lines 644-654)
```python
initial_k = k_target + 3        # ✅ Uses k_target
fetch_k = initial_k * 3          # ✅ Uses k_target indirectly
concept_chunks = pinecone_handler.query_documents_mmr(
    query_text=query,
    fetch_k=fetch_k,             # ✅ Uses k_target (via fetch_k)
    k=initial_k,                  # ✅ Uses k_target (via initial_k)
    lambda_mult=lambda_mult       # ✅ Uses lambda_mult directly
)
```
✅ All variables passed correctly

#### 3. **query_documents_mmr** (pinecone_handler.py lines 807-885)
```python
def query_documents_mmr(self, query_text: str, fetch_k: int = 50, k: int = 10,
                        lambda_mult: float = 0.65, ...):
    # ...
    docs = vectorstore.similarity_search(query_text, k=fetch_k, ...)  # ✅ Uses fetch_k
    # ...
    formatted_results = self.mmr_select_from_chunks(
        chunks=formatted_results,
        query_text=query_text,
        k=k,                       # ✅ Uses k (which is initial_k = k_target + 3)
        lambda_mult=lambda_mult    # ✅ Uses lambda_mult
    )
```
✅ Variables passed through correctly

#### 4. **mmr_select_from_chunks** (pinecone_handler.py lines 1284-1400)
```python
def mmr_select_from_chunks(self, chunks: List[Dict], query_text: str,
                           k: int = 10, lambda_mult: float = 0.65):
    # ...
    # Calculate combined scores (similarity + intrinsic)
    combined_scores = [...]  # Uses intrinsic_score from metadata
    
    # MMR algorithm using combined scores
    # Select first document (highest combined score)
    first_idx = max(remaining_indices, key=lambda i: combined_scores[i])
    
    # Select remaining k-1 documents using MMR
    for _ in range(min(k - 1, len(remaining_indices))):  # ✅ Uses k
        # ...
        mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_similarity  # ✅ Uses lambda_mult
        # ...
    
    return diverse_chunks[:k]  # ✅ Returns k chunks
```
✅ Both k and lambda_mult used correctly

#### 5. **Final MMR Re-ranking** (mock_test.py lines 839-848)
```python
mmr_k = min(total_target, len(diverse_content_chunks))
final_content = pinecone_handler.mmr_select_from_chunks(
    chunks=diverse_content_chunks,
    query_text=query,
    k=mmr_k,                      # ✅ Uses total_target (derived from k_target)
    lambda_mult=lambda_mult       # ✅ Uses lambda_mult
)
```
✅ Variables preserved

## Summary

### k_target Flow:
```
k_target (10/12/15)
  ↓
initial_k = k_target + 3 (13/15/18)
  ↓
fetch_k = initial_k * 3 (39/45/54) → similarity_search(k=fetch_k)
  ↓
k = initial_k (13/15/18) → mmr_select_from_chunks(k=k)
  ↓
Returns k chunks ✅
```

### lambda_mult Flow:
```
lambda_mult (0.65/0.65/0.6)
  ↓
query_documents_mmr(lambda_mult=lambda_mult)
  ↓
mmr_select_from_chunks(lambda_mult=lambda_mult)
  ↓
Used in MMR calculation: mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_similarity ✅
```

### Combined Scoring Integration:
```
Similarity (from vector search)
  +
Intrinsic Score (from metadata)
  ↓
Combined Score = 0.8 * similarity + 0.2 * intrinsic
  ↓
Used as "relevance" in MMR: mmr_score = lambda_mult * combined_score - (1 - lambda_mult) * max_similarity
```

## ✅ Verification

1. **k_target**: ✅ Used to calculate initial_k, fetch_k, and total_target
2. **lambda_mult**: ✅ Passed through and used in MMR calculation
3. **Combined scoring**: ✅ Added without breaking existing logic
4. **Granularity-based behavior**: ✅ Preserved (sub-domain: 10/0.65, major: 12/0.65, general: 15/0.6)

## Conclusion

**All variables are preserved correctly!** The combined scoring is integrated seamlessly:
- Similarity scores are still calculated
- Combined scores use similarity + intrinsic
- MMR uses combined scores with lambda_mult for diversity
- k_target determines how many chunks to retrieve
- lambda_mult controls diversity vs relevance balance

The system maintains all existing variable-based behavior while adding quality filtering via intrinsic scores.


