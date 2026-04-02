"""
Stage 3 — Question Generation (Batch Mode)

Builds a single structured prompt for all N skeletons and sends 1 Gemini Pro call.
Each QUESTION N: section is bounded to its own retrieved chunks + CA context.

Batch temperature is determined by batch size:
  ≤ 5   → 0.75 (medium)
  ≤ 10  → 2 batches: medium (0.75) + hard (0.90)
  ≤ 15  → 2 batches: hard x2 + medium x1
  ≥ 20  → 50% hard (0.90), 25% easy (0.50), 25% medium (0.75)

Structured output uses a Pydantic schema (GeneratedQuestionBatch) so Gemini
returns a validated JSON object with a top-level `questions` array.
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
    global _trap_cache
    if not _trap_cache:
        try:
            with open(trap_registry_path, encoding="utf-8") as f:
                raw = json.load(f)
            # Build flat lookup
            if "traps" in raw:
                for t in raw["traps"]:
                    _trap_cache[t["trap_id"]] = t
            else:
                for subj, val in raw.items():
                    if subj == "_meta":
                        continue
                    if isinstance(val, dict) and "traps" in val:
                        for t in val["traps"]:
                            _trap_cache[t["trap_id"]] = t
        except Exception as e:
            logger.warning(f"[Stage2] Could not load trap registry: {e}")
    return _trap_cache.get(trap_id, {})


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


# ── Difficulty rules ──────────────────────────────────────────────────────────

_DIFFICULTY_RULES = {
    "easy": """
DIFFICULTY: EASY
- One clear correct answer, 3 obviously wrong distractors
- Test direct recall of one fact from the retrieved context
- Avoid qualifiers like 'only', 'always', 'never' — keep statements clean
- Suitable for match_pair or direct_fact type
""",
    "medium": """
DIFFICULTY: MEDIUM
- At least one distractor must be partially true or plausible on first reading
- For multi_statement: 2-3 statements where at least one is subtly wrong
- Use qualifier traps: 'always' vs 'usually', 'only' vs 'primarily'
- Student must reason through each option, not just recall
""",
    "hard": """
DIFFICULTY: HARD
- The trap strategy below MUST be visible in the question
- For multi_statement: exactly one statement should be false, and it must be
  the statement students are MOST LIKELY to believe is true
- For assertion_reason: the Reason must be true but NOT explain the Assertion,
  OR the Assertion must be false for a subtle factual reason
- Distractors must all be real facts — just wrong for this specific question
- A student who has studied but not deeply reasoned will get this wrong
""",
}


# ── Trap injection block ──────────────────────────────────────────────────────

def _trap_injection(trap: dict, question_type: str) -> str:
    if not trap:
        return ""
    name        = trap.get("name", "")
    mechanism   = trap.get("mechanism", "")
    how_to      = trap.get("how_to_generate", "")
    pyq_example = trap.get("real_pyq_example", "")

    return f"""
TRAP STRATEGY TO USE: {name}
  Mechanism (why students get this wrong): {mechanism}
  How to build this trap in your question:
    {how_to}
  Real UPSC example of this trap (use as style reference, not as the question):
    {pyq_example}

Your question MUST use this trap. The false statement or wrong option must
be specifically designed using the mechanism above.
"""


# ── Cross-concept instruction ─────────────────────────────────────────────────

def _cross_concept_instruction(skeleton) -> str:
    """
    If sub_concepts contain borrowed topics (source_concept != ""),
    tell the LLM explicitly how to use them.
    """
    borrowed = [
        sc for sc in skeleton.sub_concepts
        if sc.source_concept and sc.source_concept != skeleton.concept
    ]
    if not borrowed:
        return ""

    lines = "\n".join(
        f'  - "{sc.topic}" (from {sc.source_concept})'
        for sc in borrowed
    )

    linked = getattr(skeleton, "linked_concept", None)
    ar_note = ""
    if linked and skeleton.question_type == "assertion_reason":
        ar_note = (
            f"\nFor this Assertion-Reason question:\n"
            f"  Assertion = fact about {skeleton.concept}\n"
            f"  Reason    = mechanism from {linked} that explains (or SEEMS to explain) the Assertion\n"
            f"  The hard trap: Reason is TRUE but does NOT correctly explain the Assertion."
        )

    return f"""
