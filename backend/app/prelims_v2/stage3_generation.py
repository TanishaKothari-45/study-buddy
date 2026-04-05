"""
Stage 3 — Question Generation (Batch Mode)

DIRECT pipeline: Stage 0 → Stage 1 → Stage 3 (no Stage 2 intermediary)

Builds a single structured prompt for all N skeletons and sends 1 Gemini Pro call.
Each QUESTION N: section is bounded to its own retrieved chunks + CA context.

Inputs:
  - skeletons:      List[QuestionSkeleton] from Stage 0 v4.5 Controlled
  - retrieval_map:  Dict[skeleton_id → RetrievalResult] from Stage 1 (LLM-gen exploratory)
  - trap_registry:  trap_id → trap_data lookup (on-demand during prompt assembly)

Process:
  1. Look up trap data for each skeleton.trap_strategy
  2. Format 65 chunks per skeleton (50 structured + 15 exploratory from Stage 1)
  3. Build prompt with difficulty rules, trap injection, cross-concept instructions
  4. Call Gemini with batch temperature (0.75-0.90 depending on batch size)
  5. Parse structured JSON response → V2GeneratedQuestion objects

Batch temperature strategy:
  ≤ 5   → 0.75 (medium)
  ≤ 10  → 0.83 (medium↑ blend)
  ≤ 15  → 0.85 (heavy hard bias)
  ≥ 20  → 0.82 (50% hard, 25% medium, 25% easy weighted avg)

Structured output uses Pydantic schema (GeneratedQuestionBatch).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

from app.utils.mock_test_prompting import (
    get_system_prompt,
    get_cognitive_framework,
)


# ── Pydantic output schema for batch generation ───────────────────────────────

class GeneratedQuestion(BaseModel):
    question:       str
    options:        List[str]
    correct_answer: str
    explanation:    str
    source:         Dict[str, str] = {}


class GeneratedQuestionBatch(BaseModel):
    questions: List[GeneratedQuestion]


# ── Batch temperature strategy ────────────────────────────────────────────────

def get_batch_temperature(num_questions: int) -> float:
    """
    Returns the temperature to use for a batch call.
    For multi-batch scenarios the orchestrator will split into sub-batches
    and call this per sub-batch — here we return the temperature for a single
    uniform batch.

      ≤ 5   → 0.75 (medium)
      ≤ 10  → 0.83 (medium↑ — blend of medium + hard)
      ≤ 15  → 0.85 (heavy hard bias)
      ≥ 20  → 0.82 (50% hard, 25% medium, 25% easy weighted avg)
    """
    if num_questions <= 5:
        return 0.75
    if num_questions <= 10:
        return 0.83
    if num_questions <= 15:
        return 0.85
    return 0.82


def split_into_batches(skeletons: list, num_questions: int) -> List[List]:
    """
    Splits skeletons into sub-batches based on total count.

      ≤ 5   → 1 batch (all medium temp)
      ≤ 10  → 2 batches of ~5 (batch 1 = medium, batch 2 = hard)
      ≤ 15  → 3 batches (2 hard, 1 medium)
      ≥ 20  → batches of 5; 50% hard, 25% easy, 25% medium
    """
    if num_questions <= 5:
        return [skeletons]
    batch_size = 5
    batches = [
        skeletons[i: i + batch_size]
        for i in range(0, len(skeletons), batch_size)
    ]
    return batches


def get_sub_batch_temperature(batch_index: int, total_batches: int, total_questions: int) -> float:
    """
    Temperature per sub-batch based on user spec:
      ≤ 5   → single batch  → medium (0.75)
      ≤ 10  → 2 batches     → batch 0=medium, batch 1=hard
      ≤ 15  → 3 batches     → batch 0=hard, batch 1=hard, batch 2=medium
      ≥ 20  → N batches     → 50% hard(0.90), 25% medium(0.75), 25% easy(0.50)
    """
    if total_questions <= 5:
        return 0.75
    if total_questions <= 10:
        return 0.90 if batch_index >= 1 else 0.75
    if total_questions <= 15:
        return 0.75 if batch_index == total_batches - 1 else 0.90
    # ≥ 20: assign hard to first 50%, easy to last 25%, medium to middle 25%
    hard_cutoff   = math.ceil(total_batches * 0.50)
    easy_cutoff   = total_batches - math.ceil(total_batches * 0.25)
    if batch_index < hard_cutoff:
        return 0.90
    if batch_index >= easy_cutoff:
        return 0.50
    return 0.75


# ── Trap registry loader ──────────────────────────────────────────────────────

_trap_cache: dict = {}

def _get_trap(trap_id: str, trap_registry_path: Path) -> dict:
    """
    Load trap data on-demand from trap_registry.json.
    Cached for performance (loaded once, reused across all skeletons).

    Called during Stage 3 prompt assembly (no Stage 2 intermediary).
    """
    global _trap_cache
    if not _trap_cache:
        try:
            logger.info(f"[Stage3][TrapRegistry] Attempting to load from: {trap_registry_path}")
            logger.info(f"[Stage3][TrapRegistry] File exists: {trap_registry_path.exists()}")

            if not trap_registry_path.exists():
                logger.warning(f"[Stage3][TrapRegistry] ❌ File not found: {trap_registry_path}")
                return {}

            with open(trap_registry_path, encoding="utf-8") as f:
                raw = json.load(f)

            logger.info(f"[Stage3][TrapRegistry] Raw JSON keys: {list(raw.keys())}")

            # Build flat lookup — try multiple structures

            # Structure 1: Top-level "traps" key
            if "traps" in raw:
                for t in raw["traps"]:
                    _trap_cache[t["trap_id"]] = t
                logger.info(f"[Stage3][TrapRegistry] ✅ Loaded {len(_trap_cache)} traps (top-level 'traps' key)")

            # Structure 2: "trap_patterns_global_reference" key (new structure)
            elif "trap_patterns_global_reference" in raw:
                trap_ref = raw["trap_patterns_global_reference"]
                if isinstance(trap_ref, dict):
                    for trap_id, trap_data in trap_ref.items():
                        if isinstance(trap_data, dict):
                            _trap_cache[trap_id] = {**trap_data, "trap_id": trap_id}
                logger.info(f"[Stage3][TrapRegistry] ✅ Loaded {len(_trap_cache)} traps from 'trap_patterns_global_reference'")

            # Structure 3: "concept_trap_mapping" + "trap_patterns" (hierarchical domain files)
            elif "concept_trap_mapping" in raw and "trap_patterns" in raw:
                concept_mapping = raw.get("concept_trap_mapping", {})
                trap_patterns = raw.get("trap_patterns", {})

                # Flatten: collect all trap IDs from mapping and fetch their data from patterns
                all_trap_ids = set()
                for concept_name, trap_ids in concept_mapping.items():
                    if isinstance(trap_ids, list):
                        all_trap_ids.update(trap_ids)

                # If mapping is empty (all arrays are empty), use all trap IDs from trap_patterns
                if not all_trap_ids and trap_patterns:
                    all_trap_ids = set(trap_patterns.keys())
                    logger.debug(f"[Stage3][TrapRegistry] concept_trap_mapping was empty, using all {len(all_trap_ids)} trap IDs from trap_patterns")

                # Build cache from trap_patterns
                for trap_id in all_trap_ids:
                    if trap_id in trap_patterns:
                        trap_data = trap_patterns[trap_id]
                        _trap_cache[trap_id] = {**trap_data, "trap_id": trap_id} if isinstance(trap_data, dict) else {"trap_id": trap_id}

                # Show first 5 trap IDs loaded
                sample_ids = sorted(list(_trap_cache.keys()))[:5]
                logger.info(f"[Stage3][TrapRegistry] ✅ Loaded {len(_trap_cache)} traps from 'concept_trap_mapping' + 'trap_patterns'. Sample IDs: {sample_ids}")

            # Structure 4: Nested by subject
            else:
                for subj, val in raw.items():
                    if subj in ("_meta", "description", "subject", "question_types", "sub_domains_covered", "notes", "subdomain", "concept_trap_mapping", "trap_patterns", "generation_guidance_by_question_type", "common_misconceptions_by_concept", "notes_for_blueprint"):
                        continue
                    if isinstance(val, dict) and "traps" in val:
                        count_before = len(_trap_cache)
                        for t in val["traps"]:
                            _trap_cache[t["trap_id"]] = t
                        count_added = len(_trap_cache) - count_before
                        logger.info(f"[Stage3][TrapRegistry]   • {subj}: +{count_added} traps")
                logger.info(f"[Stage3][TrapRegistry] ✅ Total loaded: {len(_trap_cache)} traps")

            if len(_trap_cache) == 0:
                logger.error(f"[Stage3][TrapRegistry] ❌ No traps found in registry. Structure: {list(raw.keys())}\nTry checking if traps are in 'traps', 'trap_patterns_global_reference', 'concept_trap_mapping'+'trap_patterns', or nested by subject.")
        except Exception as e:
            logger.error(f"[Stage3][TrapRegistry] ❌ Could not load trap registry: {e}", exc_info=True)

    trap = _trap_cache.get(trap_id, {})
    if not trap:
        logger.warning(f"[Stage3][TrapRegistry] ⚠️ Trap not found for ID: {trap_id}")
    else:
        logger.debug(f"[Stage3][TrapRegistry] ✓ Found trap: {trap_id}")
    return trap


# ── Chunk formatter ───────────────────────────────────────────────────────────

def _format_chunks(chunks: List[Dict]) -> str:
    if not chunks:
        return "No static content retrieved. Use your knowledge grounded in NCERT and standard Geography texts."
    lines = []
    for i, chunk in enumerate(chunks, 1):
        content  = chunk.get("content", "").strip()
        meta     = chunk.get("metadata", {})
        concept  = meta.get("major_domain", meta.get("sub_domain", ""))
        label    = f"[Chunk {i} — {concept}]" if concept else f"[Chunk {i}]"
        lines.append(f"{label}\n{content}")
    return "\n\n".join(lines)



# -- Difficulty type loader (from JSON) -----------------------------------------

_V2_DIR = Path(__file__).parent
_difficulty_type_cache: dict = {}

_DIFFICULTY_FALLBACK = {
    "easy": "Test direct recall. One clear correct answer. Distractors are plausible but clearly distinguishable with basic knowledge.",
    "medium": "At least one distractor must be partially true. Student must reason through each option, not just recall. Use qualifier precision: 'always' vs 'usually', 'only' vs 'primarily'.",
    "hard": "All distractors must be real facts -- just wrong for this specific question. A student who has studied but not deeply reasoned should get this wrong. The trap must be clearly visible in the question structure.",
}


def _load_difficulty_types(subject: str) -> dict:
    """Load and cache difficulty_types JSON for a subject."""
    global _difficulty_type_cache
    key = subject.lower().replace(" ", "_")
    if key in _difficulty_type_cache:
        return _difficulty_type_cache[key]

    filename = f"difficulty_types_{key}_base.json"
    path = _V2_DIR / filename
    if not path.exists():
        logger.warning(f"[Stage3] Difficulty types file not found: {path}")
        _difficulty_type_cache[key] = {}
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        types = data.get("difficulty_types", {})
        _difficulty_type_cache[key] = types
        logger.info(f"[Stage3] Loaded {len(types)} difficulty types for {subject}")
        return types
    except Exception as e:
        logger.error(f"[Stage3] Failed to load difficulty types: {e}")
        _difficulty_type_cache[key] = {}
        return {}


def _get_difficulty_block(skeleton, subject: str) -> str:
    """
    Build difficulty instruction from the specific difficulty_type JSON.
    Falls back to generic easy/medium/hard if no match found.
    """
    diff_type = getattr(skeleton, "difficulty_type", "")
    diff = skeleton.difficulty

    types = _load_difficulty_types(subject)
    dt_data = types.get(diff_type, {}) if diff_type else {}

    if dt_data:
        characteristics = "\n".join(f"  - {c}" for c in dt_data.get("characteristics", []))
        gen_rules = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(dt_data.get("generation_rules", [])))
        q_structure = dt_data.get("question_structure", "")

        return f"""DIFFICULTY: {diff.upper()} -- Type: {diff_type}
  {dt_data.get('description', '')}

  Characteristics:
{characteristics}

  Question structure: {q_structure}

  Generation steps:
{gen_rules}"""
    else:
        return f"DIFFICULTY: {diff.upper()}\n  {_DIFFICULTY_FALLBACK.get(diff, _DIFFICULTY_FALLBACK['medium'])}"


# -- Trap injection block (enriched) -------------------------------------------

def _trap_injection(trap: dict, question_type: str) -> str:
    """Inject full trap data including generation_rules and distractor_strategy."""
    if not trap:
        return ""

    name      = trap.get("name", "")
    mechanism = trap.get("mechanism", "")
    how_to    = trap.get("how_to_generate", "")
    error_type = trap.get("error_type", "")
    distractor_strategy = trap.get("distractor_strategy", "")
    gen_rules = trap.get("generation_rules", [])
    pyq_example = trap.get("real_pyq_example", trap.get("example_question", ""))

    lines = [f"TRAP STRATEGY: {name}"]
    if error_type:
        lines.append(f"  Error type: {error_type} (the specific mistake students make)")
    lines.append(f"  Mechanism: {mechanism}")
    if distractor_strategy:
        lines.append(f"  Distractor strategy: {distractor_strategy}")
    if gen_rules:
        lines.append("  Steps to build this trap:")
        for i, rule in enumerate(gen_rules, 1):
            lines.append(f"    {i}. {rule}")
    if how_to:
        lines.append(f"  How to generate: {how_to}")
    if pyq_example:
        lines.append(f"  UPSC reference (style only, do not copy): {pyq_example[:300]}")

    return "\n".join(lines)


# -- Cross-concept instruction -------------------------------------------------

def _cross_concept_instruction(skeleton) -> str:
    """
    If sub_concepts contain borrowed topics (source_concept != ""),
    guide the LLM on how to use cross-concept material.
    """
    borrowed = [
        sc for sc in skeleton.sub_concepts
        if sc.source_concept and sc.source_concept != skeleton.concept
    ]
    if not borrowed:
        return ""

    blines = "\n".join(
        f'  - "{sc.topic}" (from {sc.source_concept})'
        for sc in borrowed
    )

    linked = getattr(skeleton, "linked_concept", None)
    ar_note = ""
    if linked and skeleton.question_type == "assertion_reason":
        ar_note = (
            f"\n  For this Assertion-Reason question:"
            f"\n    Assertion = fact about {skeleton.concept}"
            f"\n    Reason = mechanism from {linked} that explains (or SEEMS to explain) the Assertion"
            f"\n    Hard trap: Reason is TRUE but does NOT correctly explain the Assertion."
        )

    return f"""CROSS-CONCEPT LINKAGE:
  These sub_concepts are borrowed from other concepts. They should appear
  in the question or distractors -- not only in the explanation.
{blines}{ar_note}"""


# -- Shared per-question block builder ------------------------------------------

def _build_question_block(
    idx: int,
    skeleton,
    retrieval_map: dict,
    trap_registry_path: Path,
    pyq_chunks: Optional[List[Dict]],
    subject: str,
) -> str:
    """
    Build the prompt block for a single skeleton.
    Used by both assemble_skeleton_prompt and assemble_batch_prompt.
    """
    concept = skeleton.concept
    qtype   = skeleton.question_type
    diff    = skeleton.difficulty

    # Sub_concepts
    sc_lines = "\n".join(
        f'    - {sc.topic} [aspect={sc.aspect}'
        + (f', from={sc.source_concept}' if sc.source_concept else '') + ']'
        for sc in skeleton.sub_concepts
    )

    # Difficulty type rules (from JSON, not generic)
    diff_block = _get_difficulty_block(skeleton, subject)

    # Trap (enriched: generation_rules + distractor_strategy)
    trap     = _get_trap(skeleton.trap_strategy, trap_registry_path)
    trap_blk = _trap_injection(trap, qtype)

    # Cross-concept
    cross_blk = _cross_concept_instruction(skeleton)

    # Static chunks
    retrieval_result = retrieval_map.get(skeleton.skeleton_id)
    is_pure_ca = getattr(skeleton, "pure_ca", False)

    if is_pure_ca:
        static_text = ""
        logger.info(
            f"[Stage3][Q{idx}/{skeleton.skeleton_id}] Pure CA -- skipping static chunks"
        )
    elif retrieval_result:
        chunks_to_use = retrieval_result.static_chunks
        static_text = _format_chunks(chunks_to_use)
        logger.info(
            f"[Stage3][Q{idx}/{skeleton.skeleton_id}] {len(chunks_to_use)} chunks"
        )
    else:
        static_text = "No static content retrieved. Use your knowledge grounded in NCERT texts."
        logger.warning(f"[Stage3][Q{idx}] No retrieval result for {skeleton.skeleton_id}")

    # CA context
    ca_block = ""
    if skeleton.ca_flag and retrieval_result and retrieval_result.ca_context:
        if is_pure_ca:
            ca_block = (
                f"\n  PURE CURRENT AFFAIRS QUESTION:"
                f"\n  {retrieval_result.ca_context[:1500]}"
                f"\n  Create a question entirely about this event/development."
                f"\n  Test impact, causes, policy responses, or factual details."
            )
        else:
            ca_block = (
                f"\n  CURRENT AFFAIRS CONTEXT:"
                f"\n  {retrieval_result.ca_context[:1200]}"
                f"\n  Integrate this event naturally into the question stem."
                f"\n  The static concept drives correctness; CA provides contemporary framing."
            )

    # Constraints
    available_qts = getattr(skeleton, "available_question_types", [qtype])
    available_traps = getattr(skeleton, "available_trap_ids", [skeleton.trap_strategy])

    constraints_info = ""
    if available_qts:
        constraints_info += f"  Valid question_types: {', '.join(available_qts)}\n"
    if available_traps:
        constraints_info += f"  Valid trap_ids: {', '.join(available_traps)}\n"

    # PYQ
    pyq_display = "Standard UPSC Prelims style -- formal, concise."
    if pyq_chunks:
        relevant = [
            c for c in pyq_chunks
            if qtype.replace("_", "").lower() in
               c.get("metadata", {}).get("pattern_type", "").replace("_", "").lower()
        ] or pyq_chunks[:1]
        if relevant:
            pyq_display = relevant[0].get("content", "")[:250] or pyq_display

    return f"""
