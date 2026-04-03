"""
Stage 0 — Blueprint Generation (v5)

v5 REDESIGN: Two-pass structure
  1. Python randomly samples: difficulty_type (15 types, weighted), concept (by priority)
  2. Stage 0 LLM structures the skeleton:
     - Selects sub_concepts that fit the difficulty_type
     - Decides ca_flag based on concept.ca_connectable + difficulty_type
     - Picks linked_concept from links_to (only if difficulty_type expects linking)
     - Lists available_trap_ids (all traps that fit this concept + difficulty_type)
     - Lists available_question_types (all QTs that fit this difficulty_type)
  3. Stage 3 LLM uses skeleton to generate: chooses trap_id + question_type + writes question

Key insight: Move sub_concepts selection and trap/QT filtering UP to Stage 0.
Stage 3 focuses purely on generation, not structure.
"""
from __future__ import annotations

import json
import logging
import math
import random
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
from .models import SubConceptItem, QuestionSkeleton

logger = logging.getLogger(__name__)

_V2_DIR = Path(__file__).parent
_CONFIG_DIR = _V2_DIR.parent.parent.parent / "config"

# Weight multipliers for priority-based concept selection
_PRIORITY_WEIGHT: dict = {"high": 3, "medium": 2, "low": 1}


# ── Difficulty Type Taxonomy & Mappings ───────────────────────────────────────

DIFFICULTY_TYPE_TO_QUESTION_TYPES = {
    # EASY (15 questions total)
    "easy_recall_static": ["direct_fact", "match_pair"],
    "easy_ca_trigger": ["direct_fact", "pure_ca"],
    "easy_reverse_mild": ["direct_fact", "multi_statement"],

    # MEDIUM (25 questions total)
    "medium_concept_linking_same_domain": ["assertion_reason", "multi_statement"],
    "medium_adjacent_fact": ["match_pair", "multi_statement"],
    "medium_statistical_reversal": ["multi_statement", "assertion_reason"],
    "medium_precision_location": ["match_pair", "multi_statement"],
    "medium_ca_integration": ["multi_statement", "assertion_reason"],

    # HARD (50 questions total)
    "hard_counterintuitive_single_concept": ["assertion_reason", "multi_statement"],
    "hard_cross_domain_linking": ["assertion_reason"],
    "hard_all_of_above_precision": ["multi_statement"],
    "hard_strong_concept_depth": ["assertion_reason"],
    "hard_spatial_sequence": ["assertion_reason", "match_pair"],
    "hard_reverse_extreme": ["assertion_reason"],

    # PURE_CA (10 questions total)
    "pure_ca_news_tracking": ["direct_fact", "pure_ca"],
    "pure_ca_recent_event": ["direct_fact", "pure_ca"],
}

# Difficulty types that expect concept linking (cross-domain or same-domain)
DIFFICULTY_TYPES_THAT_LINK = {
    "medium_concept_linking_same_domain",
    "hard_cross_domain_linking",
}

# Difficulty types that are especially good for CA integration
# Expanded to reach 30% target
CA_FRIENDLY_DIFFICULTY_TYPES = {
    "easy_ca_trigger",
    "easy_reverse_mild",                  # Can be CA-triggered
    "medium_ca_integration",
    "medium_concept_linking_same_domain", # Can have CA aspect
    "pure_ca_news_tracking",
    "pure_ca_recent_event",
}


class SkeletonV5(BaseModel):
    """Enhanced skeleton output from Stage 0 LLM.

    Unlike v4 (which pre-sampled sub_concepts), v5 has LLM determine:
    - Which sub_concepts fit this difficulty_type
    - Which traps work with this concept + difficulty_type
    - Which question_types are appropriate for this difficulty_type
    """
    skeleton_id: str
    subject: str
    domain: str
    subdomain: str

    # Python-sampled (Stage 0 deterministic)
    difficulty_type: str  # e.g., "hard_cross_domain_linking"
    concept: str
    trap_affinity: List[str]  # from concept pool

    # Stage 0 LLM-determined (structure of the question)
    sub_concepts: List[SubConceptItem]  # 2-3 sub_concepts chosen for this difficulty
    ca_flag: bool  # should this be CA-linked?
    linked_concept: Optional[str] = None  # second concept (only if difficulty expects linking)

    # Constraints for Stage 3 LLM
    available_trap_ids: List[str]  # Stage 3 picks one from this list
    available_question_types: List[str]  # Stage 3 picks one from this list

    # For Stage 3 generation (filled later)
    question_type: Optional[str] = None
    trap_id: Optional[str] = None
    ca_event: str = ""


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


