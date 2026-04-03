"""
Stage 0 — Blueprint Generation (v4)

v4 changes (pre-sampled slots):
  1. Python pre-samples concept + sub_concepts + trap + linked sub_concept per slot
  2. LLM only decides question_type, ca_event, and optional sub_concept swap
  3. Diversity driven by Python randomness, not LLM laziness
  4. Linking probability varies by difficulty: easy=0%, medium=40%, hard=80%
  5. New concept pool format supported: dict-keyed concepts normalised to list

v3 changes (retained):
  1. Trap-concept affinity enforced
  2. ca_event populated from concept's ca_trigger_types
  3. Difficulty math guarantees exact sum
  4. Prompt now shorter and more focused
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

# Probability of injecting a linked (borrowed) sub_concept per difficulty tier
_LINKING_PROB_BY_DIFFICULTY: dict = {"easy": 0.0, "medium": 0.4, "hard": 0.8}

# Weight multipliers for priority-based concept selection
_PRIORITY_WEIGHT: dict = {"high": 3, "medium": 2, "low": 1}


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


# ── Slot completion models (v4 — LLM only fills these fields) ─────────────────

class SlotCompletion(BaseModel):
    """What the LLM fills in for each pre-sampled slot."""
    id:               str
    question_type:    str              # chosen question type
    ca_event:         str  = ""        # required when ca_linked=true
    linked_concept:   Optional[str] = None   # for assertion_reason questions
    swap_sub_concept: Optional[dict] = None  # {index, new_topic, new_aspect, new_source_concept}


class SlotCompletionOutput(BaseModel):
    completions: List[SlotCompletion]


# ── SubjectConfig stub (replace with your real import) ────────────────────────

class DifficultyConfig(BaseModel):
    easy:   float = 0.15    # 15% easy
    medium: float = 0.25    # 25% medium
    hard:   float = 0.40    # 40% hard
    pure_ca: float = 0.15   # 15% pure current affairs (dedicated)


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
            difficulty=DifficultyConfig(easy=0.15, medium=0.25, hard=0.40, pure_ca=0.15),
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
            ca_linkage_rate=0.30,
            difficulty=DifficultyConfig(easy=0.15, medium=0.25, hard=0.40, pure_ca=0.15),
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


def _normalise_concept_dict(concepts_dict: dict) -> list:
    """
    Convert new dict-keyed concept pool format to the flat list format the pipeline uses.

    New format  — concepts is a dict:
        {"Monsoon": {"priority": "high", "sub_concepts": [...], "links_to": [...], ...}}

    Normalised — concepts is a list:
        [{"concept": "Monsoon", "priority": "high", "sub_concepts": [...], ...}]

    Also normalises sub_concept fields: `aspects` (array) → first element becomes
    `aspect` (string) so existing pipeline code that reads sc["aspect"] keeps working.
    """
    result = []
    for name, entry in concepts_dict.items():
        raw_scs = entry.get("sub_concepts", [])
        norm_scs = []
        for sc in raw_scs:
            # Support both "aspects" (new array) and "aspect" (old string)
            aspects = sc.get("aspects") or []
            if isinstance(aspects, str):
                aspects = [aspects]
            if not aspects and sc.get("aspect"):
                aspects = [sc["aspect"]]
            if not aspects:
                aspects = ["process"]

            norm_scs.append({
                "topic":          sc["topic"],
                "aspect":         aspects[0],   # singular — existing code reads this
                "aspects":        aspects,       # full list — _pre_sample_slots reads this
                "ca_connectable": sc.get("ca_connectable", False),
                "linked_to":      sc.get("linked_to", []),
            })

        result.append({
            "concept":          name,
            "priority":         entry.get("priority", "medium"),
            "sub_concepts":     norm_scs,
            "links_to":         entry.get("links_to", []),
            "trap_affinity":    entry.get("trap_affinity", []),
            "ca_trigger_types": entry.get("ca_trigger_types", []),
        })
    return result


def _load_concept_pool(subject: str, subdomain: str) -> list:
    subj_slug = subject.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    sub_slug  = subdomain.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    candidate = _V2_DIR / "concept_pools" / f"{subj_slug}_{sub_slug}.json"
    data = _load_json(candidate, "concept pool")
    if data:
        raw = data.get("concepts", [])
        return _normalise_concept_dict(raw) if isinstance(raw, dict) else raw
    fallback = _V2_DIR / "concept_pools" / f"{subj_slug}.json"
    data = _load_json(fallback, "concept pool fallback")
    if not data:
        return []
    raw = data.get("concepts", [])
    return _normalise_concept_dict(raw) if isinstance(raw, dict) else raw


# ── Difficulty distribution (FIXED) ──────────────────────────────────────────

def _difficulty_counts(cfg: SubjectConfig, num_questions: int) -> tuple[int, int, int, int]:
    """
    Distribute num_questions into easy/medium/hard/pure_ca using cfg ratios.
    Guarantees they sum to exactly num_questions.
    Remainder goes to medium.

    Distribution (Option A):
      - easy: 15%
      - medium: 25%
      - hard: 40%
      - pure_ca: 15% (dedicated pure CA questions)
    """
    pure_ca = math.floor(cfg.difficulty.pure_ca * num_questions)
    easy   = math.floor(cfg.difficulty.easy   * num_questions)
    hard   = math.floor(cfg.difficulty.hard   * num_questions)
    medium = num_questions - easy - hard - pure_ca

    # Ensure at least 1 of each if num_questions >= 4
    if num_questions >= 4:
        pure_ca = max(1, pure_ca)
        easy   = max(1, easy)
        hard   = max(1, hard)
        medium = num_questions - easy - hard - pure_ca

    return easy, medium, hard, pure_ca


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


# ── Pre-sample slots ──────────────────────────────────────────────────────────

def _pre_sample_slots(
    cfg:          SubjectConfig,
    num_questions: int,
    concept_pool:  list,
    trap_registry: dict,
    ledger:        Optional[dict] = None,
) -> list:
    """
    Randomly sample question ingredients before the LLM call.

    Returns a list of slot dicts (one per question):
        concept       — concept name
        sub_concepts  — List[SubConceptItem] (2 own + 0-1 linked)
        trap_id       — selected trap id
        trap_name     — human-readable trap name
        difficulty    — easy | medium | hard
        ca_linked     — bool
        ca_event      — "" (LLM fills this later)
        ca_triggers   — list of ca_trigger_type strings (for prompt context)
    """
    all_traps      = _get_all_traps(trap_registry)
    concept_lookup = {c["concept"]: c for c in concept_pool}

    # ── 1. Difficulty distribution ────────────────────────────────────────────
    easy, medium, hard, pure_ca = _difficulty_counts(cfg, num_questions)
    difficulties = ["easy"] * easy + ["medium"] * medium + ["hard"] * hard + ["pure_ca"] * pure_ca
    random.shuffle(difficulties)

    # ── 2. CA slot assignment ─────────────────────────────────────────────────
    # Pure CA questions automatically get ca_flag=True (no additional ca_linkage rate)
    # For non-pure-CA questions, apply ca_linkage_rate
    non_pure_ca_indices = [i for i, d in enumerate(difficulties) if d != "pure_ca"]
    ca_linkage_count = max(1, round(len(non_pure_ca_indices) * cfg.ca_linkage_rate))
    ca_linked_indices = set(random.sample(non_pure_ca_indices, min(ca_linkage_count, len(non_pure_ca_indices))))

    # Combine: pure_ca gets ca_flag=True, plus ca_linked get ca_flag=True
    pure_ca_indices = set(i for i, d in enumerate(difficulties) if d == "pure_ca")
    ca_indices = pure_ca_indices | ca_linked_indices

    # ── 3. Ledger awareness ───────────────────────────────────────────────────
    heavy_seen: set = set()
    traps_exhausted_set: set = set()
    if ledger:
        heavy_seen = {
            name for name, entry in ledger.get("concepts_seen", {}).items()
            if isinstance(entry, dict) and entry.get("count", 0) >= 2
        }
        traps_exhausted_set = set(ledger.get("traps_exhausted", []))

    # ── 4. Priority-weighted, ledger-biased concept pool ─────────────────────
    weighted_pool: list = []
    for c in concept_pool:
        name   = c["concept"]
        weight = _PRIORITY_WEIGHT.get(c.get("priority", "medium"), 2)
        if name in heavy_seen:
            weight = max(1, weight - 1)   # downweight but never exclude
        weighted_pool.extend([name] * weight)
    random.shuffle(weighted_pool)

    # ── 5. Assign concepts (min coverage + max-3 cap) ────────────────────────
    unique_needed  = min(5, len(concept_pool))
    concept_counts: dict = {}
    concepts_assigned: list = []
    unique_seen: set = set()

    # Cycle the weighted pool enough times to fill all slots
    supply = (weighted_pool * max(3, num_questions)) if weighted_pool else [
        c["concept"] for c in concept_pool
    ]
    supply_iter = iter(supply)

    for _ in range(num_questions):
        chosen = None
        # Try to pick an unseen concept first (until coverage is met)
        want_fresh = len(unique_seen) < unique_needed
        for name in supply_iter:
            if concept_counts.get(name, 0) >= 3:
                continue
            if want_fresh and name in unique_seen:
                # Skip already-seen until we've covered unique_needed — but only
                # if there are still fresh options available
                fresh_remaining = [
                    n for n in weighted_pool
                    if n not in unique_seen and concept_counts.get(n, 0) < 3
                ]
                if fresh_remaining:
                    continue
            chosen = name
            break

        if chosen is None:
            # Fallback: any concept under cap
            for c in concept_pool:
                if concept_counts.get(c["concept"], 0) < 3:
                    chosen = c["concept"]
                    break
            if chosen is None:
                chosen = concept_pool[len(concepts_assigned) % len(concept_pool)]["concept"]

        concepts_assigned.append(chosen)
        concept_counts[chosen] = concept_counts.get(chosen, 0) + 1
        unique_seen.add(chosen)

    # ── 6. Build each slot ────────────────────────────────────────────────────
    slots: list = []
    trap_use: dict = {}

    for i in range(num_questions):
        concept_name = concepts_assigned[i]
        concept      = concept_lookup.get(concept_name, concept_pool[0])
        difficulty   = difficulties[i]
        ca_linked    = i in ca_indices

        # 6a. Own sub_concepts — pick 2 at random
        own_scs = concept.get("sub_concepts", [])
        sampled_own = random.sample(own_scs, k=min(2, len(own_scs))) if own_scs else []

        # 6b. Linked sub_concept injection (difficulty-based probability)
        link_prob  = _LINKING_PROB_BY_DIFFICULTY.get(difficulty, 0.4)
        linked_sc: Optional[dict] = None
        if random.random() < link_prob:
            # Build candidate linked concepts: prefer sub_concept-level linked_to
            # (more coherent), fall back to concept-level links_to
            candidate_names: list = []
            for sc in sampled_own:
                candidate_names.extend(sc.get("linked_to", []))
            candidate_names.extend(concept.get("links_to", []))

            in_pool = [n for n in candidate_names if n in concept_lookup and n != concept_name]
            if in_pool:
                linked_name    = random.choice(in_pool)
                linked_concept = concept_lookup[linked_name]
                linked_pool    = linked_concept.get("sub_concepts", [])
                if linked_pool:
                    chosen_linked = random.choice(linked_pool)
                    aspects       = chosen_linked.get("aspects") or [chosen_linked.get("aspect", "process")]
                    linked_sc = {
                        "topic":          chosen_linked["topic"],
                        "aspect":         aspects[0] if aspects else "process",
                        "source_concept": linked_name,
                    }

        # 6c. Build SubConceptItem list
        sub_concept_items: list = []
        for sc in sampled_own:
            aspects = sc.get("aspects") or [sc.get("aspect", "process")]
            sub_concept_items.append(SubConceptItem(
                topic          = sc["topic"],
                aspect         = aspects[0] if aspects else "process",
                source_concept = "",
            ))
        if linked_sc:
            sub_concept_items.append(SubConceptItem(
                topic          = linked_sc["topic"],
                aspect         = linked_sc["aspect"],
                source_concept = linked_sc["source_concept"],
            ))
        if not sub_concept_items:
            sub_concept_items = [SubConceptItem(
                topic="General concept", aspect="process", source_concept=""
            )]

        # 6d. Trap selection — exclude exhausted, prefer least-used this session
        valid_traps   = _traps_for_concept(concept, all_traps)
        fresh_traps   = [t for t in valid_traps if t["trap_id"] not in traps_exhausted_set]
        candidate_pool = fresh_traps if fresh_traps else valid_traps

        # Sort by session usage; pick randomly from bottom half to stay diverse
        sorted_traps = sorted(candidate_pool, key=lambda t: trap_use.get(t["trap_id"], 0))
        pick_pool    = sorted_traps[:max(1, len(sorted_traps) // 2 + 1)]
        trap         = random.choice(pick_pool) if pick_pool else {}
        if trap:
            tid = trap.get("trap_id", "")
            trap_use[tid] = trap_use.get(tid, 0) + 1

        slots.append({
            "concept":      concept_name,
            "sub_concepts": sub_concept_items,
            "trap_id":      trap.get("trap_id", ""),
            "trap_name":    trap.get("name", ""),
            "difficulty":   difficulty,
            "ca_linked":    ca_linked,
            "ca_event":     "",   # LLM fills this
            "ca_triggers":  concept.get("ca_trigger_types", []),
        })

    logger.info(
        f"[Stage0] Pre-sampled {len(slots)} slots — "
        f"concepts used: {sorted(set(s['concept'] for s in slots))}"
    )
    return slots


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
    ledger: Optional[dict] = None,
) -> str:
    easy, medium, hard, pure_ca = _difficulty_counts(cfg, num_questions)
    scale    = num_questions / 10   # type range baseline is per-10

    all_traps = _get_all_traps(trap_registry)

    # Build lookup once — passed into every _concept_block call
    all_concepts_lookup = {c["concept"]: c for c in concept_pool}

    concept_blocks = "\n".join(
        _concept_block(c, all_traps, all_concepts_lookup)
        for c in concept_pool
    )

    type_ranges = _type_ranges_str(cfg, scale)

    # Optional diversity constraints from user's concept ledger
    from .user_ledger import build_diversity_constraints
    diversity_block = build_diversity_constraints(ledger, concept_pool, num_questions)

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

{diversity_block}
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


# ── Slots-based prompt (v4) ────────────────────────────────────────────────────

def _build_slots_prompt(
    cfg:          SubjectConfig,
    slots:        list,
    trap_registry: dict,
    domain:       str,
    subdomain:    str,
) -> str:
    """
    Build a focused prompt where sub_concepts + traps are already pre-sampled.
    LLM only assigns question_type, ca_event, linked_concept, and an optional swap.
    """
    all_traps  = _get_all_traps(trap_registry)
    valid_types = list(cfg.question_type_ranges.keys())
    types_str   = " | ".join(valid_types)

    slot_blocks = []
    for i, slot in enumerate(slots, 1):
        # Sub_concept lines
        sc_lines = "\n".join(
            f'    - "{sc.topic}" [aspect={sc.aspect}'
            + (f', source_concept="{sc.source_concept}"' if sc.source_concept else "")
            + "]"
            for sc in slot["sub_concepts"]
        )

        # Trap description (brief)
        trap_info = ""
        trap_obj  = all_traps.get(slot["trap_id"], {})
        if trap_obj:
            trap_info = f'{slot["trap_id"]}: {trap_obj.get("name", "")} — {trap_obj.get("description", "")[:90]}'
        else:
            trap_info = slot["trap_id"] or "(none)"

        # CA block — show ca_trigger candidates so LLM can write a specific event
        ca_block = ""
        if slot["ca_linked"] and slot["ca_triggers"]:
            ca_opts = "\n".join(f"      * {ct}" for ct in slot["ca_triggers"][:4])
            ca_block = f"\n  ca_trigger candidates (adapt one into a datable ca_event):\n{ca_opts}"

        ca_label = "true — YOU MUST write ca_event" if slot["ca_linked"] else "false"

        slot_blocks.append(
            f"SLOT {i}:\n"
            f"  concept    : {slot['concept']}\n"
            f"  difficulty : {slot['difficulty']}\n"
            f"  trap_id    : {trap_info}\n"
            f"  ca_linked  : {ca_label}\n"
            f"  sub_concepts (pre-assigned — change only if combination is incoherent):\n"
            f"{sc_lines}"
            f"{ca_block}"
        )

    slots_text = "\n\n".join(slot_blocks)
    num_slots  = len(slots)

    return f"""You are an expert UPSC Prelims question paper setter.