CROSS-CONCEPT LINKAGE:
The following sub_concepts are borrowed from other concepts.
They MUST appear in the question — not just the explanation.
{lines}
{ar_note}
This cross-concept structure is what makes UPSC hard questions.
"""


# ── Main prompt assembler ─────────────────────────────────────────────────────

def assemble_skeleton_prompt(
    skeleton,
    retrieval_result,
    trap_registry_path: Path,
    pyq_chunks: Optional[List[Dict]] = None,
) -> str:
    """
    Build the per-skeleton generation prompt.

    Args:
        skeleton:            QuestionSkeleton from Stage 0
        retrieval_result:    RetrievalResult from Stage 1
        trap_registry_path:  Path to trap_registry.json
        pyq_chunks:          Optional PYQ style examples (fetched once, shared)

    Returns:
        Complete prompt string for one Gemini Pro call.
    """
    subject  = skeleton.sub_domain
    concept  = skeleton.concept
    qtype    = skeleton.question_type
    diff     = skeleton.difficulty

    # Subject cognitive framework (from old prompting file — unchanged)
    framework = get_cognitive_framework(subject)

    # Retrieved static content
    static_text = _format_chunks(retrieval_result.static_chunks)

    # Trap injection
    trap     = _get_trap(skeleton.trap_strategy, trap_registry_path)
    trap_blk = _trap_injection(trap, qtype)

    # Difficulty rules
    diff_rules = _DIFFICULTY_RULES.get(diff, _DIFFICULTY_RULES["medium"])

    # Cross-concept instruction
    cross_blk = _cross_concept_instruction(skeleton)

    # Sub_concepts list for the prompt
    sc_lines = "\n".join(
        f'  - {sc.topic} [aspect={sc.aspect}'
        + (f', from={sc.source_concept}' if sc.source_concept else '') + ']'
        for sc in skeleton.sub_concepts
    )

    # PYQ style examples — filter to same question type if possible
    pyq_text = ""
    if pyq_chunks:
        relevant = [
            c for c in pyq_chunks
            if qtype.replace("_", "").lower() in
               c.get("metadata", {}).get("pattern_type", "").replace("_", "").lower()
        ] or pyq_chunks[:2]
        pyq_text = "\n---\n".join(
            c.get("content", "")[:300] for c in relevant[:2]
        )

    # CA context block
    ca_block = ""
    if skeleton.ca_flag and retrieval_result.ca_context:
        ca_block = f"""
CURRENT AFFAIRS CONTEXT (use this to ground the question in a real recent event):
{retrieval_result.ca_context[:1500]}

The question MUST link this current event to the static concept.
The current event should appear in the question STEM (not just the explanation).
"""

    # Question type formatting rules (from old prompt — exact same text)
    type_format_rules = """
FORMATTING RULES BY QUESTION TYPE:

For multi_statement: "Consider the following statements regarding [topic]:
1. [Statement 1]
2. [Statement 2]
3. [Statement 3]

Which of the statements given above is/are correct?"
Options: (a) 1 only  (b) 1 and 2 only  (c) 2 and 3 only  (d) 1, 2 and 3

For assertion_reason: "Assertion (A): [Assertion text]
Reason (R): [Reason text]

Which of the following is correct?"
Options: (a) Both A and R are true and R is the correct explanation of A
         (b) Both A and R are true but R is NOT the correct explanation of A
         (c) A is true but R is false
         (d) A is false but R is true

For match_pair: "Match the following:
List I              List II
1. [Item 1]         (a) [Match a]
2. [Item 2]         (b) [Match b]
3. [Item 3]         (c) [Match c]
4. [Item 4]         (d) [Match d]
Select the correct answer using the code given below:"

For direct_fact: Single stem question, 4 options (a)–(d), one correct.
"""

    prompt = f"""You are an expert UPSC Prelims question paper setter.
Generate exactly ONE question. Not a batch. ONE question.

═══════════════════════════════════════════════
QUESTION SPECIFICATION
  concept       : {concept}
  question_type : {qtype}
  difficulty    : {diff}
  sub_concepts to test (MUST appear in the question):
{sc_lines}

═══════════════════════════════════════════════
SUBJECT FRAMEWORK
{framework}

═══════════════════════════════════════════════
{diff_rules}

═══════════════════════════════════════════════
{trap_blk}

═══════════════════════════════════════════════
{cross_blk}

═══════════════════════════════════════════════
STATIC CONTENT (factual grounding — use for statements and distractors):
{static_text}

═══════════════════════════════════════════════
{ca_block}

