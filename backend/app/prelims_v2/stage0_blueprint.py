"""
Stage 0 — Blueprint Generation (v3)

Key fixes over v2:
  1. Trap-concept affinity enforced — LLM only sees traps valid for each concept
  2. ca_event is populated from concept's ca_trigger_types, not left blank
  3. Difficulty math fixed — uses cfg.difficulty ratios properly, sums exactly to num_questions
  4. _trap_summary bug fixed — iterated correctly, not overwritten each loop
  5. Prompt restructured — CONCEPT → VALID TRAPS FOR THAT CONCEPT (not a global list)
  6. Inter-concept linkage fed to LLM so it can make hard A/R questions that span two concepts
  7. BlueprintQuestion model shown explicitly — sub_concepts typed as list of SubConceptItem
"""
from __future__ import annotations

import json
import logging
import math
import random
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
from .models import QuestionSkeleton, SubConceptItem as SubConceptItem

logger = logging.getLogger(__name__)

_V2_DIR    = Path(__file__).parent
_CONFIG_DIR = _V2_DIR.parent.parent.parent / "config"


# SubConceptItem and QuestionSkeleton are imported from .models
# (so stage0 output is the SAME class that stage2/stage3 expect)


class BlueprintQuestion(BaseModel):
    id:           str
    question_type: str   # multi_statement|match_pair|assertion_reason|direct_fact|spatial|chronology|data_based
    concept:      str
    sub_concepts: List[SubConceptItem]
    difficulty:   str    # easy | medium | hard
    ca_linked:    bool
    ca_event:     str    # populated from concept's ca_trigger_types when ca_linked=true
    trap_id:      str    # MUST match a trap_id from that concept's trap_affinity list
    linked_concept: Optional[str] = None   # second concept for A/R cross-concept questions


class BlueprintOutput(BaseModel):
    questions: List[BlueprintQuestion]


# ── SubjectConfig stub (replace with your real import) ────────────────────────

class DifficultyConfig(BaseModel):
    easy:   float = 0.25
    medium: float = 0.50
    hard:   float = 0.25


class QuestionTypeRange(BaseModel):
    min: int
    max: int


class SubjectConfig(BaseModel):
    subject:              str
    trap_file:            str
    pyq_file:             str
    ca_linkage_rate:      float
    difficulty:           DifficultyConfig
    question_type_ranges: dict   # qt_slug -> QuestionTypeRange


def get_subject_config(subject: str) -> SubjectConfig:
    """Replace this stub with your real subject config loader."""
    defaults = {
        "Geography": SubjectConfig(
            subject="Geography",
            trap_file="traps_geography.json",
            pyq_file="geography_prelims_pyq_patterns.json",
            ca_linkage_rate=0.30,
            difficulty=DifficultyConfig(easy=0.25, medium=0.50, hard=0.25),
            question_type_ranges={
                "multi_statement":  {"min": 3, "max": 6},
                "match_pair":       {"min": 1, "max": 3},
                "assertion_reason": {"min": 1, "max": 3},
                "direct_fact":      {"min": 1, "max": 3},
                "spatial":          {"min": 0, "max": 2},
            },
        ),
        "Polity": SubjectConfig(
            subject="Polity",
            trap_file="traps_polity.json",
            pyq_file="polity_prelims_pyq_patterns.json",
            ca_linkage_rate=0.40,
            difficulty=DifficultyConfig(easy=0.20, medium=0.55, hard=0.25),
            question_type_ranges={
                "multi_statement":  {"min": 4, "max": 7},
                "assertion_reason": {"min": 1, "max": 3},
                "direct_fact":      {"min": 2, "max": 4},
                "match_pair":       {"min": 0, "max": 2},
            },
        ),
    }
    return defaults.get(subject, defaults["Geography"])


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_json(path: Path, label: str) -> dict | list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"[Stage0] {label} not found: {path}")
        return {}
    except Exception as e:
        logger.warning(f"[Stage0] Failed to load {label}: {e}")
        return {}