The question ingredients (concept, sub_concepts, trap) are pre-assigned.
Your only job is to decide question_type + ca_event for each slot.

═══════════════════════════════════════════════
CONTEXT
  subject  : {cfg.subject}
  domain   : {domain}
  subdomain: {subdomain}

Valid question types: {types_str}

Guidance:
  easy   → prefer direct_fact or match_pair
  medium → prefer multi_statement
  hard   → prefer assertion_reason or multi_statement

═══════════════════════════════════════════════
PRE-ASSIGNED SLOTS

{slots_text}

═══════════════════════════════════════════════
INSTRUCTIONS

For each slot:
1. Choose the most appropriate question_type from: {types_str}
2. If ca_linked=true: write a specific, datable ca_event string (NOT a generic phrase).
   Use one of the ca_trigger candidates as a starting point and make it concrete.
   Example: "IMD issued below-normal monsoon forecast for 2024 attributing it to El Nino"
3. For assertion_reason questions: set linked_concept to the name of the second concept
   being tested. Use the source_concept from the sub_concepts list as a hint.
4. If a sub_concept combination is genuinely incoherent (e.g. sub_concepts from
   completely unrelated domains), you MAY swap ONE sub_concept by setting swap_sub_concept:
   {{"index": 0|1|2, "new_topic": "...", "new_aspect": "...", "new_source_concept": ""}}
   Leave swap_sub_concept as null if the combination is acceptable.

