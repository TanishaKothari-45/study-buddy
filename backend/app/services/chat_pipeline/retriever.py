"""
Stage 1: Enhanced Retrieval

Runs multi-query Pinecone fetches in parallel, deduplicates by chunk_id,
then cross-encoder reranks the merged set.
"""
import asyncio
import logging
from .state import QueryAnalysis, RetrievedChunk

logger = logging.getLogger(__name__)


def _build_filter(analysis: QueryAnalysis, user_subject: str | None) -> dict | None:
    """Build Pinecone metadata filter from analysis + user selection."""
    subject = user_subject or analysis.subject
    if not subject:
        return None
    return {"subject": subject}


async def retrieve_chunks(
    analysis: QueryAnalysis,
    pinecone_handler,
    user_subject: str | None = None,
    k: int = 7,
    fetch_k: int = 20,
) -> list[RetrievedChunk]:
    """
    Multi-query retrieval: run each search variant against Pinecone,
    merge results, deduplicate, rerank to top-k.
    """
    filter_metadata = _build_filter(analysis, user_subject)

    queries = analysis.search_queries or [analysis.original_question]

    def _query_sync(query_text: str) -> list[dict]:
        try:
            return pinecone_handler.query_documents(
                query_text=query_text,
                k=fetch_k,
                filter_metadata=filter_metadata,
                use_content_store=True,
                re_rank=False,   # we rerank after merge
                fetch_k=fetch_k,
            )
        except Exception as e:
            logger.warning(f"⚠️ Query failed for '{query_text[:40]}': {e}")
            return []

    # Run queries in parallel using asyncio thread pool
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _query_sync, q)
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks)

    # Merge and deduplicate by chunk_id (keep highest score)
    seen: dict[str, dict] = {}
    for results in results_per_query:
        for doc in results:
            cid = doc.get("metadata", {}).get("chunk_id") or doc.get("chunk_id", "")
            if not cid:
                continue
            existing = seen.get(cid)
            if existing is None or doc.get("score", 0) > existing.get("score", 0):
                seen[cid] = doc

    merged = list(seen.values())
    logger.info(f"📚 Merged {len(merged)} unique chunks from {len(queries)} queries")

    if not merged:
        return []

    # Cross-encoder rerank
    try:
        reranked = pinecone_handler.re_rank_documents(
            query=analysis.original_question,
            docs=merged,
            top_k=k,
        )
    except Exception as e:
        logger.warning(f"⚠️ Rerank failed: {e}, using raw merge scores")
        reranked = sorted(merged, key=lambda d: d.get("score", 0), reverse=True)[:k]

    chunks = []
    for doc in reranked:
        meta = doc.get("metadata", {})
        content = doc.get("content") or doc.get("page_content", "")
        chunks.append(RetrievedChunk(
            chunk_id=meta.get("chunk_id", ""),
            filename=meta.get("filename", "Unknown"),
            content=content,
            score=doc.get("score", 0.0),
            metadata=meta,
        ))

    logger.info(f"✅ Returning {len(chunks)} reranked chunks (k={k})")
    return chunks