═══════════════════════════════════════════════
PYQ STYLE REFERENCE (match this tone and structure exactly):
{pyq_text if pyq_text else "Standard UPSC Prelims style — formal, concise, no ambiguity."}

═══════════════════════════════════════════════
{type_format_rules}

═══════════════════════════════════════════════
OUTPUT FORMAT — return ONLY this JSON, nothing else:
{{
  "question":       "Full question text with all statements/options embedded",
  "options":        ["(a) ...", "(b) ...", "(c) ...", "(d) ..."],
  "correct_answer": "A" | "B" | "C" | "D",
  "explanation":    "Justify correct answer. Explain why each wrong option is wrong. Reference the trap mechanism if applicable.",
  "source":         {{"concept": "{concept}", "sub_domain": "{subject}", "trap_used": "{skeleton.trap_strategy}"}}
}}

Do NOT wrap in markdown. Do NOT add extra keys. Start with {{ end with }}.
"""
    return prompt.strip()


# \u2500\u2500 Batch prompt assembler \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def assemble_batch_prompt(
    skeletons:          list,
    retrieval_map:      dict,
    bundle_map:         dict,
    trap_registry_path: Path,
    pyq_chunks:         Optional[List[Dict]] = None,
    subject:            str = "",
) -> str:
    """
    Build a single structured prompt for all N skeletons.

    Shared once (saves tokens):
      - Subject cognitive framework
      - Question-type formatting rules
      - Output schema instructions

    Per-question (bounded to that skeleton only):
      - QUESTION N: header
      - Spec: concept, type, difficulty, sub_concepts
      - Difficulty rules
      - Trap strategy block
      - Cross-concept instruction (if any borrowed sub_concepts)
      - Static chunks from retrieval_map[skeleton_id] only
      - CA context if ca_flag=True
    """
    if not skeletons:
        return ""

    n          = len(skeletons)
    # Use first skeleton's sub_domain as subject if not passed
    subj       = subject or (skeletons[0].sub_domain if skeletons else "")
    framework  = get_cognitive_framework(subj)

    # \u2500 Shared type rules block \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    type_format_rules = """
FORMATTING RULES BY QUESTION TYPE:

For multi_statement: "Consider the following statements regarding [topic]:
1. [Statement 1]
2. [Statement 2]
3. [Statement 3]

Which of the statements given above is/are correct?"
Options: (a) 1 only  (b) 1 and 2 only  (c) 2 and 3 only  (d) 1, 2 and 3

For assertion_reason: "Assertion (A): [Assertion text]
Reason (R): [Reason text]

Which of the following is correct?"
Options: (a) Both A and R are true and R is the correct explanation of A
         (b) Both A and R are true but R is NOT the correct explanation of A
         (c) A is true but R is false
         (d) A is false but R is true

For match_pair: "Match the following:
List I              List II
1. [Item 1]         (a) [Match a]
2. [Item 2]         (b) [Match b]
3. [Item 3]         (c) [Match c]
4. [Item 4]         (d) [Match d]
Select the correct answer using the code given below:"

For direct_fact: Single stem question, 4 options (a)\u2013(d), one correct.
"""

    # \u2500 Per-question blocks \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    question_blocks = []
    for idx, skeleton in enumerate(skeletons, 1):
        concept = skeleton.concept
        qtype   = skeleton.question_type
        diff    = skeleton.difficulty

        # Sub_concepts
        sc_lines = "\n".join(
            f'  - {sc.topic} [aspect={sc.aspect}'
            + (f', from={sc.source_concept}' if sc.source_concept else '') + ']'
            for sc in skeleton.sub_concepts
        )

        # Difficulty rules
        diff_rules = _DIFFICULTY_RULES.get(diff, _DIFFICULTY_RULES["medium"])

        # Trap
        trap     = _get_trap(skeleton.trap_strategy, trap_registry_path)
        trap_blk = _trap_injection(trap, qtype)

        # Cross-concept
        cross_blk = _cross_concept_instruction(skeleton)

        # Static chunks \u2500 BOUNDED to THIS skeleton only
        retrieval_result = retrieval_map.get(skeleton.skeleton_id)
        if retrieval_result:
            static_text = _format_chunks(retrieval_result.static_chunks)
        else:
            static_text = "No static content retrieved. Use your knowledge grounded in NCERT texts."

        # CA context \u2500 BOUNDED to THIS skeleton only
        ca_block = ""
        if skeleton.ca_flag and retrieval_result and retrieval_result.ca_context:
            ca_block = (
                f"\n  CURRENT AFFAIRS CONTEXT (use ONLY for this question, do NOT bleed to others):\n"
                f"{retrieval_result.ca_context[:1200]}\n"
                f"  The question MUST link this event to the static concept.\n"
            )

        # PYQ style for this question type
        pyq_text = ""
        if pyq_chunks:
            relevant = [
                c for c in pyq_chunks
                if qtype.replace("_", "").lower() in
                   c.get("metadata", {}).get("pattern_type", "").replace("_", "").lower()
            ] or pyq_chunks[:1]
            pyq_text = relevant[0].get("content", "")[:250] if relevant else ""
        
        pyq_display = pyq_text if pyq_text else "Standard UPSC Prelims style — formal, concise."

        question_blocks.append(f"""