def _load_trap_registry(cfg: SubjectConfig) -> dict:
    return _load_json(_V2_DIR / cfg.trap_file, "trap registry")


def _load_pyq_patterns(cfg: SubjectConfig) -> dict:
    return _load_json(_CONFIG_DIR / cfg.pyq_file, "PYQ patterns")


def _load_concept_pool(subject: str, subdomain: str) -> list:
    subj_slug = subject.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    sub_slug  = subdomain.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    candidate = _V2_DIR / "concept_pools" / f"{subj_slug}_{sub_slug}.json"
    data = _load_json(candidate, "concept pool")
    if data:
        return data.get("concepts", [])
    fallback = _V2_DIR / "concept_pools" / f"{subj_slug}.json"
    data = _load_json(fallback, "concept pool fallback")
    return data.get("concepts", []) if data else []


# ── Difficulty distribution (FIXED) ──────────────────────────────────────────

def _difficulty_counts(cfg: SubjectConfig, num_questions: int) -> tuple[int, int, int]:
    """
    Distribute num_questions into easy/medium/hard using cfg ratios.
    Guarantees they sum to exactly num_questions.
    Remainder goes to medium.
    """
    easy   = math.floor(cfg.difficulty.easy   * num_questions)
    hard   = math.floor(cfg.difficulty.hard   * num_questions)
    medium = num_questions - easy - hard
    # Ensure at least 1 of each if num_questions >= 3
    if num_questions >= 3:
        easy   = max(1, easy)
        hard   = max(1, hard)
        medium = num_questions - easy - hard
    return easy, medium, hard


# ── Trap lookup (FIXED — was overwriting on every loop iteration) ─────────────

def _get_all_traps(trap_registry: dict) -> dict:
    """
    Return flat dict: trap_id -> trap_dict.
    Works for both formats:
      - {subject: {traps: [...]}}   (your current multi-subject file)
      - {traps: [...]}              (single-subject file)
    """
    flat = {}
    if "traps" in trap_registry:
        # Single subject file
        for t in trap_registry["traps"]:
            flat[t["trap_id"]] = t
    else:
        # Multi-subject file keyed by subject name
        for key, val in trap_registry.items():
            if key == "_meta":
                continue
            if isinstance(val, dict) and "traps" in val:
                for t in val["traps"]:
                    flat[t["trap_id"]] = t
    return flat


def _traps_for_concept(concept: dict, all_traps: dict) -> list:
    """
    Return only the traps that are in this concept's trap_affinity list.
    Falls back to all traps if trap_affinity is missing or empty.
    """
    affinity = concept.get("trap_affinity", [])
    if not affinity:
        return list(all_traps.values())
    return [all_traps[tid] for tid in affinity if tid in all_traps]


# ── Prompt builder ────────────────────────────────────────────────────────────

def _concept_block(concept: dict, all_traps: dict, all_concepts: dict) -> str:
    """
    Build a single concept block for the prompt.
    Shows this concept's own sub_concepts AND sub_concepts from every other
    concept in the pool (for cross-concept borrowing).
    """
    name        = concept["concept"]
    links       = concept.get("links_to", [])
    ca_types    = concept.get("ca_trigger_types", [])
    sub_cs      = concept.get("sub_concepts", [])
    valid_traps = _traps_for_concept(concept, all_traps)

    scs_lines = "\n".join(
        f'      - "{sc["topic"]}" [aspect={sc["aspect"]}, ca_connectable={sc["ca_connectable"]}]'
        for sc in sub_cs
    )

    # Show sub_concepts of every OTHER concept inline so LLM can freely borrow
    linked_scs_lines = ""
    for linked_name, linked in all_concepts.items():
        if linked_name == name:   # skip itself
            continue
        linked_scs = linked.get("sub_concepts", [])
        if not linked_scs:
            continue
        lines = "\n".join(
            f'        - "{sc["topic"]}" [aspect={sc["aspect"]}]'
            for sc in linked_scs
        )
        linked_scs_lines += f'\n    FROM "{linked_name}" (set source_concept="{linked_name}"):\n{lines}'

    trap_lines = "\n".join(
        f'      - {t["trap_id"]}: {t["name"]} — {t["description"][:100]}'
        for t in valid_traps
    )

    ca_lines   = "\n".join(f'      - {ct}' for ct in ca_types)
    link_str   = ", ".join(links) if links else "none"

    return f"""  CONCEPT: {name}
    own sub_concepts (copy topic verbatim, set source_concept to ""):
{scs_lines}
    borrowable sub_concepts from other concepts (copy topic verbatim, set source_concept to that concept name):{linked_scs_lines}
    VALID trap_ids for this concept ONLY:
{trap_lines}
    links_to: {link_str}
    ca_trigger_types:
{ca_lines}
"""


