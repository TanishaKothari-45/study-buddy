"""
targeted_retriever.py — Stage 1 of the mains answer pipeline.

Runs Pinecone retrieval and CA search in parallel, one query per blueprint
dimension.  Returns a DimensionContext dict where each subheading maps to its
own chunks + CA bullets.  The generator then receives dimension-labelled context
rather than one undifferentiated blob, improving section-level accuracy.

Degrades gracefully: if retrieval fails for a dimension, that dimension gets an
empty string so the generator falls back to general knowledge for it.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# DimensionContext: {subheading_label: {"chunks": str, "ca_bullets": list[str]}}
DimensionContext = dict[str, dict]

# Collected sources across all dimensions (returned alongside DimensionContext)
RetrievalSources = list[dict]


async def run_targeted_retrieval(
    blueprint,
    pinecone_handler,
    flash_client,
    k_per_query: int = 3,
) -> tuple[DimensionContext, RetrievalSources]:
    """
    Stage 1: Run targeted retrieval based on blueprint queries.

    Chunk retrieval:
      - blueprint.retrieval_queries[i] → blueprint.subheadings[i] (index-aligned)
      - k=3 per dimension, all parallel

    CA retrieval:
      - blueprint.ca_dimension_queries: [{subheading, query}] — named mapping
      - Calls fetch_targeted_ca_bullets() directly (no internal dimension re-planning)
      - Uses Flash model for speed

    Returns a DimensionContext dict ready for assemble_generator_user_prompt().
    """
    from .context_retriever import retrieve_context_for_question
    from .current_affairs_fetcher import fetch_targeted_ca_bullets

    subheadings = blueprint.subheadings
    retrieval_queries = blueprint.retrieval_queries or []
    ca_dimension_queries = blueprint.ca_dimension_queries or []

    # Initialise empty result for Introduction, every body subheading, and Conclusion.
    # CA for Introduction (event hook) and Conclusion (forward-looking) is populated
    # if blueprint includes them in ca_dimension_queries.
    all_sections = ["Introduction"] + subheadings + ["Conclusion"]
    dimension_context: DimensionContext = {
        sh: {"chunks": "", "ca_bullets": []} for sh in all_sections
    }

    all_sources: RetrievalSources = []

    # ── Parallel chunk retrieval (index-aligned) ──────────────────────────────
    async def _retrieve_one(query: str, subheading: str):
        try:
            if not pinecone_handler:
                return subheading, "", []
            # retrieve_context_for_question is synchronous — run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            context_text, src_list = await loop.run_in_executor(
                None,
                lambda: retrieve_context_for_question(
                    search_query=query,
                    vector_handler=pinecone_handler,
                    mode="mains",
                    k=k_per_query,
                ),
            )
            return subheading, context_text or "", src_list or []
        except Exception as exc:
            logger.warning(f"Chunk retrieval failed for '{subheading}': {exc}")
            return subheading, "", []

    # ── Targeted CA search (named mapping, direct search — no re-planning) ────
    async def _fetch_ca_one(ca_query_obj):
        subheading = ca_query_obj.subheading
        query = ca_query_obj.query
        try:
            bullets = await fetch_targeted_ca_bullets(
                query=query,
                subheading=subheading,
                gemini_client=flash_client,
                max_bullets=3,
            )
            return subheading, bullets or []
        except Exception as exc:
            logger.warning(f"Targeted CA fetch failed for '{subheading}': {exc}")
            return subheading, []

    chunk_tasks = [
        _retrieve_one(query, subheadings[i] if i < len(subheadings) else f"Dimension {i+1}")
        for i, query in enumerate(retrieval_queries)
    ]
    ca_tasks = [_fetch_ca_one(cq) for cq in ca_dimension_queries]

    all_results = await asyncio.gather(*chunk_tasks, *ca_tasks, return_exceptions=True)

    chunk_results = all_results[: len(chunk_tasks)]
    ca_results = all_results[len(chunk_tasks):]

    for result in chunk_results:
        if isinstance(result, Exception):
            continue
        subheading, chunks, src_list = result
        if subheading in dimension_context:
            dimension_context[subheading]["chunks"] = chunks
        all_sources.extend(src_list)

    for result in ca_results:
        if isinstance(result, Exception):
            continue
        subheading, bullets = result
        if subheading in dimension_context:
            dimension_context[subheading]["ca_bullets"] = bullets

    total_chunks = sum(1 for v in dimension_context.values() if v["chunks"])
    total_ca = sum(len(v["ca_bullets"]) for v in dimension_context.values())
    logger.info(
        f"✅ Targeted retrieval: {total_chunks}/{len(subheadings)} dims have chunks, "
        f"{total_ca} CA bullets across {len(ca_tasks)} targeted searches"
    )
    for section, data in dimension_context.items():
        bullets = data.get("ca_bullets") or []
        if bullets:
            logger.info(f"📰 CA [{section}]:")
            for b in bullets:
                logger.info(f"    • {b}")

    return dimension_context, all_sources
