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
  - Hard cap: 10 chunks total per skeleton
  - Tier 3 (web_only): 0 Pinecone chunks
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# Chunk budget constants
_OWN_CONCEPT_K      = 5
_BORROWED_CONCEPT_K = 3
_MAX_CHUNKS_TOTAL   = 10


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    skeleton_id:    str
    static_chunks:  List[Dict]          # from Pinecone
    ca_context:     str                 # from Google Search (raw text)
    ca_queries:     List[str]           # the queries that were run
    retrieval_mode: str                 # pinecone | pinecone_fuzzy | web_only


# ── Pinecone query builder ────────────────────────────────────────────────────

def _build_pinecone_queries(skeleton) -> List[Dict]:
    """
    Build one Pinecone query per unique source_concept in skeleton.sub_concepts.

    Returns list of:
      {"query_text": str, "concept_filter": str, "k": int}

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

        k = _OWN_CONCEPT_K if source == own_concept else _BORROWED_CONCEPT_K

        queries.append({
            "query_text":      query_text,
            "concept_filter":  source,
            "k":               k,
        })

    # Enforce total chunk cap across all queries
    total = sum(q["k"] for q in queries)
    if total > _MAX_CHUNKS_TOTAL:
        # Scale down proportionally, floor at 2 per query
        scale = _MAX_CHUNKS_TOTAL / total
        for q in queries:
            q["k"] = max(2, int(q["k"] * scale))

    # Log what we're about to fire
    for q in queries:
        label = "own" if q["concept_filter"] == own_concept else "borrowed"
        logger.info(
            f"[Stage1][PineQuery] [{label}] concept='{q['concept_filter']}' k={q['k']} "
            f"→ '{q['query_text'][:80]}'"
        )
    return queries


# ── Google Search query builder ───────────────────────────────────────────────

def _build_ca_search_queries(skeleton) -> List[str]:
    """
    Build Google Search queries for a CA-flagged skeleton.

    Priority order:
    1. skeleton.ca_event  — specific event string from blueprint (most targeted)
    2. build_current_search_queries adapter — falls back to topic-based queries

    Returns list of query strings (not dicts) to pass to Gemini search tool.
    """
    queries = []

    # Priority 1: ca_event from blueprint (always use if present)
    if skeleton.ca_event:
        # Build a specific, event-anchored query
        queries.append(
            f"{skeleton.ca_event} {skeleton.concept} India 2024 2025 official"
        )
        # Second query: static concept anchor for grounding
        queries.append(
            f"site:ncert.nic.in OR site:gov.in {skeleton.concept} "
            f"{skeleton.sub_concepts[0].topic[:50] if skeleton.sub_concepts else ''} UPSC"
        )
        return queries

    # Priority 2: fallback — build queries from concept + sub_concepts topics
    first_topic = skeleton.sub_concepts[0].topic[:50] if skeleton.sub_concepts else ""
    queries.append(
        f"{skeleton.concept} {first_topic} UPSC Prelims 2024 2025 current affairs India"
    )
    queries.append(
        f"site:pib.gov.in OR site:indiabudget.gov.in OR site:moes.gov.in "
        f"{skeleton.concept} {first_topic}"
    )
    logger.info(
        f"[Stage1][CAQuery] {skeleton.skeleton_id} | {len(queries)} search queries:"
    )
    for i, q in enumerate(queries, 1):
        logger.info(f"  [{i}] {q[:100]}")
    return queries



async def _retrieve_from_pinecone(
    queries:         List[Dict],
    pinecone_handler,
    subject:         str,
    retrieval_mode:  str,
) -> List[Dict]:
    """
    Batch-embed all queries once → then hit Pinecone per query with the pre-computed
    vector. This avoids N separate embed_query API calls.
    fetch_k is set to k (exact count needed) — no over-fetching.
    Enriches with SQLite full text identical to v1 pipeline.
    """
    if not queries:
        return []

    all_chunks    = []
    seen_ids      = set()
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

    # ── Per-query Pinecone call (using pre-computed vector) ───────────────────
    for i, q in enumerate(queries):
        filter_meta = {"source_type": {"$ne": "pyq"}}
        if retrieval_mode == "pinecone":
            filter_meta["major_domain"] = {"$in": [q["concept_filter"], subject]}

        query_vec = vectors[i] if vectors[i] is not None else None

        try:
            chunks = pinecone_handler.query_documents(
                query_text    = q["query_text"],
                k             = q["k"],
                fetch_k       = q["k"],        # no over-fetch — exact count
                filter_metadata = filter_meta,
                use_content_store = False,     # we do enrichment ourselves below
                query_vector  = query_vec,     # skip re-embedding inside handler
            )
        except Exception as e:
            logger.warning(f"[Stage1] Pinecone query failed for '{q['concept_filter']}': {e}")
            chunks = []

        # Fuzzy fallback if sparse (< half requested)
        if len(chunks) < max(1, q["k"] // 2):
            try:
                chunks = pinecone_handler.query_documents(
                    query_text      = q["query_text"],
                    k               = q["k"],
                    fetch_k         = q["k"],
                    filter_metadata = {"source_type": {"$ne": "pyq"}},
                    use_content_store = False,
                    query_vector    = query_vec,
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
            f"[Stage1] '{q['concept_filter'][:40]}' | k={q['k']} | "
            f"query='{q['query_text'][:55]}' "
            f"→ {len(chunks)} chunks, {enriched_count} SQLite-enriched"
        )

    return all_chunks


# ── Main retrieval function ───────────────────────────────────────────────────

async def retrieve_for_skeleton(
    skeleton,
    pinecone_handler,
    gemini_client,
    subject: str,
) -> RetrievalResult:
    """
    Full retrieval for one skeleton.
    Runs Pinecone + Google Search concurrently where applicable.
    """
    retrieval_mode = getattr(skeleton, "retrieval_mode", "pinecone")

    static_chunks = []
    ca_context    = ""
    ca_queries    = []

    # ── Pinecone retrieval ────────────────────────────────────────────────────
    if retrieval_mode != "web_only":
        pinecone_queries = _build_pinecone_queries(skeleton)
        static_chunks = await _retrieve_from_pinecone(
            queries=pinecone_queries,
            pinecone_handler=pinecone_handler,
            subject=subject,
            retrieval_mode=retrieval_mode,
        )
        logger.info(
            f"[Stage1] {skeleton.skeleton_id} | Pinecone: "
            f"{len(static_chunks)} chunks from {len(pinecone_queries)} queries"
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
