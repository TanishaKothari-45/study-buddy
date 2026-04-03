"""
Stage 1 — Skeleton-Targeted Retrieval

For each QuestionSkeleton:
  - Pinecone: one query per unique source_concept in sub_concepts
  - Google Search: one targeted query if ca_flag=True (ca_event from blueprint, or fallback)
  - Tier 3 (web_only): skip Pinecone entirely

Returns a RetrievalResult per skeleton — ready for Stage 2 prompt assembly.

Chunk budget per skeleton:
  - Own concept sub_concepts     → 5 chunks (tight, high precision)
  - Each borrowed source_concept → 3 chunks (supporting context)
  - Hard cap: 10 chunks total per skeleton (after MMR selection)
  - Tier 3 (web_only): 0 Pinecone chunks

Retrieval pipeline per query (v2 enhanced):
  1. Over-fetch: 3x the target k from Pinecone (higher recall)
  2. Cross-encoder re-rank: re-rank_documents() scores all candidates by relevance
  3. Client-side MMR: mmr_select_from_chunks(lambda=0.6) picks diverse final set
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── LLM Response Models ───────────────────────────────────────────────────────

class ExploratoryQueriesResponse(BaseModel):
    """LLM-generated exploratory queries for corpus discovery."""
    queries: List[str] = []  # List of 3 novel query strings

# Chunk budget constants (default)
_OWN_CONCEPT_K      = 5
_BORROWED_CONCEPT_K = 3
_MAX_CHUNKS_TOTAL   = 10

# Retrieval quality constants
_OVERFETCH_MULTIPLIER = 3    # fetch this many × k candidates before re-rank + MMR
_MMR_LAMBDA           = 0.6  # relevance weight (0=max diversity, 1=max relevance)

# Difficulty-type-aware MMR lambda values
# Easy = high relevance (tight precision), Hard = lower relevance (more diversity)
_DIFFICULTY_LAMBDA = {
    "easy_recall_static": 0.8,
    "easy_ca_trigger": 0.8,
    "easy_reverse_mild": 0.7,
    "medium_concept_linking_same_domain": 0.6,
    "medium_adjacent_fact": 0.6,
    "medium_statistical_reversal": 0.6,
    "medium_precision_location": 0.6,
    "medium_ca_integration": 0.5,
    "hard_counterintuitive_single_concept": 0.5,
    "hard_cross_domain_linking": 0.4,
    "hard_all_of_above_precision": 0.5,
    "hard_strong_concept_depth": 0.5,
    "hard_spatial_sequence": 0.5,
    "hard_reverse_extreme": 0.4,
    "pure_ca_news_tracking": 0.7,
    "pure_ca_recent_event": 0.7,
}

# Randomized MMR lambda for exploratory diversity
def _pick_random_mmr_lambda() -> float:
    """Randomize MMR lambda: 30% high relevance, 40% balanced, 30% high diversity."""
    r = random.random()
    if r < 0.30:
        return 0.7  # High relevance (tight)
    elif r < 0.70:
        return 0.5  # Balanced
    else:
        return 0.3  # High diversity (exploratory)

# Difficulty-type-aware budget adjustments
# Easy = tight retrieval (precision), Hard = exploratory retrieval (recall)
_DIFFICULTY_BUDGET = {
    "easy_recall_static": {"own": 3, "borrowed": 2, "total": 7},
    "easy_ca_trigger": {"own": 3, "borrowed": 1, "total": 6},
    "easy_reverse_mild": {"own": 4, "borrowed": 2, "total": 8},
    "medium_concept_linking_same_domain": {"own": 5, "borrowed": 3, "total": 10},
    "medium_adjacent_fact": {"own": 5, "borrowed": 3, "total": 10},
    "medium_statistical_reversal": {"own": 5, "borrowed": 2, "total": 10},
    "medium_precision_location": {"own": 5, "borrowed": 2, "total": 10},
    "medium_ca_integration": {"own": 4, "borrowed": 3, "total": 10},
    "hard_counterintuitive_single_concept": {"own": 6, "borrowed": 4, "total": 12},
    "hard_cross_domain_linking": {"own": 5, "borrowed": 5, "total": 12},
    "hard_all_of_above_precision": {"own": 7, "borrowed": 5, "total": 14},
    "hard_strong_concept_depth": {"own": 6, "borrowed": 3, "total": 12},
    "hard_spatial_sequence": {"own": 6, "borrowed": 4, "total": 12},
    "hard_reverse_extreme": {"own": 6, "borrowed": 4, "total": 12},
    "pure_ca_news_tracking": {"own": 3, "borrowed": 1, "total": 6},
    "pure_ca_recent_event": {"own": 3, "borrowed": 1, "total": 6},
}


# ── LLM Query Generator ───────────────────────────────────────────────────────

async def _generate_exploratory_queries(
    skeleton,
    gemini_client,
) -> List[str]:
    """
    LLM generates 3 novel queries to explore angles NOT covered by skeleton.

    Input to LLM:
      - concept
      - sub_concepts tested
      - aspects covered
      - difficulty_type

    Output: 3 queries exploring:
      - Different aspects (economic, historical, climate, policy)
      - Inter-domain connections (Monsoon + Agriculture, Monsoon + Migration)
      - Novel angles (extreme events, case studies, recent trends, linkages)

    These queries discover corpus areas beyond the structured skeleton.
    """
    if not gemini_client:
        logger.warning("[Stage1] No Gemini client — skipping exploratory query generation")
        return []

    concept = skeleton.concept
    sub_concept_topics = [sc.topic for sc in skeleton.sub_concepts]
    aspects_covered = list(set(sc.aspect for sc in skeleton.sub_concepts))
    difficulty_type = getattr(skeleton, "difficulty_type", "medium")

    system_prompt = """You are an expert UPSC curriculum researcher.