═══════════════════════════════════════════════
OUTPUT — return ONLY this JSON, no markdown:
{{
  "completions": [
    {{
      "id": "Q1",
      "question_type": "multi_statement",
      "ca_event": "",
      "linked_concept": null,
      "swap_sub_concept": null
    }},
    ...
  ]
}}

Generate exactly {num_slots} completion objects, one per slot in order.
"""


def _rule_based_fallback(
    num_questions: int,
    concept_pool:  list,
    trap_registry: dict,
    cfg:           SubjectConfig,
    slots:         Optional[list] = None,
) -> List[QuestionSkeleton]:
    """
    Fallback when the LLM call fails.
    Reuses pre-sampled slots if provided (so ingredients are still diverse).
    Falls back to plain round-robin only when no slots are available.
    """
    logger.info(f"[Stage0] Rule-based fallback for {num_questions} skeletons")

    if slots is None:
        slots = _pre_sample_slots(cfg, num_questions, concept_pool, trap_registry, None)

    types_pool = list(cfg.question_type_ranges.keys())

    # Difficulty → preferred question type mapping
    type_by_difficulty = {
        "easy":   next((t for t in ["direct_fact", "match_pair"] if t in types_pool), types_pool[0]),
        "medium": next((t for t in ["multi_statement"] if t in types_pool), types_pool[0]),
        "hard":   next((t for t in ["assertion_reason", "multi_statement"] if t in types_pool), types_pool[-1]),
        "pure_ca": next((t for t in ["direct_fact", "multi_statement"] if t in types_pool), types_pool[0]),  # CA-focused type
    }

    skeletons = []
    for i, slot in enumerate(slots):
        difficulty = slot["difficulty"]
        is_pure_ca = difficulty == "pure_ca"

        # Map pure_ca to a concrete difficulty for generation (use easy as base)
        actual_difficulty = "easy" if is_pure_ca else difficulty
        qtype = type_by_difficulty.get(difficulty, types_pool[i % len(types_pool)])

        skeletons.append(QuestionSkeleton(
            skeleton_id    = f"sk_{i+1:03d}",
            question_type  = qtype,
            concept        = slot["concept"],
            sub_concepts   = slot["sub_concepts"],
            difficulty     = actual_difficulty,
            pure_ca        = is_pure_ca,
            ca_flag        = True if is_pure_ca else slot["ca_linked"],  # Pure CA always needs CA search
            ca_event       = "",   # no LLM available to write ca_event
            trap_strategy  = slot["trap_id"],
            trap_name      = slot["trap_name"],
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


def _to_skeleton_from_slot(
    slot:       dict,
    completion: SlotCompletion,
    idx:        int,
    cfg:        SubjectConfig,
) -> QuestionSkeleton:
    """
    Merge a pre-sampled slot with the LLM's SlotCompletion into a QuestionSkeleton.
    Applies optional sub_concept swap if the LLM flagged an incoherent combination.
    """
    sub_concepts = list(slot["sub_concepts"])

    swap = completion.swap_sub_concept
    if swap and isinstance(swap, dict):
        swap_idx = swap.get("index", -1)
        if isinstance(swap_idx, int) and 0 <= swap_idx < len(sub_concepts):
            old_sc = sub_concepts[swap_idx]
            sub_concepts[swap_idx] = SubConceptItem(
                topic          = swap.get("new_topic", old_sc.topic),
                aspect         = swap.get("new_aspect", old_sc.aspect),
                source_concept = swap.get("new_source_concept", old_sc.source_concept),
            )

    return QuestionSkeleton(
        skeleton_id    = f"sk_{idx:03d}",
        question_type  = completion.question_type,
        concept        = slot["concept"],
        sub_concepts   = sub_concepts,
        difficulty     = slot["difficulty"],
        ca_flag        = slot["ca_linked"],
        ca_event       = completion.ca_event or "",
        trap_strategy  = slot["trap_id"],
        trap_name      = slot["trap_name"],
        sub_domain     = cfg.subject,
        linked_concept = completion.linked_concept,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_blueprint(
    num_questions: int,
    topics:        List[str],
    subject:       str,
    gemini_client,
    domain:        str = "",
    subdomain:     str = "",
    ledger:        Optional[dict] = None,
) -> List[QuestionSkeleton]:
    """
    Stage 0: generate a structured question blueprint before any retrieval.

    v4 flow:
      1. Python pre-samples all ingredients (concept, sub_concepts, trap, difficulty, CA).
      2. Gemini Flash only assigns question_type + ca_event + optional sub_concept swap.
      3. On LLM failure, rule-based fallback reuses the same pre-sampled slots.

    Args:
        ledger: Optional user concept ledger (Redis). When present, concept selection
                is biased toward fresh concepts and exhausted traps are excluded.
    """
    cfg       = get_subject_config(subject)
    domain    = domain    or cfg.subject
    subdomain = subdomain or (topics[0] if topics else cfg.subject)

    logger.info(
        f"[Stage0] Blueprint: {num_questions}Q | {cfg.subject} > {domain} > {subdomain}"
        + (" [ledger active]" if ledger else "")
    )

    trap_registry = _load_trap_registry(cfg)
    concept_pool  = _load_concept_pool(cfg.subject, subdomain)

    # Build concept pool from trap sub_domains if pool file is missing
    if not concept_pool:
        logger.warning(f"[Stage0] No concept pool for {cfg.subject}/{subdomain} — building from trap sub_domains")
        seen: set = set()
        all_traps = _get_all_traps(trap_registry)
        for t in all_traps.values():
            for sd in t.get("sub_domains", []):
                if sd not in seen:
                    concept_pool.append({
                        "concept":          sd,
                        "priority":         "medium",
                        "sub_concepts":     [],
                        "trap_affinity":    [t["trap_id"]],
                        "links_to":         [],
                        "ca_trigger_types": [],
                    })
                    seen.add(sd)

    # ── Step 1: Python pre-samples all slot ingredients ──────────────────────
    slots = _pre_sample_slots(cfg, num_questions, concept_pool, trap_registry, ledger)

    # ── Step 2: LLM assigns question_type + ca_event per slot ────────────────
    prompt = _build_slots_prompt(
        cfg=cfg,
        slots=slots,
        trap_registry=trap_registry,
        domain=domain,
        subdomain=subdomain,
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
            response_schema=SlotCompletionOutput,
            temperature=0.7,
            use_google_search=False,
        )

        output      = SlotCompletionOutput.model_validate_json(response_text)
        completions = output.completions[:num_questions]

        # Merge pre-sampled slots with LLM completions
        skeletons = [
            _to_skeleton_from_slot(slot, comp, i + 1, cfg)
            for i, (slot, comp) in enumerate(zip(slots, completions))
        ]

        # Pad with fallback skeletons if LLM returned fewer completions than slots
        if len(skeletons) < len(slots):
            fallback_skeletons = _rule_based_fallback(
                num_questions, concept_pool, trap_registry, cfg, slots[len(skeletons):]
            )
            skeletons.extend(fallback_skeletons)

        logger.info(f"[Stage0] Flash success: {len(skeletons)}/{num_questions} skeletons")

        empty_ca = [s.skeleton_id for s in skeletons if s.ca_flag and not s.ca_event]
        if empty_ca:
            logger.warning(f"[Stage0] ca_event empty on ca_linked skeletons: {empty_ca}")

        return skeletons

    except Exception as e:
        logger.error(f"[Stage0] Flash failed: {e} — using rule-based fallback with pre-sampled slots")
        return _rule_based_fallback(num_questions, concept_pool, trap_registry, cfg, slots)