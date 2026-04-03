# Study Buddy — RAG + LangGraph Retrieval Orchestration Plan

## 🧠 High-Level Vision

Study Buddy is an intelligent study assistant for UPSC (Prelims & Mains) that:
- Answers questions using a knowledge base (RAG)
- Uses advanced retrieval strategies
- Adapts strategies based on question type and performance
- Evolves into a judge-based retrieval
- Orchestrated with LangGraph

### Core Learning Goals
- Master RAG patterns
- Learn LangGraph workflow orchestration
- Experiment with retrieval strategies
- Build evaluation logic for model-guided assessment
- Improve answer quality over time

---

## 📊 Version Path & Roadmap

| Version | Focus Area | Description |
|---------|------------|-------------|
| **v1.0** | Adaptive Retriever | Basic LangGraph routing to different retrievers |
| **v1.1** | Re-ranker Toggle | Add optional re-ranking step |
| **v1.2** | Evaluation Node | Introduce a quality judge node |
| **v2.0** | Retriever Judge Agent | Full retrieval comparison system |
| **v2.x** | Long-term Learning | Feedback loop & persistence |

---

## 🧩 Project Structure

```
/study-buddy/
│
├── docs/
│   └── STUDY_BUDDY_RAG_LANGGRAPH_PLAN.md   ← (This file)
│
├── src/
│   ├── retrievers/
│   │   ├── base_retriever.py
│   │   ├── hybrid_retriever.py
│   │   └── re_ranker.py
│   │
│   ├── langgraph_flow/
│   │   ├── nodes/
│   │   │   ├── InputNode.py
│   │   │   ├── RouterNode.py
│   │   │   ├── RetrieverA.py
│   │   │   ├── RetrieverB.py
│   │   │   ├── JudgeNode.py
│   │   │   └── MergeNode.py
│   │   └── study_buddy_graph.json
│   │
│   ├── evaluation/
│   │   ├── metrics.py
│   │   └── judge.py
│   │
│   ├── llm_engine/
│   │   └── llm_wrapper.py
│   │
│   ├── app.py
│   └── config.py
│
├── datasets/
│   └── upsci_corpus/
│
├── tests/
│   └── test_retrievers.py
└── README.md
```

---

## ⚙️ Technology Stack

- **LangGraph** — Workflow engine
- **RAG Retriever** — Vector search (Cosine/Hybrid)
- **Re-ranker** — Optional optional semantic re-rank step
- **LLM** — GPT-4o / Claude / Equivalent
- **Vector DB** — Pinecone / Qdrant / Weaviate
- **Evaluation Tools** — Custom judge logic, metrics

---

## 🧠 Version 1.0 — Adaptive Retriever

### Goal
Route queries to different retriever strategies depending on question type:
- Prelims-style questions → `PrelimsRetriever`
- Mains-style/concept questions → `MainsRetriever`

### LangGraph Flow

```
┌─────────────┐
│ Input Node  │
└──────┬──────┘
       ↓
┌─────────────┐
│ Router Node │   ← Classifier based on heuristics/question pattern
└──────┬──────┘
       ↓
┌─────────────┐        ┌─────────────┐
│ Retriever A │        │ Retriever B │
└──────┬──────┘        └──────┬──────┘
       ↓                        ↓
┌─────────────┐        ┌─────────────┐
│   Context   │        │   Context   │  ← Top K chunks
└─────────────┘        └─────────────┘
       ↓                        ↓
      Merge Context & Pass to LLM
```

### Logic
- RouterNode decides strategy A or B.
- Both retrievers produce candidate chunks.
- Pass merged chunks to LLM with prompt.

---

## 🧪 Version 1.1 — Add Optional Re-Ranker

### Purpose
Improve retrieval quality by re-ranking top candidate chunks before passing to the LLM.

### Changes

Add `ReRankerNode` to LangGraph:

```
Retriever A/B → ReRankerNode → Sorted Context → LLM
```

