"""
user_ledger.py — Per-user concept exhaustion tracking in Redis.

Ledger key: ledger:{user_id}:{subject}:{subdomain}
TTL: 30 days, refreshed on every read + write.

Structure:
{
  "concepts_seen": {
    "Monsoon": {
      "count": 3,
      "traps_used": ["GEO_T04", "GEO_T06"],
      "sub_concepts_used": ["Southwest monsoon onset mechanism", ...],
      "last_seen": "2026-03-15"
    }
  },
  "traps_exhausted": ["GEO_T04"],   # trap used >= TRAP_EXHAUSTION_THRESHOLD times
  "total_questions_seen": 25
}
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LEDGER_TTL_SECONDS      = 60 * 60 * 24 * 30   # 30 days
_TRAP_EXHAUSTION_THRESHOLD = 3                   # deprioritise a trap after this many uses
_HEAVY_CONCEPT_THRESHOLD   = 2                   # concept is "heavily tested" after this many


def _redis_key(user_id: str, subject: str, subdomain: str) -> str:
    safe = lambda s: s.lower().replace(" ", "_")
    return f"ledger:{user_id}:{safe(subject)}:{safe(subdomain)}"


async def load_ledger(
    redis,
    user_id: str,
    subject: str,
    subdomain: str,
) -> Optional[Dict[str, Any]]:
    """
    Load the user's concept ledger from Redis.
    Refreshes TTL on access. Returns None if no ledger exists yet.
    """
    if not user_id:
        return None
    key = _redis_key(user_id, subject, subdomain)
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        ledger = json.loads(raw)
        # Refresh TTL on every read so active users never expire mid-streak
        await redis.expire(key, _LEDGER_TTL_SECONDS)
        return ledger
    except Exception as e:
        logger.warning(f"[Ledger] Failed to load ledger for {user_id}: {e}")
        return None


async def merge_and_save_ledger(
    redis,
    user_id: str,
    subject: str,
    subdomain: str,
    skeletons: list,          # List[QuestionSkeleton] from Stage 0
) -> None:
    """
    Merge the just-generated skeletons into the user's concept ledger and persist.

    Called after a successful pipeline run (Stage 5 complete).
    Safe to skip on failure — ledger is advisory, not critical.
    """
    if not user_id or not skeletons:
        return
    key = _redis_key(user_id, subject, subdomain)
    try:
        raw = await redis.get(key)
        ledger: Dict[str, Any] = json.loads(raw) if raw else {
            "concepts_seen": {},
            "traps_exhausted": [],
            "total_questions_seen": 0,
        }

        concepts_seen: Dict[str, Any] = ledger.setdefault("concepts_seen", {})
        traps_exhausted: List[str]    = ledger.setdefault("traps_exhausted", [])
        today = str(date.today())

        # Count per-trap usage across ALL concepts in this session
        session_trap_counts: Dict[str, int] = {}

        for sk in skeletons:
            concept_name = sk.concept
            trap_id      = sk.trap_strategy or ""
            sub_concepts = [sc.topic for sc in (sk.sub_concepts or [])]

            # Update concept entry
            entry = concepts_seen.setdefault(concept_name, {
                "count": 0,
                "traps_used": [],
                "sub_concepts_used": [],
                "last_seen": today,
            })
            entry["count"] += 1
            entry["last_seen"] = today
            if trap_id and trap_id not in entry["traps_used"]:
                entry["traps_used"].append(trap_id)
            for sc in sub_concepts:
                if sc not in entry["sub_concepts_used"]:
                    entry["sub_concepts_used"].append(sc)

            # Accumulate trap usage for exhaustion check
            if trap_id:
                session_trap_counts[trap_id] = session_trap_counts.get(trap_id, 0) + 1

        # Re-evaluate trap exhaustion across full history
        all_trap_counts: Dict[str, int] = {}
        for entry in concepts_seen.values():
            for tid in entry.get("traps_used", []):
                all_trap_counts[tid] = all_trap_counts.get(tid, 0) + 1

        ledger["traps_exhausted"] = [
            tid for tid, cnt in all_trap_counts.items()
            if cnt >= _TRAP_EXHAUSTION_THRESHOLD
        ]
        ledger["total_questions_seen"] = ledger.get("total_questions_seen", 0) + len(skeletons)

        await redis.set(key, json.dumps(ledger), ex=_LEDGER_TTL_SECONDS)
        logger.info(
            f"[Ledger] Saved ledger for user={user_id} — "
            f"{ledger['total_questions_seen']} total questions seen"
        )
    except Exception as e:
        logger.warning(f"[Ledger] Failed to save ledger for {user_id}: {e}")


def build_diversity_constraints(
    ledger: Dict[str, Any],
    concept_pool: list,
    num_questions: int,
) -> str:
    """
    Build the DIVERSITY CONSTRAINTS prompt block from a user's ledger.

    Returns an empty string if ledger is None / has no meaningful history.
    """
    if not ledger:
        return ""

    concepts_seen: Dict[str, Any] = ledger.get("concepts_seen", {})
    traps_exhausted: List[str]    = ledger.get("traps_exhausted", [])

    if not concepts_seen and not traps_exhausted:
        return ""

    all_concept_names = {c["concept"] for c in concept_pool} if concept_pool else set()

    heavily_tested  = [
        name for name, entry in concepts_seen.items()
        if entry.get("count", 0) >= _HEAVY_CONCEPT_THRESHOLD
        and name in all_concept_names
    ]
    fresh_concepts  = [
        name for name in all_concept_names
        if concepts_seen.get(name, {}).get("count", 0) < _HEAVY_CONCEPT_THRESHOLD
    ]
    used_sub_concepts: List[str] = []
    for entry in concepts_seen.values():
        used_sub_concepts.extend(entry.get("sub_concepts_used", []))

    # Only emit the block if there's something meaningful to say
    if not heavily_tested and not traps_exhausted and not used_sub_concepts:
        return ""

    min_preferred_pct = min(60, max(40, int(100 * len(fresh_concepts) / max(1, len(all_concept_names)))))

    lines = ["═══════════════════════════════════════════════",
             "DIVERSITY CONSTRAINTS (personalised for this user's history):",
             ""]

    if heavily_tested:
        lines.append(
            f"  Concepts already heavily tested (use sparingly — max 1 question each):\n"
            f"    {', '.join(heavily_tested)}"
        )
    if traps_exhausted:
        lines.append(
            f"  Trap IDs seen {_TRAP_EXHAUSTION_THRESHOLD}+ times — DO NOT use these:\n"
            f"    {', '.join(traps_exhausted)}"
        )
    if used_sub_concepts:
        # Cap list for prompt length
        shown = used_sub_concepts[:20]
        lines.append(
            f"  Sub-concepts already tested (do NOT reuse exact topics):\n"
            + "\n".join(f"    - {sc}" for sc in shown)
        )
    if fresh_concepts:
        lines.append(
            f"  Preferred concepts (not yet tested or tested < {_HEAVY_CONCEPT_THRESHOLD} times):\n"
            f"    {', '.join(list(fresh_concepts)[:15])}"
        )
    lines.append(
        f"\n  REQUIREMENT: allocate at least {min_preferred_pct}% of questions to preferred concepts."
    )
    lines.append("═══════════════════════════════════════════════")
    return "\n".join(lines)
