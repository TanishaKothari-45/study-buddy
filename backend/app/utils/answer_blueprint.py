"""
answer_blueprint.py — Stage 0 of the mains answer pipeline.

Calls Gemini Flash with a focused prompt (directive decoder + IBC rules + visual
trigger conditions only) to produce a structured answer plan.  The blueprint is
then used by Stage 1 (targeted retrieval) and Stage 2 (generation) so that:

  - Retrieval queries are dimension-specific rather than the raw question.
  - The generator follows a pre-planned skeleton and doesn't decide structure
    while writing — reducing lost-in-the-middle instruction failures.
  - Visual decisions are locked before generation, not left to chance.

Falls back gracefully: if generate_blueprint() returns None, the caller
(worker.py) degrades to the legacy run_enriched_pipeline path.
"""

import json
import logging
from typing import Optional

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# ── Prompt components ────────────────────────────────────────────────────────
from ..prompts.core.ibc_core_rules import IBC_FORMAT_RULES
from ..prompts.core.directive_decoder import DIRECTIVE_DECODER
from ..prompts.core.visual_trigger_rules import VISUAL_TRIGGER_RULES
from ..prompts.core.blueprint_gs_overlays import get_blueprint_gs_hint, get_blueprint_subject_hint


# ── Output schema ─────────────────────────────────────────────────────────────

class CaDimensionQuery(BaseModel):
    subheading: str   # exact subheading name from the subheadings list
    query: str        # targeted Google Search query for this dimension