---
QUESTION {idx}:
  concept: {concept}
  question_type: {qtype}
  difficulty: {diff}
  trap_strategy: {skeleton.trap_strategy}
{constraints_info}
  sub_concepts:
{sc_lines}

{diff_block}

{trap_blk}

{cross_blk}

  REFERENCE CONTENT (primarily for this question; you may draw from other material if it genuinely strengthens the question):
{static_text if static_text else '(Pure CA question -- no static content)'}
{ca_block}

  PYQ STYLE: {pyq_display}
"""


# -- Question type formatting rules (trimmed to relevant types) ----------------

_TYPE_FORMAT = {
    "multi_statement": """multi_statement: "Consider the following statements regarding [topic]:
  1. [Statement 1]
  2. [Statement 2]
  3. [Statement 3]
  Which of the statements given above is/are correct?"
  Options: (a) 1 only  (b) 1 and 2 only  (c) 2 and 3 only  (d) 1, 2 and 3""",

    "assertion_reason": """assertion_reason: "Assertion (A): [text]
  Reason (R): [text]
  Which of the following is correct?"
  Options: (a) Both A and R are true and R is the correct explanation of A
           (b) Both A and R are true but R is NOT the correct explanation of A
           (c) A is true but R is false
           (d) A is false but R is true""",

    "match_pair": """match_pair: "Match the following:
  List I              List II
  1. [Item 1]         (a) [Match a]
  2. [Item 2]         (b) [Match b]
  3. [Item 3]         (c) [Match c]
  4. [Item 4]         (d) [Match d]
  Select the correct answer using the code given below:"
  Options encode column pairings, e.g. (a) 1-b, 2-a, 3-d, 4-c""",

    "direct_fact": "direct_fact: Single stem question, 4 options (a)-(d), one correct.",
    "spatial": "spatial: Test geographic location, distribution, or map-based reasoning. 4 options (a)-(d).",
    "chronology": "chronology: Test correct temporal ordering of events/processes. 4 options (a)-(d).",
    "data_based": "data_based: Present data (table/figure description) and test interpretation. 4 options (a)-(d).",

    "how_many": """how_many: "Consider the following statements regarding [topic]:
  1. [Statement 1]
  2. [Statement 2]
  3. [Statement 3]
  4. [Statement 4]
  How many of the above statements are correct?"
  Options: (a) Only one  (b) Only two  (c) Only three  (d) All four
  NOTE: Craft statements so the correct count is non-obvious (avoid trivial all-true or all-false). \
