# Pure CA Questions Architecture

**Date**: 2026-04-04  
**Status**: ✅ Implemented in Stage 1 & Stage 3  

---

## Pure CA Questions: Definition

**Pure CA Questions** (15% of test, pure_ca=True):
- 100% dedicated to current affairs events/developments
- NO concept retrieval (no Pinecone queries)
- NO static chunks from knowledge base
- ONLY CA search context

Examples:
- "Explain the 2023 monsoon floods and its agricultural impact"
- "What were the key policy responses to [recent event]?"
- "Describe the causes and consequences of [2024 development]"

---

## Three Question Types

```
Type 1: PURE CA (15%)
  ca_flag: True
  pure_ca: True
  ├─ Stage 1: SKIP Pinecone, ONLY Google Search
  ├─ Stage 3: ONLY CA context, NO static chunks
  └─ LLM: 100% focused on event

Type 2: CA-LINKED (variable from remaining 85%)
  ca_flag: True
  pure_ca: False
  ├─ Stage 1: Pinecone retrieval + Google Search
  ├─ Stage 3: Chunks + CA context
  └─ LLM: Link CA event to static concept

Type 3: REGULAR (rest of remaining 85%)
  ca_flag: False
  pure_ca: False
  ├─ Stage 1: ONLY Pinecone retrieval
  ├─ Stage 3: ONLY static chunks, NO CA
  └─ LLM: Regular concept-based question
```

---

## Stage 1 Implementation (Retrieval)

### Pure CA (pure_ca=True)

```python
if is_pure_ca:
    # SKIP Pinecone entirely
    static_chunks = []
    query_metadata = []
    
    # Google Search is MANDATORY
    ca_context = Google Search (required)
    ca_queries = _build_ca_search_queries(skeleton)
    
    logger.info("Pure CA question — skipping Pinecone, CA search only")
```

### CA-Linked (ca_flag=True, pure_ca=False)

```python
else if ca_flag:
    # Normal Pinecone retrieval
    static_chunks = Pinecone retrieval (70% struct + 30% expl)
    
    # Google Search is OPTIONAL (for linking)
    ca_context = Google Search (if available)
    
    logger.info("CA-linked question — Pinecone + optional CA search")
```

### Regular (ca_flag=False, pure_ca=False)

```python
else:
    # Normal Pinecone retrieval
    static_chunks = Pinecone retrieval (70% struct + 30% expl)
    
    # No CA search
    ca_context = None
    
    logger.info("Regular question — Pinecone only")
```

---

## Stage 3 Implementation (Generation)

### Question Block Structure

**For Pure CA:**
```
QUESTION N:
  concept: [concept name]
  difficulty: easy (base difficulty)
  pure_ca: True
  
  STATIC CONTENT:
  (No static content for Pure CA questions)
  
  PURE CURRENT AFFAIRS QUESTION (ONLY INPUT):
  [CA search results - bullet points about event]
  
  Your task:
    - Create a question 100% focused on this event
    - Explore impact, causes, policy responses
```

**For CA-Linked:**
```
QUESTION N:
  concept: [concept name]
  ca_flag: True
  pure_ca: False
  
  STATIC CONTENT (use chunks):
  [50-65 chunks from Pinecone]
  
  CURRENT AFFAIRS CONTEXT:
  [CA search results - link to concept]
  
  CA-Linked Question (Type 2):
    - Link this CA event to the static concept
    - Use as a statement, match pair, or stem integration
```

**For Regular:**
```
QUESTION N:
  concept: [concept name]
  ca_flag: False
  pure_ca: False
  
  STATIC CONTENT (use chunks):
  [50-65 chunks from Pinecone]
  
  (No CA context)
```

---

## Data Flow

### Pure CA Question (Type 1)

```
Stage 0 (Blueprint):
  skeleton: pure_ca=True, ca_flag=True, difficulty=easy

Stage 1 (Retrieval):
  Query: Skip Pinecone
  ├─ static_chunks: [] (empty)
  ├─ ca_context: "2023 floods caused X damage, affected Y regions..."
  └─ query_metadata: [] (no Pinecone queries)

Stage 3 (Generation):
  Input: skeleton + ca_context (NO chunks)
  ├─ "Pure CA context: [event details]"
  ├─ "Your task: Create question 100% about this event"
  └─ LLM output: "Explain the 2023 floods..."

Stage 4 (Quality Gate):
  Check: ca_in_stem (should be True)
  Validate: question focuses on event, not unrelated topics
```

---

## Logging Output Example

```
[Stage1] sk_010 | Pure CA question — skipping Pinecone, CA search only
[Stage1] sk_010 | Pure CA question — CA search result: 450 chars (ONLY source)
[Stage3][Q10/sk_010] Pure CA question — skipping static chunks (using CA context only)
[Stage3] Batch input: 10 skeletons
  └─ Q1-Q9: Variable chunks from Pinecone
  └─ Q10: 0 chunks (Pure CA, CA context only)
```

---

## Key Differences Summary

| Aspect | Pure CA | CA-Linked | Regular |
|--------|---------|-----------|---------|
| **ca_flag** | True | True | False |
| **pure_ca** | True | False | False |
| **Pinecone** | ❌ None | ✅ 50-65 chunks | ✅ 50-65 chunks |
| **CA Search** | ✅ Mandatory | ✅ Optional | ❌ None |
| **Static Chunks** | None | Yes | Yes |
| **CA Context** | Yes (ONLY) | Yes (linked) | None |
| **Focus** | Event 100% | Event + Concept | Concept only |
| **% of Test** | 15% | Variable | Rest |

---

## Advantages

✅ **Dedicated CA Coverage**: 15% of test fully focused on recent events  
✅ **No Redundancy**: Pure CA skips Pinecone (saves API calls, tokens)  
✅ **Clear Separation**: LLM knows pure CA means "100% about the event"  
✅ **Flexible CA-linking**: CA-linked questions blend event + concept  
✅ **Quality Distinction**: Pure CA validates "event focus", not "concept focus"  

---

## Summary

✅ **Pure CA implementation**: Stage 1 skips Pinecone, Stage 3 uses only CA context  
✅ **CA-linked preserved**: Pinecone + CA search for concept linking  
✅ **Three types enforced**: Pure CA / CA-linked / Regular via pure_ca flag  
✅ **Logging clarified**: Visible distinction in logs which type each question is  
✅ **Syntax passed**: Both Stage 1 & Stage 3 checked

**Pipeline ready for 15% pure CA, variable CA-linked, and regular questions.** 🚀