══════════════════════════════════════════════════
QUESTION {idx}:
  concept       : {concept}
  question_type : {qtype}
  difficulty    : {diff}
  sub_concepts to test (MUST appear in the question):
{sc_lines}
{diff_rules}
{trap_blk}
{cross_blk}
  STATIC CONTENT (use ONLY for question {idx} — do NOT use for other questions):
{static_text}
{ca_block}
  PYQ STYLE REFERENCE: {pyq_display}
""")

    questions_section = "\n".join(question_blocks)

    return f"""You are an expert UPSC Prelims question paper setter.
Generate exactly {n} questions, one per slot below.

CRITICAL RULES:
  1. Context (static chunks, CA context) under each QUESTION N: block applies ONLY to that question.
     Do NOT use context from one question's block when writing another question.
  2. Each question must follow its own difficulty, trap strategy, and sub_concepts exactly.
  3. Use the sub_domain cognitive framework below to ensure conceptually rigorous questions.

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
SUBJECT COGNITIVE FRAMEWORK
{framework}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
{type_format_rules}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
QUESTION SLOTS ({n} questions to generate):
{questions_section}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
OUTPUT FORMAT \u2014 return ONLY this JSON, no markdown:
{{
  "questions": [
    {{
      "question":       "Full question text",
      "options":        ["(a) ...", "(b) ...", "(c) ...", "(d) ..."],
      "correct_answer": "A",
      "explanation":    "Justify correct answer. Explain why each wrong option is wrong.",
      "source":         {{"concept": "<concept name>", "sub_domain": "<subject>", "trap_used": "<trap_id>"}}
    }},
    ... (one entry per QUESTION slot, in order)
  ]
}}

Generate exactly {n} objects in the "questions" array, one per slot in order.
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

    text = text.strip()

    # 1. Try Pydantic full validation (preferred \u2014 structured output from Gemini)
    try:
        batch = GeneratedQuestionBatch.model_validate_json(text)
        results = []
        for i, skeleton in enumerate(skeletons):
            if i < len(batch.questions):
                q = _make_q(batch.questions[i].model_dump(), skeleton)
                results.append(q)
            else:
                results.append(None)
        logger.info(f"[Stage3][Batch] Pydantic parse: {sum(1 for r in results if r)} / {len(skeletons)} OK")
        return results
    except Exception:
        pass

    # 2. Strip markdown fences and retry
    cleaned = _re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        batch = GeneratedQuestionBatch.model_validate_json(cleaned)
        results = []
        for i, skeleton in enumerate(skeletons):
            if i < len(batch.questions):
                q = _make_q(batch.questions[i].model_dump(), skeleton)
                results.append(q)
            else:
                results.append(None)
        logger.info(f"[Stage3][Batch] Cleaned Pydantic parse: {sum(1 for r in results if r)} / {len(skeletons)} OK")
        return results
    except Exception:
        pass

    # 3. Regex fallback: extract individual JSON objects
    logger.warning("[Stage3][Batch] Pydantic parse failed, falling back to regex extraction")
    objects = _re.findall(r'\{[^{}]*"question"[^{}]*\}', cleaned, _re.DOTALL)
    results = []
    for i, skeleton in enumerate(skeletons):
        if i < len(objects):
            try:
                data = json.loads(objects[i])
                results.append(_make_q(data, skeleton))
            except Exception:
                results.append(None)
        else:
            results.append(None)
    ok = sum(1 for r in results if r)
    logger.info(f"[Stage3][Batch] Regex fallback: {ok} / {len(skeletons)} OK")
    return results