Each wrong statement must embed a specific factual error (number, direction, mechanism) not a vague one.""",

    "single_best_answer": """single_best_answer: Single stem question where all options contain \
a partial truth, but only one is the most precise/complete answer.
  Format: "[Question stem]?"
  Options: (a)-(d), each option plausible but only one is fully correct.
  NOTE: Distractors must be subtly wrong — a wrong scale, a missing qualifier, an incorrect \
causal link — not obviously false.""",
}


def _get_type_format_rules(question_types: List[str]) -> str:
    """Return formatting rules only for the question types in this batch."""
    unique_types = sorted(set(question_types))
    rules = []
    for qt in unique_types:
        if qt in _TYPE_FORMAT:
            rules.append(_TYPE_FORMAT[qt])
        elif qt == "pure_ca" and "direct_fact" in _TYPE_FORMAT:
            rules.append(_TYPE_FORMAT["direct_fact"])
    if not rules:
        rules = [_TYPE_FORMAT["direct_fact"]]
    return "QUESTION TYPE FORMATS:\n" + "\n\n".join(rules)


# -- Single-question prompt assembler (fallback) -------------------------------

def assemble_skeleton_prompt(
    skeleton,
    retrieval_result,
    trap_registry_path: Path,
    pyq_chunks: Optional[List[Dict]] = None,
) -> str:
    """
    Build a prompt for generating ONE question (per-skeleton fallback).
    Uses _build_question_block for the question spec, wraps in full prompt.
    """
    subject = skeleton.sub_domain
    retrieval_map = {skeleton.skeleton_id: retrieval_result}

    question_block = _build_question_block(
        idx=1,
        skeleton=skeleton,
        retrieval_map=retrieval_map,
        trap_registry_path=trap_registry_path,
        pyq_chunks=pyq_chunks,
        subject=subject,
    )

    type_rules = _get_type_format_rules([skeleton.question_type])

    prompt = f"""You are an expert UPSC Prelims question paper setter.