def _type_ranges_str(cfg: SubjectConfig, scale: float) -> str:
    lines = []
    for qt, rng in cfg.question_type_ranges.items():
        if isinstance(rng, dict):
            lo, hi = rng["min"], rng["max"]
        else:
            lo, hi = rng.min, rng.max
        lines.append(f'    {qt}: [{max(0, round(lo*scale))}, {round(hi*scale)}]')
    return "\n".join(lines)


def _build_prompt(
    cfg: SubjectConfig,
    domain: str,
    subdomain: str,
    num_questions: int,
    concept_pool: list,
    trap_registry: dict,
    pyq_data: dict,
) -> str:
    easy, medium, hard = _difficulty_counts(cfg, num_questions)
    ca_count = max(1, round(num_questions * cfg.ca_linkage_rate))
    scale    = num_questions / 10   # type range baseline is per-10

    all_traps = _get_all_traps(trap_registry)

    # Build lookup once — passed into every _concept_block call
    all_concepts_lookup = {c["concept"]: c for c in concept_pool}

    concept_blocks = "\n".join(
        _concept_block(c, all_traps, all_concepts_lookup)
        for c in concept_pool
    )

    type_ranges = _type_ranges_str(cfg, scale)

    return f"""You are an expert UPSC Prelims question paper setter.
Your task is to DESIGN a blueprint — NOT generate actual questions.

═══════════════════════════════════════════════
SUBJECT CONTEXT
  subject  : {cfg.subject}
  domain   : {domain}
  subdomain: {subdomain}

═══════════════════════════════════════════════
CONCEPT POOL WITH VALID TRAPS
Each concept lists:
  - sub_concepts you must pick from (verbatim)
  - VALID trap_ids for THAT concept only — do not use trap_ids from other concepts
  - links_to other concepts (for hard assertion_reason questions)
  - ca_trigger_types (use to fill ca_event for ca_linked questions)

{concept_blocks}

═══════════════════════════════════════════════
CONSTRAINTS
  num_questions     : {num_questions}
  difficulty        : easy={easy}, medium={medium}, hard={hard}  [must sum to {num_questions}]
  ca_linked count   : exactly {ca_count} questions must have ca_linked=true
  question_type_ranges (min, max):
{type_ranges}

═══════════════════════════════════════════════
RULES — FOLLOW STRICTLY

1. TRAP MATCHING (most important rule)
   Each question's trap_id MUST come from that concept's "VALID trap_ids" list above.
   NEVER use a trap_id from a different concept's valid list.
   If a concept only has GEO_T04 available, use GEO_T04 — do not substitute.

2. CA_EVENT POPULATION
   For every question where ca_linked=true, ca_event MUST be filled with a specific
   recent event string from that concept's ca_trigger_types list.
   Example: "IMD announced below-normal 2024 SW monsoon due to El Nino conditions"
   ca_event must NEVER be empty when ca_linked=true.

3. SUB_CONCEPTS
   Pick 2-3 sub_concepts per question.
   topic text MUST be copied verbatim from whichever sub_concept list you pick from.

   You are FREE to mix sub_concepts from the question's own concept AND from any
   other concept shown — for any question type, any difficulty level.
   There is no minimum or maximum on how many you borrow.

   When you borrow a sub_concept from another concept:
     - Copy the topic text verbatim from that concept's borrowable list
     - Set source_concept to that concept's exact name (e.g. "Jet Streams")

   When sub_concept comes from the question's own concept:
     - Set source_concept to "" (empty string)

   Cross-concept borrowing creates hard UPSC questions.
   Example: concept=Monsoon, borrow "Seasonal northward migration of subtropical jet"
   from Jet Streams → source_concept="Jet Streams"
   This tests whether students know the jet stream drives monsoon onset.

4. CONCEPT COVERAGE
   Cover at least {min(5, len(concept_pool))} different concepts across all {num_questions} questions.
   No concept in more than 3 questions.

5. TRAP DIVERSITY
   No trap_id used more than 2 times total.
   No same trap_id in consecutive questions.

6. DIFFICULTY
   Follow exactly: easy={easy}, medium={medium}, hard={hard}.
   Hard questions MUST use assertion_reason or multi_statement type.
   Easy questions SHOULD use direct_fact or match_pair type.

7. LINKED_CONCEPT
   For assertion_reason type questions, set linked_concept to the second concept
   being tested (from links_to). Leave null for all other types.

═══════════════════════════════════════════════
OUTPUT FORMAT

Return a JSON object:
{{
  "questions": [
    {{
      "id": "Q1",
      "question_type": "multi_statement",
      "concept": "<exact concept name from pool>",
      "sub_concepts": [
        {{"topic": "<verbatim from own sub_concepts>",          "aspect": "<mechanism|process|comparison|impact|application>", "source_concept": ""}},
        {{"topic": "<verbatim from another concept's sub_concepts>", "aspect": "<...>",                                            "source_concept": "<that concept's name>"}}
      ],
      "difficulty": "medium",
      "ca_linked": false,
      "ca_event": "",
      "trap_id": "<trap_id from that concept's valid list only>",
      "linked_concept": null
    }},
    ...
  ]
}}

Generate exactly {num_questions} questions. No explanations. No markdown. Pure JSON only.
"""



