"""
Chat Pipeline v2

SSE event flow:
  sources → content (streamed, map placeholders inline) → map (per map, async) → recommendations → done

Maps are extracted before streaming and generated concurrently.
Text streams immediately with __MAP_0__ etc. placeholders.
Each map fires a separate SSE event when ready — frontend shows loader until it arrives.
"""
import re
import json
import asyncio
import logging
from typing import AsyncIterator

from .state import ChatPipelineState
from .query_analyzer import analyze_query
from .retriever import retrieve_chunks
from .generator import generate_response_text, stream_text
from .recommender import build_recommendations

logger = logging.getLogger(__name__)

_MAP_BLOCK_RE = re.compile(r"```map-json\s*\n.*?\n```", re.DOTALL)
_MAP_PLACEHOLDER = "__MAP_{i}__"


def _extract_maps(text: str) -> tuple[str, list[str]]:
    """
    Replace map-json blocks with __MAP_0__, __MAP_1__ etc.
    Returns (text_with_placeholders, [map_json_block_0, map_json_block_1, ...])
    """
    blocks: list[str] = []

    def replacer(m: re.Match) -> str:
        i = len(blocks)
        blocks.append(m.group(0))
        return f"\n\n{_MAP_PLACEHOLDER.format(i=i)}\n\n"

    replaced = _MAP_BLOCK_RE.sub(replacer, text)
    return replaced, blocks


async def _render_map(block: str) -> str | None:
    """Render a single map-json block → markdown image string, or None on failure."""
    try:
        from ...utils.map_proxy import parse_and_generate_maps
        result = await parse_and_generate_maps(block)
        # parse_and_generate_maps returns the block replaced with ![...](data:...)
        # If unchanged (no map found/rendered), return None
        if result == block or "map-json" in result:
            return None
        return result.strip()
    except Exception as e:
        logger.warning(f"⚠️ Map render failed: {e}")
        return None


async def run_chat_pipeline(
    question: str,
    subject: str | None,
    pinecone_handler,
    gemini_client,
    k: int = 7,
) -> AsyncIterator[str]:
    state = ChatPipelineState(question=question, subject=subject, k=k)

    try:
        # ── Stage 0: Query Analysis ───────────────────────────────────────
        state.analysis = await analyze_query(
            question=question,
            gemini_client=gemini_client,
            user_subject=subject,
        )

        # ── Stage 1: Enhanced Retrieval ───────────────────────────────────
        state.chunks = await retrieve_chunks(
            analysis=state.analysis,
            pinecone_handler=pinecone_handler,
            user_subject=subject,
            k=k,
        )

        state.sources = [
            {
                "filename": c.metadata.get("filename", "Unknown"),
                "page_number": c.metadata.get("page_number") or c.metadata.get("page_start"),
                "chapter": c.metadata.get("chapter", "Unknown"),
                "subject": c.metadata.get("subject", "Unknown"),
                "major_domain": c.metadata.get("major_domain"),
                "sub_domain": c.metadata.get("sub_domain"),
            }
            for c in state.chunks
        ]
        yield f"data: {json.dumps({'type': 'sources', 'sources': state.sources})}\n\n"

        # ── Stage 2: Generate full response text ──────────────────────────
        response_text = await generate_response_text(
            question=question,
            analysis=state.analysis,
            chunks=state.chunks,
            gemini_client=gemini_client,
        )

        # Extract map blocks and replace with placeholders
        try:
            from ...utils.map_proxy import check_map_service_health
            map_service_up = await check_map_service_health()
        except Exception:
            map_service_up = False

        map_blocks: list[str] = []
        if map_service_up:
            response_text, map_blocks = _extract_maps(response_text)
            if map_blocks:
                logger.info(f"🗺️ Found {len(map_blocks)} map block(s) — rendering in parallel")
                # Fire off map rendering concurrently (don't await yet)
                map_tasks = [asyncio.create_task(_render_map(b)) for b in map_blocks]

        # ── Stream text immediately (maps show as loader placeholders) ────
        async for text_chunk in stream_text(response_text):
            yield f"data: {json.dumps({'type': 'content', 'content': text_chunk})}\n\n"

        # ── Collect and send map results as they complete ─────────────────
        if map_blocks and map_service_up:
            for i, task in enumerate(map_tasks):
                try:
                    rendered = await task
                    if rendered:
                        yield f"data: {json.dumps({'type': 'map', 'id': i, 'content': rendered})}\n\n"
                        logger.info(f"🗺️ Map {i} sent")
                    else:
                        # Tell frontend to remove the placeholder gracefully
                        yield f"data: {json.dumps({'type': 'map', 'id': i, 'content': None})}\n\n"
                except Exception as e:
                    logger.warning(f"⚠️ Map {i} failed: {e}")
                    yield f"data: {json.dumps({'type': 'map', 'id': i, 'content': None})}\n\n"

        # ── Stage 3: Recommendations ──────────────────────────────────────
        try:
            content_store_engine = pinecone_handler.content_store.engine
            state.recommendations = build_recommendations(
                chunks=state.chunks,
                content_store_engine=content_store_engine,
            )
        except Exception as e:
            logger.warning(f"⚠️ Recommendations skipped: {e}")
            state.recommendations = []

        if state.recommendations:
            recs_payload = [
                {
                    "type": r.type,
                    "label": r.label,
                    "topic": r.topic,
                    "sub_domain": r.sub_domain,
                    "major_domain": r.major_domain,
                    "query": r.query,
                }
                for r in state.recommendations
            ]
            yield f"data: {json.dumps({'type': 'recommendations', 'items': recs_payload})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"❌ Chat pipeline error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