def _load_trap_registry(subject: str) -> dict:
    trap_file = f"traps_{subject.lower().replace(' ', '_')}_climatology.json"
    return _load_json(_V2_DIR / trap_file, "trap registry")


def _load_difficulty_types(subject: str, subdomain: str) -> dict:
    """Load difficulty_types_geography_base.json or equivalent."""
    diff_file = f"difficulty_types_{subject.lower().replace(' ', '_')}_base.json"
    data = _load_json(_V2_DIR / diff_file, "difficulty types taxonomy")
    return data.get("difficulty_types", {})


def _normalise_concept_dict(concepts_dict: dict) -> list:
    """Convert dict-keyed concept pool to flat list format."""
    result = []
    for name, entry in concepts_dict.items():
        raw_scs = entry.get("sub_concepts", [])
        norm_scs = []
        for sc in raw_scs:
            aspects = sc.get("aspects") or []
            if isinstance(aspects, str):
                aspects = [aspects]
            if not aspects and sc.get("aspect"):
                aspects = [sc["aspect"]]
            if not aspects:
                aspects = ["process"]

            norm_scs.append({
                "topic":          sc["topic"],
                "aspect":         aspects[0],
                "aspects":        aspects,
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
    sub_slug = subdomain.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    candidate = _V2_DIR / "concept_pools" / f"{subj_slug}_{sub_slug}.json"
    data = _load_json(candidate, "concept pool")
    if data:
        raw = data.get("concepts", [])
        return _normalise_concept_dict(raw) if isinstance(raw, dict) else raw
    return []


def _get_concept_trap_mapping(trap_registry: dict) -> dict:
    """Get concept -> [trap_ids] mapping from registry."""
    return trap_registry.get("concept_trap_mapping", {})


def _get_trap_details(trap_registry: dict) -> dict:
    """Get trap_id -> details mapping from registry."""
    return trap_registry.get("trap_patterns", {})


def _traps_for_concept(concept_name: str, concept_trap_mapping: dict) -> list:
    """Return list of trap IDs available for this concept."""
    return concept_trap_mapping.get(concept_name, [])


# ── Difficulty Type Sampling ──────────────────────────────────────────────────

def _sample_difficulty_types(
    difficulty_types_taxonomy: dict,
    num_questions: int,
    ca_linkage_rate: float = 0.30,
) -> list:
    """
    Sample difficulty types weighted by their percentage_in_climatology.

    ENFORCES that ca_linkage_rate % of questions are CA-friendly types.

    Returns: list of difficulty_type strings, one per question.
    """
    # Split: CA-friendly vs non-CA
    ca_friendly_types = [
        dt for dt in difficulty_types_taxonomy.keys()
        if dt in CA_FRIENDLY_DIFFICULTY_TYPES
    ]
    non_ca_types = [
        dt for dt in difficulty_types_taxonomy.keys()
        if dt not in CA_FRIENDLY_DIFFICULTY_TYPES
    ]

    num_ca = round(num_questions * ca_linkage_rate)
    num_non_ca = num_questions - num_ca

    # Sample CA-friendly types
    ca_sampled = [
        random.choice(ca_friendly_types) for _ in range(num_ca)
    ]

    # Sample non-CA types (weighted by percentage)
    non_ca_weighted = []
    for diff_type in non_ca_types:
        config = difficulty_types_taxonomy.get(diff_type, {})
        pct = config.get("percentage_in_climatology", 0.05)
        count = max(1, round(pct * num_non_ca / 0.7))  # normalize to 70%
        non_ca_weighted.extend([diff_type] * count)

    non_ca_sampled = [
        random.choice(non_ca_weighted) for _ in range(num_non_ca)
    ] if non_ca_weighted else [random.choice(non_ca_types) for _ in range(num_non_ca)]

    # Combine and shuffle
    all_sampled = ca_sampled + non_ca_sampled[:num_non_ca]
    random.shuffle(all_sampled)
    return all_sampled[:num_questions]


# ── Concept Sampling ──────────────────────────────────────────────────────────

def _sample_concepts(
    num_questions: int,
    concept_pool: list,
) -> list:
    """
    Sample concepts with priority weighting.
    Ensure variety: at least 5 different concepts, max 3 per concept.
    """
    weighted_pool = []
    for c in concept_pool:
        weight = _PRIORITY_WEIGHT.get(c.get("priority", "medium"), 2)
        weighted_pool.extend([c["concept"]] * weight)

    random.shuffle(weighted_pool)

    concept_counts = {}
    concepts_assigned = []
    unique_needed = min(5, len(concept_pool))
    unique_seen = set()

    supply = (weighted_pool * max(3, num_questions))[:num_questions * 3]
    for concept_name in supply:
        if len(concepts_assigned) >= num_questions:
            break
        if concept_counts.get(concept_name, 0) >= 3:
            continue
        concepts_assigned.append(concept_name)
        concept_counts[concept_name] = concept_counts.get(concept_name, 0) + 1
        unique_seen.add(concept_name)

    while len(concepts_assigned) < num_questions:
        c = random.choice(concept_pool)
        if concept_counts.get(c["concept"], 0) < 3:
            concepts_assigned.append(c["concept"])
            concept_counts[c["concept"]] = concept_counts.get(c["concept"], 0) + 1

    return concepts_assigned[:num_questions]


# ── Slot Preparation (v5: minimal pre-sampling) ────────────────────────────────

def _prepare_slots(
    num_questions: int,
    subject: str,
    subdomain: str,
    concept_pool: list,
    trap_registry: dict,
    difficulty_types_taxonomy: dict,
    ca_linkage_rate: float = 0.30,
) -> list:
    """
    Pre-sample only the STRUCTURE, not the details.

    Returns: list of slot dicts with:
      - difficulty_type
      - concept_name
      - trap_affinity (all traps for this concept)
      - ca_trigger_types
      - ca_connectable (overall concept-level flag)
      - links_to (available concepts to link to)
    """
    # 1. Sample difficulty types (weighted, with CA enforcement)
    difficulty_types = _sample_difficulty_types(
        difficulty_types_taxonomy, num_questions, ca_linkage_rate
    )

    # 2. Sample concepts (priority-weighted, diverse)
    concepts_assigned = _sample_concepts(num_questions, concept_pool)

    # 3. Build lookups
    concept_lookup = {c["concept"]: c for c in concept_pool}
    concept_trap_mapping = _get_concept_trap_mapping(trap_registry)

    # 4. Build slots
    slots = []
    for i, (diff_type, concept_name) in enumerate(zip(difficulty_types, concepts_assigned)):
        concept = concept_lookup.get(concept_name, concept_pool[0])
        traps_available = _traps_for_concept(concept_name, concept_trap_mapping)

        slots.append({
            "slot_id": f"slot_{i+1:02d}",
            "difficulty_type": diff_type,
            "concept": concept_name,
            "trap_affinity": traps_available,
            "ca_trigger_types": concept.get("ca_trigger_types", []),
            "links_to": concept.get("links_to", []),
            "sub_concepts_pool": concept.get("sub_concepts", []),
            "ca_connectable_overall": any(
                sc.get("ca_connectable", False)
                for sc in concept.get("sub_concepts", [])
            ),
        })

    logger.info(
        f"[Stage0 v5] Prepared {num_questions} slots: "
        f"concepts={sorted(set(concepts_assigned))}, "
        f"difficulty_types={sorted(set(difficulty_types))}"
    )
    return slots


# ── LLM Prompt ────────────────────────────────────────────────────────────────

def _build_skeleton_prompt(
    subject: str,
    subdomain: str,
    slots: list,
    concept_pool: list,
    difficulty_types_taxonomy: dict,
) -> str:
    """
    Prompt for Stage 0 LLM to build the skeleton.

    Input: slots with difficulty_type + concept
    Output: sub_concepts + ca_flag + linked_concept + available_trap_ids + available_question_types
    """
    slot_blocks = []
    for slot in slots:
        diff_type = slot["difficulty_type"]
        concept = slot["concept"]

        # Show available question types for this difficulty_type
        available_qts = DIFFICULTY_TYPE_TO_QUESTION_TYPES.get(diff_type, [])
        qts_str = " | ".join(available_qts)

        # Show available sub_concepts to pick from
        scs_str = "\n".join(
            f"    - {sc['topic']} [aspect={sc['aspect']}, ca_connectable={sc.get('ca_connectable', False)}]"
            for sc in slot["sub_concepts_pool"][:5]  # Show first 5
        )

        # Show available linked concepts
        links_str = ", ".join(slot["links_to"]) if slot["links_to"] else "none"

        # Show guidelines for this difficulty type
        diff_config = difficulty_types_taxonomy.get(diff_type, {})
        description = diff_config.get("description", "")
        characteristics = "\n".join(f"    • {c}" for c in diff_config.get("characteristics", [])[:3])

        # Show expected sub_concepts count from blueprint selection
        blueprint_selection = diff_config.get("blueprint_selection", "")

        slot_blocks.append(f"""
SLOT {slot["slot_id"]}:
  Difficulty Type: {diff_type}
  Concept: {concept}

  Description: {description}
  Key Characteristics:
{characteristics}

  Available sub_concepts (pick 2-3):
{scs_str}

  Available linked_concepts: {links_str}
  Expected question types: {qts_str}

  Blueprint guidance: {blueprint_selection}
  Should link concepts: {"YES (expected for this type)" if diff_type in DIFFICULTY_TYPES_THAT_LINK else "NO (not typical for this type)"}
  CA-friendly: {"YES" if diff_type in CA_FRIENDLY_DIFFICULTY_TYPES else "NO"}
""")

    slots_text = "\n".join(slot_blocks)

    return f"""You are an expert UPSC Prelims question structure architect.

Your task: For each slot, STRUCTURE the question by determining:
1. Which sub_concepts from the pool fit this difficulty_type
2. Whether to link a second concept (only if difficulty_type expects linking)
3. What CA integration makes sense
4. Which traps + question_types are available

SUBJECT: {subject} > {subdomain}

═══════════════════════════════════════════════════════════
SLOTS TO STRUCTURE

{slots_text}

═══════════════════════════════════════════════════════════
INSTRUCTIONS

For each slot:

1. SELECT SUB_CONCEPTS (2-3):
   - Pick sub_concepts that specifically test this difficulty_type
   - Easy types: pick 1-2 simple, direct sub_concepts
   - Hard types: pick sub_concepts that require depth understanding
   - Example: for hard_counterintuitive_single_concept on Monsoon,
     pick "Monsoon Onset" (mechanism aspect) and maybe one more about triggers

2. DECIDE CA_FLAG:
   - true if: concept has ca_connectable sub_concepts AND (difficulty_type in CA_FRIENDLY_DIFFICULTY_TYPES)
   - false otherwise
   - Example: pure_ca_news_tracking → always true; easy_recall_static → usually false

3. PICK LINKED_CONCEPT (only if needed):
   - If difficulty_type in {DIFFICULTY_TYPES_THAT_LINK}: pick one from links_to list
   - Otherwise: leave as null
   - For cross_domain linking: prefer concepts from different domains

4. AVAILABLE_TRAP_IDS:
   - List all trap_ids that work for this concept (from trap_affinity)
   - These are traps that can be used to distract students on this concept
   - No filtering needed — Stage 3 will pick based on question_type

5. AVAILABLE_QUESTION_TYPES:
   - List all question_types that fit this difficulty_type
   - From the "Expected question types" field above
   - Stage 3 will pick one that works with the trap

═══════════════════════════════════════════════════════════
OUTPUT FORMAT

Return ONLY valid JSON (no markdown, no explanation):

{{
  "skeletons": [
    {{
      "slot_id": "slot_01",
      "sub_concepts": [
        {{"topic": "exact topic from pool", "aspect": "mechanism|process|comparison|impact|application", "source_concept": ""}},
        {{"topic": "exact topic", "aspect": "...", "source_concept": ""}}
      ],
      "ca_flag": true|false,
      "linked_concept": null|"ConceptName",
      "available_trap_ids": ["TRAP_ID1", "TRAP_ID2", ...],
      "available_question_types": ["assertion_reason", "multi_statement", ...],
      "reasoning": "Brief explanation of why these choices fit the difficulty_type"
    }},
    ...
  ]
}}

Generate exactly {len(slots)} skeleton objects, one per slot in order.
"""


# ── Main Function ──────────────────────────────────────────────────────────────

async def generate_blueprint_v5(
    num_questions: int,
    subject: str,
    subdomain: str,
    gemini_client,
) -> List[SkeletonV5]:
    """
    Stage 0 v5: Generate structured skeletons via two-pass process.

    Pass 1: Python deterministically samples difficulty_type + concept
    Pass 2: LLM structurally reasons about sub_concepts + traps + question_types
    """
    logger.info(f"[Stage0 v5] Generating {num_questions} skeletons for {subject}/{subdomain}")

    # Load data
    concept_pool = _load_concept_pool(subject, subdomain)
    if not concept_pool:
        logger.error(f"[Stage0 v5] No concept pool for {subject}/{subdomain}")
        return []

    trap_registry = _load_trap_registry(subject)
    difficulty_types_taxonomy = _load_difficulty_types(subject, subdomain)

    if not difficulty_types_taxonomy:
        logger.error(f"[Stage0 v5] No difficulty types taxonomy for {subject}/{subdomain}")
        return []

    # Prepare slots (Python sampling only)
    slots = _prepare_slots(
        num_questions,
        subject,
        subdomain,
        concept_pool,
        trap_registry,
        difficulty_types_taxonomy,
    )

    # Build prompt for LLM
    prompt = _build_skeleton_prompt(
        subject,
        subdomain,
        slots,
        concept_pool,
        difficulty_types_taxonomy,
    )

    # Call LLM
    from .gemini_utils import make_flash_client
    flash_client = make_flash_client(gemini_client)

    try:
        response_text = await flash_client.generate_response(
            user_prompt=prompt,
            system_prompt="You are an expert UPSC Prelims question architect. Output ONLY valid JSON.",
            response_schema=None,  # We'll parse manually for more flexibility
            temperature=0.7,
            use_google_search=False,
        )

        # Parse response
        data = json.loads(response_text)
        skeleton_dicts = data.get("skeletons", [])

        # Convert to SkeletonV5 objects
        skeletons = []
        concept_lookup = {c["concept"]: c for c in concept_pool}

        for i, (slot, skel_dict) in enumerate(zip(slots, skeleton_dicts)):
            concept = concept_lookup.get(slot["concept"], concept_pool[0])

            # Build SubConceptItem list
            sub_concept_items = []
            for sc_dict in skel_dict.get("sub_concepts", []):
                sub_concept_items.append(SubConceptItem(
                    topic=sc_dict.get("topic", ""),
                    aspect=sc_dict.get("aspect", "process"),
                    source_concept=sc_dict.get("source_concept", ""),
                ))

            skeleton = SkeletonV5(
                skeleton_id=f"sk_{i+1:03d}",
                subject=subject,
                domain=subject,
                subdomain=subdomain,
                difficulty_type=slot["difficulty_type"],
                concept=slot["concept"],
                trap_affinity=skel_dict.get("available_trap_ids", []),
                sub_concepts=sub_concept_items,
                ca_flag=skel_dict.get("ca_flag", False),
                linked_concept=skel_dict.get("linked_concept"),
                available_trap_ids=skel_dict.get("available_trap_ids", []),
                available_question_types=skel_dict.get("available_question_types", ["multi_statement"]),
            )
            skeletons.append(skeleton)

        logger.info(f"[Stage0 v5] Generated {len(skeletons)} skeletons")
        return skeletons

    except Exception as e:
        logger.error(f"[Stage0 v5] LLM failed: {e}")
        return []


# ── Testing ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import json

    async def test_v5():
        """Test: generate 10 skeletons from climatology."""
        # Load data directly
        concept_pool = _load_concept_pool("Geography", "Climatology")
        trap_registry = _load_trap_registry("Geography")
        difficulty_types_taxonomy = _load_difficulty_types("Geography", "Climatology")

        print(f"\n✓ Loaded {len(concept_pool)} concepts")
        print(f"✓ Loaded {len(trap_registry.get('trap_patterns', {}))} traps")
        print(f"✓ Loaded {len(difficulty_types_taxonomy)} difficulty types")

        # Prepare 10 slots
        slots = _prepare_slots(
            10,
            "Geography",
            "Climatology",
            concept_pool,
            trap_registry,
            difficulty_types_taxonomy,
        )

        print(f"\n{'='*80}")
        print("PREPARED SLOTS (Stage 0 Python Sampling)")
        print(f"{'='*80}\n")

        for slot in slots:
            print(f"Slot: {slot['slot_id']}")
            print(f"  Difficulty Type: {slot['difficulty_type']}")
            print(f"  Concept: {slot['concept']}")
            print(f"  Sub-concepts available: {len(slot['sub_concepts_pool'])}")
            print(f"  Traps available: {slot['trap_affinity']}")
            print(f"  Links to: {slot['links_to']}")
            print()

        # Build skeleton prompt (what LLM sees)
        prompt = _build_skeleton_prompt(
            "Geography",
            "Climatology",
            slots,
            concept_pool,
            difficulty_types_taxonomy,
        )

        print(f"\n{'='*80}")
        print("SKELETON PROMPT (First 1500 chars - what Stage 0 LLM receives)")
        print(f"{'='*80}\n")
        print(prompt[:1500])
        print("\n[... truncated ...]")

        # Show all 10 skeletons in table format
        print(f"\n{'='*100}")
        print("10-QUESTION SKELETON DISTRIBUTION (Stage 0 v5 Output)")
        print(f"{'='*100}\n")

        print(f"{'Q#':<3} {'Difficulty Type':<35} {'Concept':<25} {'Traps':<25} {'CA?':<4} {'Link':<20}")
        print(f"{'-'*100}")

        for i, slot in enumerate(slots, 1):
            diff_type = slot["difficulty_type"]
            concept = slot["concept"]
            traps = ", ".join(slot["trap_affinity"][:2]) if slot["trap_affinity"] else "none"
            ca_flag = "✓" if slot["ca_connectable_overall"] and diff_type in CA_FRIENDLY_DIFFICULTY_TYPES else "-"
            links = slot["links_to"][0] if slot["links_to"] else "-"

            print(f"{i:<3} {diff_type:<35} {concept:<25} {traps:<25} {ca_flag:<4} {links:<20}")

        # Count distribution
        print(f"\n{'-'*100}")
        print("\nDISTRIBUTION ANALYSIS:")
        by_difficulty = {}
        for slot in slots:
            dt = slot["difficulty_type"]
            category = "EASY" if "easy" in dt else "MEDIUM" if "medium" in dt else "HARD" if "hard" in dt else "CA"
            by_difficulty[category] = by_difficulty.get(category, 0) + 1

        for cat in ["EASY", "MEDIUM", "HARD", "CA"]:
            count = by_difficulty.get(cat, 0)
            pct = (count / 10) * 100
            print(f"  {cat:<8}: {count} questions ({pct:5.1f}%)")

        # Show example LLM output
        print(f"\n{'='*100}")
        print("EXAMPLE SKELETON OUTPUT (What Stage 0 LLM Produces)")
        print(f"{'='*100}\n")

        example = {
            "slot_id": "slot_07",
            "sub_concepts": [
                {"topic": "Pressure Belt Distribution", "aspect": "distribution", "source_concept": ""},
                {"topic": "Tropical Easterly Jet", "aspect": "mechanism", "source_concept": "Jet Streams"}
            ],
            "ca_flag": False,
            "linked_concept": "Jet Streams",
            "available_trap_ids": ["GEO_C_T03", "GEO_C_T04"],
            "available_question_types": ["assertion_reason", "multi_statement"],
            "reasoning": "Hard counterintuitive requires understanding pressure belts which are often confused. Linking to Jet Streams adds depth: students must know jet streams correlate with pressure belt position. No CA integration needed. Traps T03 (jet stream latitude precision) and T04 (climate classification) both applicable."
        }
        print(json.dumps(example, indent=2))

        print(f"\n{'='*80}")
        print("SUMMARY: Stage 0 Output Ready for Stage 1 Retrieval")
        print(f"{'='*80}\n")
        print("Each skeleton now contains:")
        print("  ✓ difficulty_type (15 specific types, not just easy/medium/hard)")
        print("  ✓ concept (randomly sampled by priority)")
        print("  ✓ sub_concepts (LLM-selected for this difficulty)")
        print("  ✓ ca_flag (LLM decided based on CA-friendliness)")
        print("  ✓ linked_concept (LLM picked from links_to if needed)")
        print("  ✓ available_trap_ids (all valid traps for this concept)")
        print("  ✓ available_question_types (all valid QTs for this difficulty_type)")
        print("\nStage 3 LLM will:")
        print("  ✓ Pick trap_id from available_trap_ids")
        print("  ✓ Pick question_type from available_question_types")
        print("  ✓ Generate question using retrieval chunks + trap strategy")
        print()

    asyncio.run(test_v5())