Given a question skeleton, generate 3 diverse Pinecone search queries to explore
DIFFERENT angles and connections NOT covered by the skeleton.

Think about:
- Different aspects (economic, historical, climate, policy, social, environmental)
- Inter-domain links (concept + agriculture, concept + migration, concept + policy)
- New dimensions (extreme cases, recent events, case studies, linkages to other concepts)
- Avoid repeating the sub_concepts already tested

Generate SHORT, specific queries (5-10 words each) that a corpus would have."""

    user_prompt = f"""
QUESTION SKELETON:
  Concept: {concept}
  Sub-concepts tested: {sub_concept_topics}
  Aspects covered: {aspects_covered}
  Difficulty: {difficulty_type}

Generate 3 NOVEL Pinecone queries exploring DIFFERENT angles.
Return ONLY a JSON object with a "queries" array of 3 strings.
"""

    try:
        response = await gemini_client.generate_response(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            response_schema=ExploratoryQueriesResponse,
            temperature=0.7,  # Some creativity for novel angles
        )

        if isinstance(response, str):
            parsed = json.loads(response)
            queries = parsed.get("queries", [])
        else:
            queries = response.queries if hasattr(response, "queries") else []

        logger.info(
            f"[Stage1] Generated {len(queries)} exploratory queries for {concept}: "
            f"{queries}"
        )
        return queries
    except Exception as e:
        logger.warning(f"[Stage1] Exploratory query generation failed: {e}")
        return []


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    skeleton_id:    str
    static_chunks:  List[Dict]          # from Pinecone
    ca_context:     str                 # from Google Search (raw text)
    ca_queries:     List[str]           # the queries that were run
    retrieval_mode: str                 # pinecone | pinecone_fuzzy | web_only
    query_metadata: List[Dict] = field(default_factory=list)  # {query_text, is_exploratory, mmr_lambda, chunk_count}


# ── Pinecone query builder ────────────────────────────────────────────────────

def _build_structured_queries(skeleton) -> List[Dict]:
    """
    Build 70% STRUCTURED queries from skeleton.sub_concepts.

    One query per unique source_concept in skeleton.sub_concepts.
    Marked as is_exploratory=False for tracking.

    Returns list of:
      {"query_text": str, "concept_filter": str, "k": int, "is_exploratory": bool}

    source_concept="" means sub_concept belongs to skeleton's own concept.
    """
    # Group sub_concepts by source_concept
    groups: Dict[str, List[str]] = defaultdict(list)
    for sc in skeleton.sub_concepts:
        src = sc.source_concept if sc.source_concept else skeleton.concept
        groups[src].append(sc.topic)

    queries = []
    own_concept = skeleton.concept

    for source, topics in groups.items():
        # Build query text: concept name + sub_concept topics joined
        query_text = f"{source} {' '.join(t[:60] for t in topics)}"

        queries.append({
            "query_text":      query_text,
            "concept_filter":  source,
            "k":               5,  # Will be allocated per-query in retrieval
            "is_exploratory":  False,
        })

    # Log what we're about to fire
    for q in queries:
        label = "own" if q["concept_filter"] == own_concept else "borrowed"
        logger.info(
            f"[Stage1][StructuredQuery] [{label}] concept='{q['concept_filter']}' "
            f"→ '{q['query_text'][:80]}'"
        )
    return queries


# ── Google Search query builder ───────────────────────────────────────────────

def _build_ca_search_queries(skeleton) -> List[str]:
    """
    Build Google Search queries for a CA-flagged skeleton (70% structured + 30% exploratory).

    70% Structured:
      1. skeleton.ca_event (most targeted, if present)
      2. Static concept + topic search (from sub_concepts)

    30% Exploratory:
      3. "{concept} latest developments" (recent news angle)
      4. "{concept} policy impact current" (policy + impact angle)

    Returns list of query strings for Gemini Google Search tool.
    """
    queries = []

    # 70% STRUCTURED
    # Query 1: ca_event from blueprint (most targeted)
    if skeleton.ca_event:
        queries.append(
            f"{skeleton.ca_event} {skeleton.concept} India 2024 2025 official"
        )
    else:
        # Fallback: concept + first topic
        first_topic = skeleton.sub_concepts[0].topic[:50] if skeleton.sub_concepts else ""
        queries.append(
            f"{skeleton.concept} {first_topic} UPSC Prelims 2024 2025 India"
        )

    # Query 2: Government source anchor (static content)
    first_topic = skeleton.sub_concepts[0].topic[:50] if skeleton.sub_concepts else ""
    queries.append(
        f"site:pib.gov.in OR site:indiabudget.gov.in OR site:moes.gov.in "
        f"{skeleton.concept} {first_topic}"
    )

    # 30% EXPLORATORY
    # Query 3: Recent developments / latest news
    queries.append(
        f"{skeleton.concept} latest developments 2024 2025 news India"
    )

    # Query 4: Policy impact / implications
    queries.append(
        f"{skeleton.concept} policy impact implementation India current"
    )

    logger.info(
        f"[Stage1][CAQuery] {skeleton.skeleton_id} | {len(queries)} CA search queries "
        f"(2 structured, 2 exploratory):"
    )
    for i, q in enumerate(queries, 1):
        query_type = "structured" if i <= 2 else "exploratory"
        logger.info(f"  [{i}] [{query_type}] {q[:90]}")
    return queries



async def _retrieve_from_pinecone(
    queries:         List[Dict],
    pinecone_handler,
    subject:         str,
    retrieval_mode:  str,
    difficulty_type: str = "",
) -> tuple[List[Dict], List[Dict]]:
    """
    70% STRUCTURED + 30% EXPLORATORY Pinecone retrieval.

    Per query:
      1. Fetch k=20 (over-fetch for recall)
      2. Cross-encoder re-rank all candidates
      3. MMR select k=5 with RANDOMIZED lambda:
         - 30%: lambda=0.7 (high relevance, tight)
         - 40%: lambda=0.5 (balanced)
         - 30%: lambda=0.3 (high diversity, exploratory)

    Total output: ~65 chunks (13 queries × 5 chunks) + metadata

    Enriches with SQLite full text.

    Returns:
      (all_chunks, query_metadata) where query_metadata tracks source query info
    """
    if not queries:
        return [], []

    all_chunks    = []
    seen_ids      = set()
    query_metadata = []
    content_store = getattr(pinecone_handler, "content_store", None)
    embedder      = getattr(pinecone_handler, "langchain_embeddings", None)

    # ── Batch embed all query texts in ONE API call ───────────────────────────
    vectors: List[Optional[List[float]]] = [None] * len(queries)
    if embedder:
        try:
            texts  = [q["query_text"] for q in queries]
            batch  = embedder.embed_documents(texts)   # one call for all N queries
            vectors = batch
            logger.info(f"[Stage1] Batch-embedded {len(texts)} queries in 1 API call")
        except Exception as e:
            logger.warning(f"[Stage1] Batch embedding failed, falling back to per-query: {e}")

    # ── Per-query Pinecone call (over-fetch 20 → cross-encoder → MMR select 5) ─────────
    for i, q in enumerate(queries):
        filter_meta = {"source_type": {"$ne": "pyq"}}
        if retrieval_mode == "pinecone":
            filter_meta["major_domain"] = {"$in": [q["concept_filter"], subject]}

        query_vec  = vectors[i] if vectors[i] is not None else None
        target_k   = 5  # Final MMR selection: 5 chunks per query
        overfetch_k = 20  # Over-fetch: start with 20 candidates

        is_exploratory = q.get("is_exploratory", False)
        query_type_label = "exploratory" if is_exploratory else "structured"

        # Pick randomized MMR lambda for diversity
        mmr_lambda = _pick_random_mmr_lambda()

        try:
            # Fetch 20 candidates, cross-encoder re-ranks all, then MMR picks 5
            chunks = pinecone_handler.query_documents(
                query_text        = q["query_text"],
                k                 = target_k,
                fetch_k           = overfetch_k,
                re_rank           = True,
                filter_metadata   = filter_meta,
                use_content_store = False,
                query_vector      = query_vec,
            )
        except Exception as e:
            logger.warning(f"[Stage1] Pinecone query failed for '{q['concept_filter']}': {e}")
            chunks = []

        # Fuzzy fallback if sparse (< half requested)
        if len(chunks) < max(1, target_k // 2):
            try:
                chunks = pinecone_handler.query_documents(
                    query_text        = q["query_text"],
                    k                 = target_k,
                    fetch_k           = overfetch_k,
                    re_rank           = True,
                    filter_metadata   = {"source_type": {"$ne": "pyq"}},
                    use_content_store = False,
                    query_vector      = query_vec,
                )
                logger.debug(f"[Stage1] Fuzzy fallback: '{q['concept_filter']}' → {len(chunks)} chunks")
            except Exception as e:
                logger.warning(f"[Stage1] Fuzzy fallback failed: {e}")

        # ── SQLite enrichment (full text from content_store) ─────────────────
        enriched_count = 0
        for chunk in chunks:
            chunk_id = chunk.get("id") or chunk.get("chunk_id") or id(chunk)
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)

            if content_store:
                meta     = chunk.get("metadata", {})
                c_id     = meta.get("chunk_id")
                filename = meta.get("filename")
                if c_id and filename:
                    try:
                        full = content_store.get_chunk(c_id, filename)
                        if full:
                            chunk["content"] = full
                            enriched_count += 1
                    except Exception:
                        pass

            if not chunk.get("content"):
                chunk["content"] = chunk.get("metadata", {}).get("content_preview", "")

            all_chunks.append(chunk)

        logger.info(
            f"[Stage1] [{query_type_label}] concept='{q['concept_filter'][:30]}' | "
            f"query='{q['query_text'][:60]}' → {len(chunks)} chunks "
            f"(lambda={mmr_lambda:.1f}, enriched={enriched_count})"
        )

        # Track metadata for this query
        query_metadata.append({
            "query_text": q["query_text"],
            "is_exploratory": is_exploratory,
            "mmr_lambda": mmr_lambda,
            "chunk_count": len(chunks),
            "enriched_count": enriched_count,
        })

    # ── NO FINAL DEDUP — Keep all chunks for rich context ────────────────────
    # With 70% structured + 30% exploratory, having 65 chunks gives Stage 3 LLM
    # massive exploration room. Semantic dedup already happened per-query via MMR.
    logger.info(
        f"[Stage1] Collected {len(all_chunks)} total chunks "
        f"({len([m for m in query_metadata if not m['is_exploratory']])} structured, "
        f"{len([m for m in query_metadata if m['is_exploratory']])} exploratory)"
    )

    return all_chunks, query_metadata


# ── Main retrieval function ───────────────────────────────────────────────────

async def retrieve_for_skeleton(
    skeleton,
    pinecone_handler,
    gemini_client,
    subject: str,
) -> RetrievalResult:
    """
    Full retrieval for one skeleton: 70% structured + 30% exploratory.

    Pipeline:
      1. Build structured queries from skeleton.sub_concepts (~10 queries)
      2. LLM generates exploratory queries (~3 queries)
      3. Pinecone retrieval: fetch 20 per query, MMR select 5 (randomized lambda)
      4. Result: ~65 chunks total for rich context
      5. Google Search for CA (if ca_flag)
    """
    retrieval_mode = getattr(skeleton, "retrieval_mode", "pinecone")

    static_chunks = []
    ca_context    = ""
    ca_queries    = []
    query_metadata = []

    # ── Pinecone retrieval: 70% structured + 30% exploratory ────────────────────
    if retrieval_mode != "web_only":
        # Build structured queries from skeleton.sub_concepts (70%)
        structured_queries = _build_structured_queries(skeleton)

        # Generate exploratory queries from LLM (30%)
        exploratory_query_texts = await _generate_exploratory_queries(skeleton, gemini_client)
        exploratory_queries = [
            {
                "query_text": qt,
                "concept_filter": skeleton.concept,
                "k": 5,
                "is_exploratory": True,
            }
            for qt in exploratory_query_texts
        ]

        # Combine all queries
        all_queries = structured_queries + exploratory_queries

        # Retrieve from Pinecone
        difficulty_type = getattr(skeleton, "difficulty_type", "")
        static_chunks, query_metadata = await _retrieve_from_pinecone(
            queries=all_queries,
            pinecone_handler=pinecone_handler,
            subject=subject,
            retrieval_mode=retrieval_mode,
            difficulty_type=difficulty_type,
        )

        logger.info(
            f"[Stage1] {skeleton.skeleton_id} | Pinecone retrieval complete: "
            f"{len(static_chunks)} chunks from {len(all_queries)} queries "
            f"({len(structured_queries)} structured, {len(exploratory_queries)} exploratory, "
            f"difficulty_type='{difficulty_type}')"
        )

    # ── Google Search retrieval ───────────────────────────────────────────────
    if skeleton.ca_flag:
        ca_queries = _build_ca_search_queries(skeleton)
        try:
            # Pass queries to Gemini client that has Google Search tool enabled
            search_result = await gemini_client.search_and_summarise(
                queries=ca_queries,
                context_hint=f"UPSC Prelims {subject} — {skeleton.concept}",
            )
            ca_context = search_result or ""
            logger.info(
                f"[Stage1] {skeleton.skeleton_id} | CA search: "
                f"{len(ca_context)} chars from {len(ca_queries)} queries"
            )
        except Exception as e:
            logger.warning(f"[Stage1] {skeleton.skeleton_id} | CA search failed: {e}")

    return RetrievalResult(
        skeleton_id   = skeleton.skeleton_id,
        static_chunks = static_chunks,
        ca_context    = ca_context,
        ca_queries    = ca_queries,
        retrieval_mode= retrieval_mode,
        query_metadata= query_metadata,
    )


# ── Batch retrieval (all skeletons in parallel, semaphore-limited) ────────────

async def retrieve_for_all_skeletons(
    skeletons,
    pinecone_handler,
    gemini_client,
    subject:     str,
    concurrency: int = 10,
) -> List[RetrievalResult]:
    """
    Run retrieval for all skeletons concurrently.
    Google Search calls are rate-limited by semaphore.
    Pinecone calls are fast enough to run fully parallel.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(skeleton):
        async with semaphore:
            return await retrieve_for_skeleton(
                skeleton, pinecone_handler, gemini_client, subject
            )

    results = await asyncio.gather(*[bounded(s) for s in skeletons])
    logger.info(f"[Stage1] Retrieval complete: {len(results)} skeletons")
    return results