def _rule_based_fallback(
    num_questions: int,
    concept_pool:  list,
    trap_registry: dict,
    cfg:           SubjectConfig,
) -> List[QuestionSkeleton]:
    logger.info(f"[Stage0] Rule-based fallback for {num_questions} skeletons")
    all_traps = _get_all_traps(trap_registry)
    concepts  = concept_pool if concept_pool else [{"concept": cfg.subject, "sub_concepts": [], "trap_affinity": []}]
    types_pool = list(cfg.question_type_ranges.keys())

    easy, medium, hard = _difficulty_counts(cfg, num_questions)
    difficulties = ["easy"]*easy + ["medium"]*medium + ["hard"]*hard
    random.shuffle(difficulties)

    ca_count  = max(1, round(num_questions * cfg.ca_linkage_rate))
    ca_indices = set(random.sample(range(num_questions), min(ca_count, num_questions)))

    skeletons = []
    trap_use  = {}

    for i in range(num_questions):
        c = concepts[i % len(concepts)]
        valid_traps = _traps_for_concept(c, all_traps)
        # Pick least-used trap
        valid_traps_sorted = sorted(valid_traps, key=lambda t: trap_use.get(t["trap_id"], 0))
        trap = valid_traps_sorted[0] if valid_traps_sorted else {}
        if trap:
            trap_use[trap["trap_id"]] = trap_use.get(trap["trap_id"], 0) + 1

        sub_cs = [
            SubConceptItem(topic=sc["topic"], aspect=sc.get("aspect", "process"))
            for sc in c.get("sub_concepts", [])[:2]
        ]

        ca_flag  = i in ca_indices
        ca_event = ""
        if ca_flag and c.get("ca_trigger_types"):
            ca_event = c["ca_trigger_types"][i % len(c["ca_trigger_types"])]

        skeletons.append(QuestionSkeleton(
            skeleton_id    = f"sk_{i+1:03d}",
            question_type  = types_pool[i % len(types_pool)],
            concept        = c["concept"],
            sub_concepts   = sub_cs,
            difficulty     = difficulties[i],
            ca_flag        = ca_flag,
            ca_event       = ca_event,
            trap_strategy  = trap.get("trap_id", ""),
            trap_name      = trap.get("name", ""),
            sub_domain     = cfg.subject,
        ))
    return skeletons


