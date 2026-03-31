"""
pipeline.py — V2 Orchestrator

Wires Stages 0 → 5 into a single async function.
Updates Redis progress at each stage boundary.
Falls back to the v1 pipeline if Stage 0 fails completely.

Stage flow:
  0. Blueprint        → List[QuestionSkeleton]
  1. Retrieval        → List[RetrievalResult]  (per-skeleton Pinecone + CA search)
  2. Difficulty       → List[DifficultyBundle] (trap injection)
  3. Generation       → List[V2GeneratedQuestion] (one LLM call per skeleton)
  4. Quality Gate     → passed / failed split
  5. Gap Fill         → final List[dict]
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from redis.asyncio import Redis

from .models import V2GeneratedQuestion

logger = logging.getLogger(__name__)

_STAGE_PROGRESS = {
    0: {"msg": "Generating question blueprint…",    "pct": 5},
    1: {"msg": "Retrieving targeted content…",      "pct": 20},
    2: {"msg": "Injecting difficulty & traps…",     "pct": 25},
    3: {"msg": "Generating questions in parallel…", "pct": 70},
    4: {"msg": "Running quality gate…",             "pct": 85},
    5: {"msg": "Finalizing & shuffling…",           "pct": 95},
}

_GENERATION_CONCURRENCY = 5   # max parallel Gemini Pro calls in Stage 3
_V2_DIR = Path(__file__).parent
_CONFIG_DIR = _V2_DIR.parent.parent.parent / "config"


async def _set_progress(redis: Redis, job_id: str, stage: int) -> None:
    info = _STAGE_PROGRESS.get(stage, {})
    try:
        await redis.set(f"job_progress:{job_id}", str(info.get("pct", 0)), ex=3600)
        await redis.set(f"job_stage:{job_id}",   info.get("msg", ""),     ex=3600)
    except Exception:
        pass


async def _check_cancel(redis: Redis, job_id: str) -> None:
    if await redis.exists(f"cancel:{job_id}"):
        raise asyncio.CancelledError(f"Job {job_id} cancelled by user")


# ── Stage 3 helpers ────────────────────────────────────────────────────────────

def _parse_generation_response(text: str, skeleton_id: str) -> Optional[dict]:
    """Parse Gemini response JSON. Returns None if malformed."""
    text = text.strip()
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\"question\"[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    logger.warning(f"[Stage3] Could not parse JSON for {skeleton_id}")
    return None


async def _generate_one(
    skeleton,
    retrieval_result,
    bundle,
    gemini_client,
    trap_registry_path: Path,
    pyq_chunks: list,
    semaphore: asyncio.Semaphore,
) -> Optional[V2GeneratedQuestion]:
    """One LLM call for one skeleton. Returns None on failure."""
    from .stage3_generation import assemble_skeleton_prompt

    prompt = assemble_skeleton_prompt(
        skeleton=skeleton,
        retrieval_result=retrieval_result,
        trap_registry_path=trap_registry_path,
        pyq_chunks=pyq_chunks,
    )

    async with semaphore:
        try:
            response_text = await gemini_client.generate_response(
                user_prompt=prompt,
                system_prompt=(
                    "You are a UPSC Prelims question setter. "
                    "Output ONLY a single valid JSON object. No markdown."
                ),
                temperature=0.85,
            )
        except Exception as e:
            logger.error(f"[Stage3] Gemini call failed for {skeleton.skeleton_id}: {e}")
            return None

    data = _parse_generation_response(response_text, skeleton.skeleton_id)
    if not data:
        return None

    q_text  = data.get("question", "").strip()
    options = data.get("options", [])
    correct = data.get("correct_answer", "").strip().upper()
    expl    = data.get("explanation", "").strip()

    if not q_text or len(options) < 4 or correct not in ("A", "B", "C", "D"):
        logger.warning(f"[Stage3] Malformed response for {skeleton.skeleton_id}")
        return None

    source = data.get("source", {})
    return V2GeneratedQuestion(
        skeleton_id   = skeleton.skeleton_id,
        question      = q_text,
        options       = options[:4],
        correct_answer= correct,
        explanation   = expl,
        sub_domain    = source.get("sub_domain", skeleton.sub_domain),
        difficulty    = skeleton.difficulty,
        question_type = skeleton.question_type,
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def run_v2_pipeline(
    job_id: str,
    num_questions: int,
    topics: List[str],
    subject: str,
    pinecone_handler,
    gemini_client,
    redis: Redis,
) -> List[dict]:
    """
    Full question-first v2 pipeline.

    Returns a list of question dicts compatible with the v1 wire format.
    Falls back to a RuntimeError if Stage 0 produces nothing.
    """
    from .stage0_blueprint  import generate_blueprint
    from .stage1_retrieval  import retrieve_for_all_skeletons
    from .stage2_difficulty import inject_difficulty
    from .stage4_quality_gate import run_quality_gate
    from .stage5_gap_fill   import fill_and_finalize

    logger.info(f"[V2] Starting job {job_id[:8]} — {num_questions}Q / {subject}")

    # ── Stage 0: Blueprint ────────────────────────────────────────────────────
    await _set_progress(redis, job_id, 0)
    await _check_cancel(redis, job_id)

    skeletons = await generate_blueprint(
        num_questions=num_questions,
        topics=topics,
        subject=subject,
        gemini_client=gemini_client,
        domain=topics[0] if topics else subject,
        subdomain=topics[1] if len(topics) > 1 else (topics[0] if topics else subject),
    )
    if not skeletons:
        raise RuntimeError("Blueprint generation failed: no skeletons produced")

    # ── Verbose: blueprint table ──────────────────────────────────────────────
    logger.info("\n" + "═" * 90)
    logger.info(f"[V2][BLUEPRINT] {len(skeletons)} question skeletons for {subject}:")
    logger.info(f"  {'ID':8} {'TYPE':22} {'TRAP':9} {'DIFF':7} {'CA'} {'CONCEPT'}")
    logger.info("  " + "─" * 80)
    for sk in skeletons:
        ca = "✓ CA" if sk.ca_flag else "    "
        logger.info(f"  {sk.skeleton_id:8} {sk.question_type:22} {sk.trap_strategy:9} {sk.difficulty:7} {ca}  {sk.concept}")
        if sk.ca_event:
            logger.info(f"  {'':8}   ca_event: {sk.ca_event[:70]}")
        for sc in sk.sub_concepts:
            src = f" ← {sc.source_concept}" if sc.source_concept else ""
            logger.info(f"  {'':8}   • [{sc.aspect:12}] {sc.topic[:55]}{src}")
    logger.info("═" * 90 + "\n")

    # ── Fetch PYQ style examples once (shared across all skeletons) ───────────
    try:
        pyq_filter = {"source_type": "pyq"}
        if subject and subject.lower() not in ("general", ""):
            pyq_filter["subject"] = subject
        pyq_chunks = pinecone_handler.query_documents(
            query_text=f"UPSC {subject} previous year questions",
            k=10,
            filter_metadata=pyq_filter,
            use_content_store=False,
        )
        logger.info(f"   [PYQ] {len(pyq_chunks)} style examples")
    except Exception as e:
        logger.warning(f"[V2] PYQ fetch failed: {e}")
        pyq_chunks = []

    # ── Stage 1: Skeleton-Targeted Retrieval ──────────────────────────────────
    await _set_progress(redis, job_id, 1)
    await _check_cancel(redis, job_id)

    retrieval_results = await retrieve_for_all_skeletons(
        skeletons=skeletons,
        pinecone_handler=pinecone_handler,
        gemini_client=gemini_client,
        subject=subject,
    )
    # Build lookup: skeleton_id → RetrievalResult
    retrieval_map = {r.skeleton_id: r for r in retrieval_results}

    # ── Verbose: retrieval & CA summary ──────────────────────────────────────
    logger.info("\n" + "─" * 80)
    logger.info("[V2][STAGE 1] Retrieval Summary:")
    total_chunks = sum(len(r.static_chunks) for r in retrieval_results)
    ca_results   = [(r.skeleton_id, r.ca_queries, len(r.ca_context)) for r in retrieval_results if r.ca_queries]
    logger.info(f"  Total Pinecone chunks across all skeletons: {total_chunks}")
    logger.info(f"  Skeletons with CA search: {len(ca_results)}")
    for sk_id, queries, ca_len in ca_results:
        logger.info(f"    {sk_id} CA queries:")
        for q in queries:
            logger.info(f"      → {q[:80]}")
        logger.info(f"      CA context retrieved: {ca_len} chars")
    for r in retrieval_results:
        logger.info(
            f"  {r.skeleton_id}: {len(r.static_chunks)} chunks | "
            f"mode={r.retrieval_mode} | ca_context={'yes' if r.ca_context else 'no'}"
        )
    logger.info("─" * 80 + "\n")

    # ── Stage 2: Difficulty Injection ─────────────────────────────────────────
    await _set_progress(redis, job_id, 2)

    bundles = inject_difficulty(skeletons, subject=subject)
    bundle_map = {b.skeleton.skeleton_id: b for b in bundles}
    logger.info(f"   [2] {len(bundles)} bundles with trap rules")

    # ── Stage 3: Parallel Generation ─────────────────────────────────────────
    await _set_progress(redis, job_id, 3)
    await _check_cancel(redis, job_id)

    # Determine trap registry path for stage3
    trap_registry_path = _V2_DIR / f"traps_{subject.lower()}.json"
    if not trap_registry_path.exists():
        trap_registry_path = _CONFIG_DIR / "trap_registry.json"

    semaphore = asyncio.Semaphore(_GENERATION_CONCURRENCY)
    gen_tasks = [
        _generate_one(
            skeleton        = sk,
            retrieval_result= retrieval_map.get(sk.skeleton_id),
            bundle          = bundle_map.get(sk.skeleton_id),
            gemini_client   = gemini_client,
            trap_registry_path = trap_registry_path,
            pyq_chunks      = pyq_chunks,
            semaphore       = semaphore,
        )
        for sk in skeletons
    ]
    gen_results = await asyncio.gather(*gen_tasks, return_exceptions=True)

    generated: List[V2GeneratedQuestion] = []
    for sk, result in zip(skeletons, gen_results):
        if isinstance(result, Exception):
            logger.error(f"[Stage3] Exception for {sk.skeleton_id}: {result}")
        elif result is not None:
            generated.append(result)
            logger.info(f"  ✅ {sk.skeleton_id} | {sk.question_type} | {sk.concept} — GENERATED")
        else:
            logger.warning(f"  ❌ {sk.skeleton_id} | {sk.concept} — FAILED (None)")

    logger.info(f"\n[V2][STAGE 3] {len(generated)}/{len(skeletons)} questions generated")
    if not generated:
        raise RuntimeError("Stage 3 produced zero questions")

    # ── Stage 4: Quality Gate ─────────────────────────────────────────────────
    await _set_progress(redis, job_id, 4)
    await _check_cancel(redis, job_id)

    embedder = getattr(pinecone_handler, "embedder", None) or getattr(
        pinecone_handler, "langchain_embeddings", None
    )
    passed, failed_ids = await run_quality_gate(
        questions=generated,
        skeletons=skeletons,
        embedder=embedder,
    )
    logger.info(f"   [4] {len(passed)} passed, {len(failed_ids)} failed")

    # ── Stage 5: Gap Fill & Shuffle ───────────────────────────────────────────
    await _set_progress(redis, job_id, 5)
    await _check_cancel(redis, job_id)

    # Build legacy chunk_map / ca_query_map for gap_fill compatibility
    chunk_map    = {r.skeleton_id: r.static_chunks for r in retrieval_results}
    ca_query_map = {r.skeleton_id: r.ca_queries[0] if r.ca_queries else ""
                    for r in retrieval_results if r.ca_queries}

    final_questions = await fill_and_finalize(
        passed              = passed,
        failed_skeleton_ids = failed_ids,
        all_bundles         = bundles,
        chunk_map           = chunk_map,
        ca_query_map        = ca_query_map,
        gemini_client       = gemini_client,
        subject             = subject,
        num_questions       = num_questions,
        topics              = topics,
        job_id              = job_id,
    )

    logger.info(f"[V2] Job {job_id[:8]} complete — {len(final_questions)} questions")
    return final_questions