Generate exactly 1 question.

{type_rules}

{question_block}

EXPLANATION QUALITY:
  Explain the correct answer with factual reasoning. For each wrong option,
  state what specific fact or mechanism makes it wrong. If a trap was used,
  explain what a student who got this wrong would have been thinking.

OUTPUT -- return ONLY this JSON, no markdown:
{{{{
  "question":       "Full question text",
  "options":        ["(a) ...", "(b) ...", "(c) ...", "(d) ..."],
  "correct_answer": "A",
  "explanation":    "Detailed explanation as described above.",
  "source":         {{{{"concept": "{skeleton.concept}", "sub_domain": "{subject}", "trap_used": "{skeleton.trap_strategy}"}}}}
}}}}
"""
    return prompt.strip()


# -- Batch prompt assembler -------------------------------------------------

def assemble_batch_prompt(
    skeletons:          list,
    retrieval_map:      dict,
    trap_registry_path: Path,
    pyq_chunks:         Optional[List[Dict]] = None,
    subject:            str = "",
) -> str:
    """
    Build a single prompt for N skeletons + 20% extra.
    Uses _build_question_block for each skeleton (shared with single-question path).
    """
    if not skeletons:
        return ""

    n        = len(skeletons)
    n_target = math.ceil(n * 1.2)  # 20% extra: 6 for 5, 12 for 10
    subj     = subject or (skeletons[0].sub_domain if skeletons else "")

    logger.info(
        f"[Stage3][BatchPrompt] Building batch prompt: {n} skeletons, "
        f"requesting {n_target} questions"
    )

    # Type format rules -- only for types in this batch
    batch_types = [sk.question_type for sk in skeletons]
    type_rules  = _get_type_format_rules(batch_types)

    # Per-question blocks via shared helper
    question_blocks = []
    for idx, skeleton in enumerate(skeletons, 1):
        block = _build_question_block(
            idx=idx,
            skeleton=skeleton,
            retrieval_map=retrieval_map,
            trap_registry_path=trap_registry_path,
            pyq_chunks=pyq_chunks,
            subject=subj,
        )
        question_blocks.append(block)

    questions_section = "\n".join(question_blocks)

    return f"""You are an expert UPSC Prelims question paper setter.