### Criteria
- Only enable if initial retrieval quality drops below threshold
- Can toggle based on question difficulty

---

## 📐 Version 1.2 — Evaluation / Judge Node

### Purpose
Assess answer quality from different strategies in LangGraph.

### Architecture

```
                  ┌─────────────┐
                  │  Router     │
                  └────┬────────┘
                       ↓
             ┌───────────────┐
             │Retriever A    │
             └──────┬────────┘
                    ↓
             ┌───────────────┐
             │ ReRanker A    │ (optional)
             └──────┬────────┘
         Context A   ↓
                     ↓    ┌───────────────┐
┌─────────────┐      ↓    │ Retriever B    │
│  User Query │───────→ Context B ← ReRanker B │
└─────────────┘           └───────────────┘
       ↓                            ↓
       ↓                            ↓
    JudgeNode (score A vs B)      
             ↓
      Best Context Selected
             ↓
           LLM Answer
```

### Judge Logic

JudgeNode should:
- Accept contexts A and B
- Use a scoring function:
  - Content relevance
  - Answer quality comparison
  - Overlap reduction
  - LLM-based judgment

### Evaluation Criteria

| Metric | Description |
|--------|-------------|
| Cosine Score Mean | Average similarity |
| Coverage | How much context matches question intent |
| Redundancy | Penalize repeated content |
| LLM Judgement | Human-style final score |

---

## 🧠 Version 2.0 — Retrieval Judge Agent

### Description
Instead of heuristic router, use an agentic decision mechanism to choose retrieval strategies dynamically.

### Approach

1. Candidate strategies list
2. Agent reasons which to run
3. Run multiple retrievals in parallel
4. Feed results to JudgeNode
5. Select best

### LangGraph Flow

```
Input
  ↓
Strategy Selector Node
  ↓
Parallel Retriever Nodes
  ↓
Judge Node
  ↓
Best context
  ↓
LLM
```

### Strategy Selector

This node uses a lightweight classifier or rules:

Examples:
```
if topics indicates static facts → use hybrid retriever
if question is opinion/concept → use semantic search
else use both
```

→ Next step: training strategy selector using observed performance feedback.

---

## 🛠️ Implementation Tips

### Retriever

- Maintain separate index for:
  - Prelims (small atomic facts)
  - Mains (thematic, linked concepts)

### Re-rankers

- Simple: use LLM to re-score
- Advanced: use cross-encoder

### Judge

- Build data recorder to save:
  - Query
  - Strategy used
  - Context returned
  - Score
  - LLM answer

---

## 🧠 Evaluation Loop

1. Run retrieval strategies
2. Judge compares them
3. Choose best context
4. Log results
5. Over time:
   - Adjust router rules
   - Adjust re-rank gains
   - Train selector with feedback

This encodes *learning from experiments*.

---

## 🧪 Metrics & Logging

Record:

```
{
  query: "...",
  retriever: "A|B",
  strategy: "cosine|hybrid",
  context_chunks: [...],
  judge_scores: {...},
  llm_answer: "...",
  timestamp: ...
}
```

Use stored logs:
- Visualize trends
- Improve selection
- Track performance over time

---

## 🧩 Long-term Vision

Eventually replace:
- Heuristic Router → Learned classifier
- Rule-based Judge → ML-based ranking

---

## 🧭 Usage Guidelines for Cursor / IDE Agents

- Save this file at project root
- Let IDE index it
- When asking for code:
  > “Remember our Study Buddy Plan”
- Trust indexing; no need to repeat context

---

## 📌 Summary

**Phase 1 — Adaptive Retriever:** Route based on question type  
**Phase 2 — Re-ranking:** Optional quality boost  
**Phase 3 — Evaluation Node:** Judge A vs B  
**Phase 4 — Retrieval Judge:** Full dynamic strategy selection

---

## 📅 Next Steps

1. Build basic retrievers
2. Add LangGraph router
3. Add re-ranker
4. Build judge node
5. Log, analyze, improve

---

