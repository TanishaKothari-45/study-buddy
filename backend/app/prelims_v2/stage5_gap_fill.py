"""
Stage 5 — Gap Fill & Shuffle

Re-runs Stage 3 for failed skeletons (one retry each).
If a skeleton keeps failing, replaces it with a simpler fresh skeleton.
Final shuffle ensures no 4 consecutive identical correct-answer letters.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Dict, List, Optional

from .models import DifficultyBundle, QuestionSkeleton, V2GeneratedQuestion

logger = logging.getLogger(__name__)

MAX_RETRIES = 1  # How many times to retry a failed skeleton before replacing


async def _retry_skeleton(
    bundle: DifficultyBundle,
    chunk_map: Dict[str, List[dict]],
    ca_query_map: Dict[str, str],
    gemini_client,
    subject: str,
) -> Optional[V2GeneratedQuestion]:
    """Retry generation for a single skeleton with lowered difficulty."""
    from .pipeline import _generate_one
    from .stage1_retrieval import RetrievalResult
    from .stage2_difficulty import inject_difficulty

    # Downgrade difficulty for retry
    sk = bundle.skeleton
    if sk.difficulty == "hard":
        sk_relaxed = sk.model_copy(update={"difficulty": "medium", "ca_flag": False})
    elif sk.difficulty == "medium":
        sk_relaxed = sk.model_copy(update={"difficulty": "easy", "ca_flag": False})
    else:
        sk_relaxed = sk.model_copy(update={"ca_flag": False})

    # Rebuild instruction with relaxed difficulty
    relaxed_bundles = inject_difficulty([sk_relaxed], subject=subject)
    relaxed_bundle = relaxed_bundles[0]

    # Build a minimal RetrievalResult from the cached chunks (drop CA on retry)
    retrieval_result = RetrievalResult(
        skeleton_id    = sk.skeleton_id,
        static_chunks  = chunk_map.get(sk.skeleton_id, []),
        ca_context     = "",
        ca_queries     = [],
        retrieval_mode = "pinecone",
    )

    from pathlib import Path
    _v2_dir = Path(__file__).parent
    _cfg_dir = _v2_dir.parent.parent.parent / "config"
    trap_registry_path = _v2_dir / f"traps_{subject.lower()}.json"
    if not trap_registry_path.exists():
        trap_registry_path = _cfg_dir / "trap_registry.json"

    semaphore = asyncio.Semaphore(1)
    return await _generate_one(
        skeleton           = sk_relaxed,
        retrieval_result   = retrieval_result,
        bundle             = relaxed_bundle,
        gemini_client      = gemini_client,
        trap_registry_path = trap_registry_path,
        pyq_chunks         = [],
        semaphore          = semaphore,
    )


def _shuffle_with_key_spread(questions: List[V2GeneratedQuestion]) -> List[V2GeneratedQuestion]:
    """
    Shuffle questions so no 4 consecutive questions share the same correct-answer letter.
    Simple Fisher-Yates with max-retries safeguard.
    """
    MAX_TRIES = 50
    for _ in range(MAX_TRIES):
        random.shuffle(questions)
        bad = False
        for i in range(3, len(questions)):
            if (
                questions[i].correct_answer
                == questions[i - 1].correct_answer
                == questions[i - 2].correct_answer
                == questions[i - 3].correct_answer
            ):
                bad = True
                break
        if not bad:
            return questions
    logger.warning("⚠️ [Stage 5] Could not achieve full answer-key spread — returning shuffled as-is")
    return questions


def _to_wire_format(q: V2GeneratedQuestion, index: int, job_id: str, topics: List[str]) -> dict:
    """Convert V2GeneratedQuestion to the same wire format as the v1 pipeline."""
    return {
        "question": q.question,
        "options": q.options,
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "source": {
            "topic": topics[0] if topics else q.sub_domain,
            "sub_domain": q.sub_domain,
            "difficulty": q.difficulty,
            "question_type": q.question_type,
            "skeleton_id": q.skeleton_id,
            "trap_verified": q.trap_verified,
            "ca_in_stem": q.ca_in_stem,
            "quality_score": q.quality_score,
            "question_id": f"{job_id}_v2_q{index + 1}",
        },
    }


async def fill_and_finalize(
    passed: List[V2GeneratedQuestion],
    failed_skeleton_ids: List[str],
    all_bundles: List[DifficultyBundle],
    chunk_map: Dict[str, List[dict]],
    ca_query_map: Dict[str, str],
    gemini_client,
    subject: str,
    num_questions: int,
    topics: List[str],
    job_id: str,
) -> List[dict]:
    """
    Stage 5: retry failed skeletons, trim/pad to num_questions, shuffle.
    Returns a list of dicts in the v1-compatible wire format.
    """
    logger.info(
        f"🔧 [Stage 5] Gap fill: {len(passed)} passed, "
        f"{len(failed_skeleton_ids)} to retry, target={num_questions}"
    )

    bundle_map: Dict[str, DifficultyBundle] = {b.skeleton.skeleton_id: b for b in all_bundles}
    all_questions = list(passed)

    # Retry failed skeletons (in parallel, limited retries)
    failed_bundles = [
        bundle_map[sid] for sid in failed_skeleton_ids if sid in bundle_map
    ]

    if failed_bundles:
        retry_tasks = [
            _retry_skeleton(b, chunk_map, ca_query_map, gemini_client, subject)
            for b in failed_bundles
        ]
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

        for result in retry_results:
            if isinstance(result, V2GeneratedQuestion):
                all_questions.append(result)
                logger.debug(f"   ✅ Retry succeeded: {result.skeleton_id}")
            else:
                logger.debug(f"   ❌ Retry failed/exception: {result}")

    # Trim to target
    if len(all_questions) > num_questions:
        # Prefer higher quality_score
        all_questions.sort(key=lambda q: q.quality_score, reverse=True)
        all_questions = all_questions[:num_questions]

    # Pad with duplicates if still short (very unlikely but safe)
    if len(all_questions) < num_questions and all_questions:
        shortage = num_questions - len(all_questions)
        logger.warning(
            f"⚠️ [Stage 5] Still {shortage} questions short — padding with extras"
        )
        extras = all_questions[:shortage]  # reuse first N (will have different shuffled positions)
        all_questions.extend(extras)

    # Shuffle + key spread
    all_questions = _shuffle_with_key_spread(all_questions)

    # Convert to wire format
    final = [
        _to_wire_format(q, i, job_id, topics)
        for i, q in enumerate(all_questions)
    ]

    trap_ok = sum(1 for q in all_questions if q.trap_verified)
    ca_ok = sum(1 for q in all_questions if q.ca_in_stem)
    avg_score = (
        sum(q.quality_score for q in all_questions) / len(all_questions)
        if all_questions else 0
    )

    logger.info(
        f"✅ [Stage 5] Finalized {len(final)} questions. "
        f"Trap verified: {trap_ok}/{len(final)}, "
        f"CA in stem: {ca_ok}/{len(final)}, "
        f"Avg quality: {avg_score:.2f}"
    )
    return final