# ── Blueprint → Skeleton conversion ──────────────────────────────────────────

def _to_skeleton(bq: BlueprintQuestion, idx: int, cfg: SubjectConfig) -> QuestionSkeleton:
    return QuestionSkeleton(
        skeleton_id    = f"sk_{idx:03d}",
        question_type  = bq.question_type,
        concept        = bq.concept,
        sub_concepts   = bq.sub_concepts,
        difficulty     = bq.difficulty,
        ca_flag        = bq.ca_linked,
        ca_event       = bq.ca_event,
        trap_strategy  = bq.trap_id,
        trap_name      = "",
        sub_domain     = cfg.subject,
        linked_concept = bq.linked_concept,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_blueprint(
    num_questions: int,
    topics:        List[str],
    subject:       str,
    gemini_client,
    domain:        str = "",
    subdomain:     str = "",
) -> List[QuestionSkeleton]:
    """
    Stage 0: generate a structured question blueprint before any retrieval.
    Uses Gemini Flash with response_schema=BlueprintOutput.
    Falls back to rule-based generation if Flash call fails.
    """
    cfg       = get_subject_config(subject)
    domain    = domain    or cfg.subject
    subdomain = subdomain or (topics[0] if topics else cfg.subject)

    logger.info(f"[Stage0] Blueprint: {num_questions}Q | {cfg.subject} > {domain} > {subdomain}")

    trap_registry = _load_trap_registry(cfg)
    pyq_data      = _load_pyq_patterns(cfg)
    concept_pool  = _load_concept_pool(cfg.subject, subdomain)

    # Fallback concept pool from trap sub_domains if concept pool missing
    if not concept_pool:
        logger.warning(f"[Stage0] No concept pool for {cfg.subject}/{subdomain} — using trap sub_domains")
        seen = set()
        all_traps = _get_all_traps(trap_registry)
        for t in all_traps.values():
            for sd in t.get("sub_domains", []):
                if sd not in seen:
                    concept_pool.append({
                        "concept": sd,
                        "sub_concepts": [],
                        "trap_affinity": [t["trap_id"]],
                        "links_to": [],
                        "ca_trigger_types": []
                    })
                    seen.add(sd)

    prompt = _build_prompt(
        cfg=cfg,
        domain=domain,
        subdomain=subdomain,
        num_questions=num_questions,
        concept_pool=concept_pool,
        trap_registry=trap_registry,
        pyq_data=pyq_data,
    )

    from .gemini_utils import make_flash_client
    flash_client = make_flash_client(gemini_client)

    try:
        response_text = await flash_client.generate_response(
            user_prompt=prompt,
            system_prompt=(
                "You are an expert UPSC Prelims question paper setter. "
                "Output ONLY valid JSON. No markdown. No explanation."
            ),
            response_schema=BlueprintOutput,
            temperature=0.7,
            use_google_search=False,
        )

        output    = BlueprintOutput.model_validate_json(response_text)
        skeletons = [
            _to_skeleton(bq, i + 1, cfg)
            for i, bq in enumerate(output.questions[:num_questions])
        ]
        logger.info(f"[Stage0] Flash success: {len(skeletons)}/{num_questions} skeletons")

        # Validate: warn if ca_event is empty on ca_linked questions
        empty_ca = [s.skeleton_id for s in skeletons if s.ca_flag and not s.ca_event]
        if empty_ca:
            logger.warning(f"[Stage0] ca_event empty on ca_linked skeletons: {empty_ca}")

        return skeletons

    except Exception as e:
        logger.error(f"[Stage0] Flash failed: {e} — using fallback")
        return _rule_based_fallback(num_questions, concept_pool, trap_registry, cfg)