class BlueprintOutput(BaseModel):
    directive_intent: str
    subheadings: list[str]
    way_forward_needed: bool
    word_allocation: dict[str, int]
    map_needed: bool
    diagram_type: str          # "flowchart" | "timeline" | "table" | "mindmap" | "pie" | "cycle" | "layered" | "none"
    diagram_placement: str     # e.g. "after Introduction", "end of Dimension 2"
    retrieval_queries: list[str]       # one optimised Pinecone query per subheading (3–5)
    ca_dimension_queries: list[CaDimensionQuery]  # 1–2 targeted CA queries, named by subheading

    @field_validator("diagram_type")
    @classmethod
    def validate_diagram_type(cls, v: str) -> str:
        allowed = {"flowchart", "timeline", "table", "mindmap", "pie", "cycle", "layered", "none"}
        return v if v in allowed else "none"

    @field_validator("diagram_placement")
    @classmethod
    def clear_placement_when_no_diagram(cls, v: str, info) -> str:
        # If diagram_type is none, placement is meaningless — clear it
        diagram_type = (info.data or {}).get("diagram_type", "none")
        if diagram_type == "none":
            return ""
        return v

    @field_validator("subheadings")
    @classmethod
    def at_least_one_subheading(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Blueprint must contain at least one subheading.")
        return v

    @field_validator("retrieval_queries")
    @classmethod
    def at_least_one_query(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Blueprint must contain at least one retrieval query.")
        return v


# ── System prompt ─────────────────────────────────────────────────────────────

BLUEPRINT_SYSTEM_PROMPT = f"""You are a UPSC Mains answer architect. Your ONLY job is to produce a
structural blueprint for an answer — NOT the answer itself.

{IBC_FORMAT_RULES}

{DIRECTIVE_DECODER}

{VISUAL_TRIGGER_RULES}

═══════════════════════ BLUEPRINT OUTPUT RULES ════════════════════════

directive_intent:
  One sentence describing exactly what the directive requires.
  E.g. "Critically assess both achievements and structural gaps, then judge overall effectiveness."

subheadings:
  3–5 body subheadings that together give complete coverage demanded by the directive.
  - "Analyse" → cause/component breakdown.
  - "Evaluate/Critically examine" → positives + negatives + balanced judgement.
  - "Discuss" → multiple balanced dimensions.
  - Do NOT include "Introduction" or "Conclusion" here — those are implied by IBC.
  - Include "Way Forward" as the last subheading only when way_forward_needed is true.

way_forward_needed:
  true ONLY for governance/policy/reform questions or when directive is
  "evaluate", "assess", "suggest measures", or "way forward" is asked explicitly.

word_allocation:
  Distribute the target word count across: "Introduction", each subheading, and "Conclusion".
  If way_forward_needed, include "Way Forward" as a separate key.
  Values MUST sum to approximately the target word count.
  Introduction ≈ 40–60 words. Conclusion ≈ 40–60 words. Body sections share the remainder evenly.

map_needed / diagram_type / diagram_placement:
  Apply VISUAL TRIGGER RULES above strictly.
  map_needed and diagram_type are independent — a map can be needed with diagram_type: "none".
  diagram_placement: where to place the Mermaid diagram ONLY.
    - Set to "" (empty string) when diagram_type is "none".
    - When diagram_type is set, be specific: "after Introduction" or "end of [exact subheading name]".
  map placement is always after Introduction — do not use diagram_placement for maps.

retrieval_queries:
  One query per subheading (3–5 total).
  Write as 5–10 word knowledge-base search phrases in UPSC academic language.
  NOT exam question language — write the knowledge that needs to be retrieved.
  Example: "India monsoon mechanism Western Ghats orographic rainfall" (not "explain Indian monsoon").

ca_dimension_queries:
  Array of up to 4 objects, each with:
    "subheading": one of — "Introduction", an exact body subheading name, or "Conclusion"
    "query": a targeted Google Search query for that specific section (recent news/journalistic language)

  Allocate as follows:
    "Introduction" (ALWAYS include): latest triggering event or recent news hook for this topic.
      The generator will use it as the opening contextual hook sentence.
      Query: most recent high-profile event/development related to the question topic.

    1–2 body subheadings: the subheadings most likely to benefit from recent data
      (policy, governance, reform, statistics). Use exact subheading name.

    "Conclusion" (include when way_forward_needed or topic has active policy debate):
      forward-looking CA fact for the synthesis/recommendation sentence.
      Query: recent policy direction, international commitment, or reform signal.

  Write all queries in news/journalistic language — no year hardcoding (the search tool applies recency).
  Example:
    [{{"subheading": "Introduction", "query": "oil price volatility geopolitical impact global economy"}},
     {{"subheading": "OPEC and Supply Dynamics", "query": "OPEC production cuts oil market 2025 geopolitics"}},
     {{"subheading": "Conclusion", "query": "energy transition fossil fuel dependency global south reform"}}]

Return ONLY valid JSON matching the schema. No explanation, no markdown wrapper, no code fences.
"""


# ── Main function ─────────────────────────────────────────────────────────────

async def generate_blueprint(
    question: str,
    word_count: int,
    gs_paper: str,
    subject: str,
    gemini_client,
    corpus_snapshot: str = "",
) -> Optional[BlueprintOutput]:
    """
    Stage 0: Generate an answer blueprint using Gemini Flash.

    corpus_snapshot: top surface chunks from a generic k=8 retrieval.
    Used only so blueprint can write corpus-aware retrieval queries.
    NOT passed to the generator — dimensions are never limited by corpus coverage.

    Returns a BlueprintOutput or None on any failure.  Callers must handle
    None and degrade to the legacy pipeline.
    """
    gs_hint = get_blueprint_gs_hint(gs_paper or "")
    subject_hint = get_blueprint_subject_hint(subject or "")

    overlay_lines = ""
    if gs_hint:
        overlay_lines += f"Paper context: {gs_hint}\n"
    if subject_hint:
        overlay_lines += f"Subject context: {subject_hint}\n"

    corpus_block = ""
    if corpus_snapshot:
        corpus_block = (
            "\nCORPUS SNAPSHOT (what the knowledge base contains on this topic):\n"
            "Use this to write more targeted retrieval_queries and ca_dimension_queries.\n"
            "Do NOT limit subheadings to only what appears here — all required dimensions\n"
            "must be planned regardless of corpus coverage.\n"
            "---\n"
            f"{corpus_snapshot}\n"
            "---\n"
        )

    user_prompt = (
        f"Question: {question}\n"
        f"Target word count: {word_count}\n"
        f"GS Paper: {gs_paper or 'Not specified'}\n"
        f"Subject: {subject or 'Not specified'}\n"
        f"{overlay_lines}"
        f"{corpus_block}\n"
        "Produce the blueprint JSON now."
    )

    try:
        raw = await gemini_client.generate_response(
            user_prompt=user_prompt,
            system_prompt=BLUEPRINT_SYSTEM_PROMPT,
            temperature=0.1,
            max_retries=1,
        )
        return _parse_blueprint(raw, word_count)
    except Exception as exc:
        logger.warning(f"Blueprint generation failed: {exc}. Falling back to legacy pipeline.")
        return None


def _parse_blueprint(raw: str, word_count: int) -> Optional[BlueprintOutput]:
    """Parse and validate raw JSON string → BlueprintOutput.  Returns None on failure."""
    try:
        # Strip accidental code fences from the model
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        bp = BlueprintOutput(**data)

        # Sanity check: word allocation should roughly match target
        total = sum(bp.word_allocation.values())
        if total < word_count * 0.5 or total > word_count * 2.0:
            logger.warning(
                f"Blueprint word allocation total ({total}) is far from target ({word_count}). "
                "Using blueprint anyway."
            )

        logger.info(
            f"✅ Blueprint parsed: {len(bp.subheadings)} subheadings, "
            f"diagram={bp.diagram_type}, map={bp.map_needed}"
        )
        return bp

    except Exception as exc:
        logger.warning(f"Blueprint parse failed: {exc}. Raw response: {raw[:300]}")
        return None
