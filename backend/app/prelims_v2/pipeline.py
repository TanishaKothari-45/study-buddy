"""
pipeline.py — V2 Orchestrator (Direct: Stage 0 → 1 → 3 → 4 → 5, no Stage 2)

Wires Stages 0, 1, 3, 4, 5 into a single async function.
Updates Redis progress at each stage boundary.
Falls back to the v1 pipeline if Stage 0 fails completely.

Stage flow (NO STAGE 2):
  0. Blueprint        → List[QuestionSkeleton] (v4.5 Controlled)
  1. Retrieval        → List[RetrievalResult]  (70% structured + 30% exploratory)
  [NO STAGE 2 — Direct flow, no wrapper]
  3. Generation       → List[V2GeneratedQuestion] (batch + fallback, single trap lookup)
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
from .user_ledger import load_ledger, merge_and_save_ledger

logger = logging.getLogger(__name__)

_STAGE_PROGRESS = {
    0: {"msg": "Generating question blueprint…",    "pct": 5},
    1: {"msg": "Retrieving targeted content…",      "pct": 20},
    3: {"msg": "Generating questions in parallel…", "pct": 70},
    4: {"msg": "Running quality gate…",             "pct": 85},
    5: {"msg": "Finalizing & shuffling…",           "pct": 95},
}

_GENERATION_CONCURRENCY = 5   # max parallel Gemini Pro calls in Stage 3
_V2_DIR = Path(__file__).parent
_CONFIG_DIR = _V2_DIR.parent.parent.parent / "config"

# Lower temperature → more predictable/clean; higher → more creative trap constructions
TEMPERATURE_BY_DIFFICULTY: dict = {
    "easy":   0.50,
    "medium": 0.75,
    "hard":   0.90,
}


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
    gemini_client,
    trap_registry_path: Path,
    pyq_chunks: list,
    semaphore: asyncio.Semaphore,
) -> Optional[V2GeneratedQuestion]:
    """
    One LLM call for one skeleton. Returns None on failure.

    Used by:
      - Stage 3 fallback (if batch call fails)
      - Stage 5 gap fill retries (when initial generation failed)
    """
    from .stage3_generation import assemble_skeleton_prompt

    prompt = assemble_skeleton_prompt(
        skeleton=skeleton,
        retrieval_result=retrieval_result,
        trap_registry_path=trap_registry_path,
        pyq_chunks=pyq_chunks,
    )

    temperature = TEMPERATURE_BY_DIFFICULTY.get(skeleton.difficulty, 0.75)

    async with semaphore:
        try:
            response_text = await gemini_client.generate_response(
                user_prompt=prompt,
                system_prompt=(
                    "You are a UPSC Prelims question setter. "
                    "Output ONLY a single valid JSON object. No markdown."
                ),
                temperature=temperature,
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
    user_id: Optional[str] = None,
) -> List[dict]:
    """
    Full question-first v2 pipeline (Stage 0 → 1 → 3 → 4 → 5, no Stage 2).

    Returns a list of question dicts compatible with the v1 wire format.
    Falls back to a RuntimeError if Stage 0 produces nothing.

    Pipeline stages:
      0. Blueprint        → List[QuestionSkeleton] (v4.5 Controlled)
      1. Retrieval        → List[RetrievalResult]  (70% struct + 30% expl)
      3. Generation       → List[V2GeneratedQuestion] (direct, no wrapper)
      4. Quality Gate     → passed / failed split
      5. Gap Fill         → final List[dict]
    """
    from .stage0_blueprint  import generate_blueprint
    from .stage1_retrieval  import retrieve_for_all_skeletons
    from .stage4_quality_gate import run_quality_gate
    from .stage5_gap_fill   import fill_and_finalize

    logger.info(f"[V2] Starting job {job_id[:8]} — {num_questions}Q / {subject}")

    domain    = topics[0] if topics else subject
    subdomain = topics[1] if len(topics) > 1 else (topics[0] if topics else subject)

    # ── Load user concept ledger (optional — skipped if no user_id) ───────────
    ledger = await load_ledger(redis, user_id or "", subject, subdomain) if user_id else None
    if ledger:
        logger.info(
            f"[V2] Ledger loaded for user={user_id} — "
            f"{ledger.get('total_questions_seen', 0)} questions seen previously"
        )

    # ── Stage 0: Blueprint ────────────────────────────────────────────────────
    await _set_progress(redis, job_id, 0)
    await _check_cancel(redis, job_id)

    skeletons = await generate_blueprint(
        num_questions=num_questions,
        topics=topics,
        subject=subject,
        gemini_client=gemini_client,
        domain=domain,
        subdomain=subdomain,
        ledger=ledger,
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

    # ── Stage 3: Batch Generation (Direct — no Stage 2 wrapper) ────────────────
    await _set_progress(redis, job_id, 3)
    await _check_cancel(redis, job_id)

    from .stage3_generation import (
        assemble_batch_prompt,
        parse_batch_response,
        split_into_batches,
        get_sub_batch_temperature,
    )

    # Construct domain-specific trap registry path
    # Structure: traps/ → subject/ → domain/ → traps_subject_domain.json
    # Example: traps/geography/climatology/traps_geography_climatology.json

    # Extract domain from topics (topics[1] if available, else fallback to first topic)
    domain = topics[1] if len(topics) > 1 else (topics[0] if topics else subject)
    domain_lower = domain.lower().replace(" ", "_")
    subject_lower = subject.lower().replace(" ", "_")

    # Hierarchical trap registry loading (3-level fallback chain):
    # 1. Domain-specific: traps/subject/domain/traps_subject_domain.json
    trap_registry_path = _V2_DIR / "traps" / subject_lower / domain_lower / f"traps_{subject_lower}_{domain_lower}.json"

    if not trap_registry_path.exists():
        # 2. Subject-level: traps/subject/traps_subject.json
        trap_registry_path = _V2_DIR / "traps" / subject_lower / f"traps_{subject_lower}.json"

    if not trap_registry_path.exists():
        # 3. Config directory (global fallback)
        trap_registry_path = _CONFIG_DIR / "trap_registry.json"

    logger.info(
        f"[V2][STAGE 3] Trap registry (domain='{domain_lower}', subject='{subject_lower}'): "
        f"{trap_registry_path} (exists: {trap_registry_path.exists()})"
    )

    generated: List[V2GeneratedQuestion] = []
    batch_failed = False

    # Split skeletons into sub-batches based on total count
    sub_batches = split_into_batches(skeletons, num_questions)
    total_batches = len(sub_batches)
    logger.info(
        f"[V2][STAGE 3] Batch mode: {len(skeletons)} skeletons → "
        f"{total_batches} sub-batch(es) of ~5"
    )

    for batch_idx, batch_skeletons in enumerate(sub_batches):
        temperature = get_sub_batch_temperature(batch_idx, total_batches, num_questions)

        # Filter retrieval_map to ONLY chunks for this batch (cleaner context)
        batch_retrieval_map = {
            sk.skeleton_id: retrieval_map[sk.skeleton_id]
            for sk in batch_skeletons
            if sk.skeleton_id in retrieval_map
        }

        # Calculate total chunks for this batch (variable per skeleton)
        # Each skeleton: (number of queries) × 5 chunks
        total_chunks_in_batch = sum(
            len(retrieval_map[sk.skeleton_id].static_chunks)
            for sk in batch_skeletons
            if sk.skeleton_id in retrieval_map
        )

        logger.info(
            f"  [3] Sub-batch {batch_idx+1}/{total_batches}: "
            f"{len(batch_skeletons)} skeletons, {total_chunks_in_batch} chunks total "
            f"(variable per skeleton: queries×5), temp={temperature}"
        )

        prompt = assemble_batch_prompt(
            skeletons          = batch_skeletons,
            retrieval_map      = batch_retrieval_map,
            trap_registry_path = trap_registry_path,
            pyq_chunks         = pyq_chunks,
            subject            = subject,
        )

        try:
            response_text = await gemini_client.generate_response(
                user_prompt   = prompt,
                system_prompt = (
                    "You are a UPSC Prelims question setter. "
                    "Output ONLY a single valid JSON object with a 'questions' array. No markdown."
                ),
                temperature   = temperature,
            )
            batch_results = parse_batch_response(response_text, batch_skeletons)

            for sk, result in zip(batch_skeletons, batch_results):
                if result is not None:
                    generated.append(result)
                    logger.info(f"  ✅ {sk.skeleton_id} | {sk.question_type} | {sk.concept} — GENERATED")
                else:
                    logger.warning(f"  ❌ {sk.skeleton_id} | {sk.concept} — FAILED (None from batch)")
                    batch_failed = True

        except Exception as e:
            logger.error(f"  [3] Batch {batch_idx+1} failed: {e} — falling back to per-skeleton calls")
            batch_failed = True

            # Per-skeleton fallback for this sub-batch
            semaphore = asyncio.Semaphore(_GENERATION_CONCURRENCY)
            fallback_tasks = [
                _generate_one(
                    skeleton           = sk,
                    retrieval_result   = retrieval_map.get(sk.skeleton_id),
                    gemini_client      = gemini_client,
                    trap_registry_path = trap_registry_path,
                    pyq_chunks         = pyq_chunks,
                    semaphore          = semaphore,
                )
                for sk in batch_skeletons
            ]
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for sk, result in zip(batch_skeletons, fallback_results):
                if isinstance(result, Exception):
                    logger.error(f"  [3][Fallback] Exception for {sk.skeleton_id}: {result}")
                elif result is not None:
                    generated.append(result)
                    logger.info(f"  ✅ {sk.skeleton_id} | {sk.concept} — FALLBACK GENERATED")
                else:
                    logger.warning(f"  ❌ {sk.skeleton_id} | {sk.concept} — FALLBACK FAILED")

    logger.info(
        f"\n[V2][STAGE 3] {len(generated)}/{len(skeletons)} questions generated"
        + (" (some sub-batches used per-skeleton fallback)" if batch_failed else " via batch call")
    )
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
        skeletons           = skeletons,
        chunk_map           = chunk_map,
        ca_query_map        = ca_query_map,
        gemini_client       = gemini_client,
        subject             = subject,
        num_questions       = num_questions,
        topics              = topics,
        job_id              = job_id,
    )

    logger.info(f"[V2] Job {job_id[:8]} complete — {len(final_questions)} questions")

    # ── Save updated concept ledger (fire-and-forget, non-critical) ───────────
    if user_id and skeletons:
        await merge_and_save_ledger(
            redis     = redis,
            user_id   = user_id,
            subject   = subject,
            subdomain = subdomain,
            skeletons = skeletons,
        )

    return final_questions
