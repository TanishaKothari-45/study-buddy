"""
Stage 2 — Per-Skeleton Question Generation

One LLM call per skeleton. Prompt = skeleton intent + trap injection + retrieved chunks.

What's kept from the old mock_test_prompting.py:
  - Subject-specific cognitive frameworks (FRAMEWORK_GEOGRAPHY etc.) — unchanged
  - Per-type formatting rules (multi_statement, A/R, match_pair) — unchanged
  - JSON output format and factual_units pattern — unchanged

What's new / different:
  - Prompt is built for ONE question (not a batch of 10)
  - Skeleton fields drive the prompt: concept, sub_concepts, type, difficulty
  - Trap injection: how_to_generate + mechanism from trap_registry
  - Cross-concept linkage instruction when linked_concept is set
  - ca_context injected only when ca_flag=True (not "40% of questions must link CA")
  - Difficulty-specific distractor rules from trap difficulty level
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

# Re-use subject framework strings from old prompting file
# Import them directly — don't duplicate
from app.utils.mock_test_prompting import (
    get_system_prompt,
    get_cognitive_framework,
)


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