Generate exactly {n_target} questions.

GUIDELINES:
  1. Each question spec below has its own context, difficulty type, and trap strategy.
     Follow them closely. You may draw from any provided material if it genuinely
     strengthens a question, but each question must primarily test its specified concept.
  2. Each question must use the specified question_type and trap_strategy.
  3. Every question must be distinct -- test different angles, facts, or mechanisms.
  4. All {n_target} questions must be equally high quality.

{type_rules}

{questions_section}

EXPLANATION QUALITY:
  For each question, the explanation must:
  - State the correct answer with factual reasoning
  - For each wrong option, explain what specific fact or mechanism makes it wrong
  - If a trap was used, explain what a student who got this wrong would have been thinking

OUTPUT -- return ONLY this JSON, no markdown:
{{{{
  "questions": [
    {{{{
      "question":       "Full question text",
      "options":        ["(a) ...", "(b) ...", "(c) ...", "(d) ..."],
      "correct_answer": "A",
      "explanation":    "Detailed explanation as described above.",
      "source":         {{{{"concept": "<concept name>", "sub_domain": "<subject>", "trap_used": "<trap_id>"}}}}
    }}}}
  ]
}}}}

Generate exactly {n_target} objects in the "questions" array.
""".strip()

# \u2500\u2500 Batch response parser \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

import re as _re

def parse_batch_response(
    text:      str,
    skeletons: list,
) -> List[Optional["V2GeneratedQuestion"]]:
    """
    Parse a batch Gemini response into a list of V2GeneratedQuestion objects.

    Strategy:
      1. Validate with GeneratedQuestionBatch Pydantic model (strict, clean JSON).
      2. Fallback: strip markdown fences and retry.
      3. Fallback: regex-extract individual JSON objects by position.
      Returns a list of the same length as skeletons; None entries = generation failed.
    """
    from .models import V2GeneratedQuestion

    def _make_q(data: dict, skeleton) -> Optional["V2GeneratedQuestion"]:
        q_text  = data.get("question", "").strip()
        options = data.get("options", [])
        correct = data.get("correct_answer", "").strip().upper()
        expl    = data.get("explanation", "").strip()
        if not q_text or len(options) < 4 or correct not in ("A", "B", "C", "D"):
            return None
        src = data.get("source", {})
        # Handle extra questions with no assigned skeleton
        if skeleton:
            return V2GeneratedQuestion(
                skeleton_id    = skeleton.skeleton_id,
                question       = q_text,
                options        = options[:4],
                correct_answer = correct,
                explanation    = expl,
                sub_domain     = src.get("sub_domain", skeleton.sub_domain),
                difficulty     = skeleton.difficulty,
                question_type  = skeleton.question_type,
            )
        else:
            # Extra question — use source or defaults
            return V2GeneratedQuestion(
                skeleton_id    = f"extra_{id(q_text)}",  # Synthetic ID for extra questions
                question       = q_text,
                options        = options[:4],
                correct_answer = correct,
                explanation    = expl,
                sub_domain     = src.get("sub_domain", "Unknown"),
                difficulty     = src.get("difficulty", "medium"),
                question_type  = src.get("question_type", "mcq"),
            )

    text = text.strip()

    # 1. Try Pydantic full validation (preferred \u2014 structured output from Gemini)
    try:
        batch = GeneratedQuestionBatch.model_validate_json(text)
        results = []
        for i, q_data in enumerate(batch.questions):
            # Map first N to skeletons, rest are extras
            skeleton = skeletons[i] if i < len(skeletons) else None
            q = _make_q(q_data.model_dump(), skeleton)
            results.append(q)

        passed = sum(1 for r in results if r)
        logger.info(
            f"[Stage3][Batch] Pydantic parse: {passed} / {len(batch.questions)} questions OK "
            f"({len(skeletons)} primary slots + {len(batch.questions) - len(skeletons)} extras)"
        )
        return results
    except Exception:
        pass

    # 2. Strip markdown fences and retry
    cleaned = _re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        batch = GeneratedQuestionBatch.model_validate_json(cleaned)
        results = []
        for i, q_data in enumerate(batch.questions):
            # Map first N to skeletons, rest are extras
            skeleton = skeletons[i] if i < len(skeletons) else None
            q = _make_q(q_data.model_dump(), skeleton)
            results.append(q)

        passed = sum(1 for r in results if r)
        logger.info(
            f"[Stage3][Batch] Cleaned Pydantic parse: {passed} / {len(batch.questions)} questions OK "
            f"({len(skeletons)} primary slots + {len(batch.questions) - len(skeletons)} extras)"
        )
        return results
    except Exception:
        pass

    # 3. Regex fallback: extract individual JSON objects
    logger.warning("[Stage3][Batch] Pydantic parse failed, falling back to regex extraction")
    objects = _re.findall(r'\{[^{}]*"question"[^{}]*\}', cleaned, _re.DOTALL)
    results = []
    for i, obj_text in enumerate(objects):
        try:
            data = json.loads(obj_text)
            # Map first N to skeletons, rest are extras
            skeleton = skeletons[i] if i < len(skeletons) else None
            results.append(_make_q(data, skeleton))
        except Exception:
            results.append(None)

    ok = sum(1 for r in results if r)
    logger.info(
        f"[Stage3][Batch] Regex fallback: {ok} / {len(objects)} questions OK "
        f"({len(skeletons)} primary slots + {len(objects) - len(skeletons)} extras)"
    )
    return results


# ── Direct Pipeline Orchestration (Stage 0 → 1 → 3) ────────────────────────────

async def generate_questions_batch(
    skeletons: List,
    retrieval_map: Dict,
    gemini_client,
    trap_registry_path: Path,
    subject: str = "Geography",
    pyq_chunks: Optional[List[Dict]] = None,
) -> tuple[List, List[str]]:
    """
    Stage 3: Generate questions directly from Stage 0 skeletons + Stage 1 retrieval.

    PIPELINE (No Stage 2):
      Stage 0 (v4.5 Controlled) → skeletons with constraints
      Stage 1 (LLM-gen retrieval) → retrieval_map with 65 chunks per skeleton
      Stage 3 (this function) → Generate questions directly

    INPUTS:
      - skeletons:         List[QuestionSkeleton] from Stage 0
      - retrieval_map:     Dict[skeleton_id → RetrievalResult] from Stage 1
      - gemini_client:     Initialized Gemini client
      - trap_registry_path: Path to trap JSON
      - subject:           Subject for cognitive framework
      - pyq_chunks:        Optional PYQ style examples

    PROCESS:
      1. Split skeletons into batches (5 per batch for efficiency)
      2. For each batch: assemble prompt + call Gemini
      3. Parse responses with fallback logic
      4. Track pass/fail per batch

    OUTPUTS:
      - (passed_questions, failed_skeleton_ids)
      - All questions have skeleton_id, question_type, difficulty, explanation

    TEMPERATURE STRATEGY:
      - ≤5:  0.75 (medium)
      - ≤10: 0.83 (medium↑)
      - ≤15: 0.85 (heavy hard)
      - ≥20: 0.82 (mixed)
    """
    logger.info(f"[Stage3] Starting question generation for {len(skeletons)} skeletons (direct pipeline, no Stage 2)")

    # Split into batches
    batches = split_into_batches(skeletons, len(skeletons))
    all_questions = []
    failed_ids = []

    for batch_idx, batch in enumerate(batches):
        logger.info(f"[Stage3] Batch {batch_idx + 1}/{len(batches)}: generating {len(batch)} questions")

        # Assemble prompt
        prompt = assemble_batch_prompt(
            skeletons=batch,
            retrieval_map=retrieval_map,
            trap_registry_path=trap_registry_path,
            pyq_chunks=pyq_chunks,
            subject=subject,
        )

        # Determine temperature for this batch
        temperature = get_sub_batch_temperature(batch_idx, len(batches), len(skeletons))

        try:
            # Call Gemini with structured output schema
            response = await gemini_client.generate_response(
                user_prompt=prompt,
                response_schema=GeneratedQuestionBatch,
                temperature=temperature,
            )

            # Parse response
            if isinstance(response, str):
                response_text = response
            else:
                response_text = response.model_dump_json() if hasattr(response, 'model_dump_json') else str(response)

            questions = parse_batch_response(response_text, batch)

            # Track results: first N map to batch, rest are extras
            skeleton_map = {sk.skeleton_id: sk for sk in batch}
            for i, q in enumerate(questions):
                if i < len(batch):
                    skeleton = batch[i]
                    if q:
                        all_questions.append(q)
                        logger.debug(f"[Stage3] ✓ {skeleton.skeleton_id}: {skeleton.question_type}")
                    else:
                        failed_ids.append(skeleton.skeleton_id)
                        logger.debug(f"[Stage3] ✗ {skeleton.skeleton_id}: parse failed")
                else:
                    # Extra question
                    if q:
                        all_questions.append(q)
                        logger.debug(f"[Stage3] ✓ EXTRA: {q.question_type}")

            logger.info(
                f"[Stage3] Batch {batch_idx + 1} complete: "
                f"{sum(1 for q in questions if q)}/{len(questions)} OK "
                f"({len(batch)} primary + {len(questions) - len(batch)} extras), "
                f"temp={temperature}"
            )

        except Exception as e:
            logger.error(f"[Stage3] Batch {batch_idx + 1} failed: {e}")
            for skeleton in batch:
                failed_ids.append(skeleton.skeleton_id)

    logger.info(
        f"[Stage3] Generation complete: {len(all_questions)} passed, {len(failed_ids)} failed"
    )
    return all_questions, failed_ids
