"""
Stage 2 — Difficulty Injection

Pure data transformation — no LLM calls.
Looks up the skeleton's trap_strategy in the registry and attaches:
  • A structured TrapRule with generation rules
  • A prose difficulty_instruction block for the Stage 3 prompt
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from .models import DifficultyBundle, QuestionSkeleton, TrapRule

logger = logging.getLogger(__name__)

_REGISTRY_DIR = Path(__file__).parent

_SUBJECT_FILE_MAP: dict[str, str] = {
    "geography"           : "traps_geography.json",
    "polity"              : "traps_polity.json",
    "history"             : "traps_history.json",
    "economy"             : "traps_economy.json",
    "environment"         : "traps_environment.json",
    "environment & ecology": "traps_environment.json",
    "science & technology": "traps_science_technology.json",
    "science & tech"      : "traps_science_technology.json",
    "science_technology"  : "traps_science_technology.json",
}

# Cache: subject_slug → {trap_id: trap_dict}
_SUBJECT_TRAP_CACHE: dict[str, dict[str, dict]] = {}


def _get_trap_lookup(subject: str) -> dict[str, dict]:
    """Return a flat trap_id → trap_data dict for the given subject."""
    key = subject.lower().strip()
    if key in _SUBJECT_TRAP_CACHE:
        return _SUBJECT_TRAP_CACHE[key]

    slug = _SUBJECT_FILE_MAP.get(key)
    if not slug:
        for map_key, fname in _SUBJECT_FILE_MAP.items():
            if key in map_key or map_key in key:
                slug = fname
                break
    if not slug:
        slug = "traps_geography.json"

    path = _REGISTRY_DIR / slug
    lookup: dict[str, dict] = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for subj_key, subj_val in data.items():
            if subj_key == "_meta":
                continue
            for trap in subj_val.get("traps", []):
                lookup[trap["trap_id"]] = trap
        logger.info(f"✅ [V2 Stage 2] Loaded {len(lookup)} traps from {slug}")
    except Exception as e:
        logger.warning(f"⚠️ [V2 Stage 2] Could not load {slug}: {e}")

    _SUBJECT_TRAP_CACHE[key] = lookup
    return lookup


_DIFFICULTY_INSTRUCTIONS = {
    "easy": (
        "Make the question straightforward. "
        "The correct answer should be identifiable by a well-prepared student in under 30 seconds. "
        "Wrong options should be plausible but clearly distinguishable on reflection."
    ),
    "medium": (
        "Make the question require careful reading. "
        "At least one wrong option must seem very appealing at first glance. "
        "Apply the trap strategy precisely — the error in the wrong option must be subtle."
    ),
    "hard": (
        "Make the question genuinely difficult for a top 1% student. "
        "All wrong options must feel plausible. "
        "Apply the trap strategy aggressively — the false statements should use authentic-sounding "
        "details that are off by one specific fact. "
        "Do NOT make any option obviously absurd."
    ),
}

_QUESTION_TYPE_INSTRUCTIONS = {
    "multi_statement": (
        "Format: 'Consider the following statements:' then 2–3 numbered statements. "
        "The correct answer identifies which statements are TRUE/FALSE. "
        "Apply the trap in exactly one statement."
    ),
    "assertion_reason": (
        "Format: 'Assertion (A): <statement> / Reason (R): <statement>'. "
        "Options: (a) Both A and R correct, R explains A  "
        "(b) Both correct, R does NOT explain A  "
        "(c) A correct, R incorrect  "
        "(d) A incorrect, R correct. "
        "Apply the trap by making one of A or R subtly wrong via the trap strategy."
    ),
    "match_pair": (
        "Format: Two columns, 4 items each. "
        "UPSC standard: List I items / List II items. "
        "Options are (a)–(d) with different matchings. "
        "Apply the trap by swapping two related items that students commonly confuse."
    ),
    "fact": (
        "Direct factual question — 'Which of the following is correct regarding X?' "
        "Four options, exactly one correct. "
        "Apply the trap by using the wrong option that the trap strategy targets."
    ),
    "spatial": (
        "Question involves a map or directional reasoning — "
        "'Which of the following rivers flows through State X before entering State Y?' "
        "or 'Arrange the following from North to South'. "
        "Apply direction_error or adjacent_fact trap strategy."
    ),
}


def _build_difficulty_instruction(skeleton: QuestionSkeleton, trap: dict | None) -> str:
    parts = []

    # Difficulty prose
    diff_text = _DIFFICULTY_INSTRUCTIONS.get(
        skeleton.difficulty,
        _DIFFICULTY_INSTRUCTIONS["medium"]
    )
    parts.append(f"DIFFICULTY [{skeleton.difficulty.upper()}]: {diff_text}")

    # Question type format
    type_text = _QUESTION_TYPE_INSTRUCTIONS.get(
        skeleton.question_type,
        _QUESTION_TYPE_INSTRUCTIONS["multi_statement"]
    )
    parts.append(f"\nQUESTION FORMAT [{skeleton.question_type}]: {type_text}")

    # Trap instruction
    if trap:
        parts.append(
            f"\nTRAP STRATEGY [{trap['trap_id']} — {trap['name']}]: {trap['description']}\n"
            f"How to apply: {trap['how_to_generate']}\n"
            f"Distractor strategy: {trap['distractor_strategy']}"
        )
        if trap.get("real_pyq_example"):
            parts.append(f"Real PYQ pattern: {trap['real_pyq_example']}")
    elif skeleton.trap_strategy:
        # trap_id not in registry (e.g. from LLM hallucination) — generic instruction
        parts.append(
            f"\nTRAP STRATEGY [{skeleton.trap_strategy}]: "
            "Include at least one wrong option that exploits common student confusion "
            "about this concept. The trap must be in the wrong options, not in the correct one."
        )

    return "\n".join(parts)


def inject_difficulty(skeletons: List[QuestionSkeleton], subject: str = "Geography") -> List[DifficultyBundle]:
    """
    Stage 2: attach trap rules and difficulty instructions to each skeleton.
    Only traps for the given subject are matched.
    No LLM calls, O(n) pure transformation.
    """
    logger.info(f"💉 [Stage 2] Injecting difficulty into {len(skeletons)} skeletons (subject={subject}) …")
    trap_lookup = _get_trap_lookup(subject)
    bundles: List[DifficultyBundle] = []

    for sk in skeletons:
        trap_data = trap_lookup.get(sk.trap_strategy)
        trap_rule: TrapRule | None = None

        if trap_data:
            trap_rule = TrapRule(
                trap_id=trap_data["trap_id"],
                trap_name=trap_data["name"],
                description=trap_data["description"],
                how_to_generate=trap_data["how_to_generate"],
                distractor_strategy=trap_data["distractor_strategy"],
                generation_rules=trap_data.get("generation_rules", {}),
                real_pyq_example=trap_data.get("real_pyq_example", ""),
            )

        instruction = _build_difficulty_instruction(sk, trap_data)

        bundles.append(
            DifficultyBundle(
                skeleton=sk,
                trap_rule=trap_rule,
                difficulty_instruction=instruction,
            )
        )

    hit_count = sum(1 for b in bundles if b.trap_rule is not None)
    logger.info(
        f"✅ [Stage 2] Difficulty injection done. "
        f"{hit_count}/{len(bundles)} skeletons matched a {subject} trap."
    )
    return bundles
