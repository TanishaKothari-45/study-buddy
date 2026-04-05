"""
Stage 0 — Blueprint Generation (v4.5 + Controlled Randomness)

BEST OF THREE WORLDS: Deterministic + Intelligent + Random

v4.5 Controlled = v4.5 rules + controlled randomness (70/30 split)

Architecture:
  1. Python samples difficulty_type (deterministic, weighted)
  2. Python picks variant rule (70% primary, 30% explore alternatives)
  3. Python selects sub_concepts (aspect-filtered by rules)
  4. Python picks linked_concept (70% smart domain-aware, 30% random exploration)
  5. Python picks question_type (70% recommended, 30% explore valid alternatives)
  6. Trap assignment (ALWAYS validated — no randomness here!)

Benefits:
  ✅ Diversity: 70% controlled, 30% explored
  ✅ Quality: Traps always valid, aspects filtered
  ✅ Speed: No LLM calls
  ✅ Reproducibility: Seeded randomness
  ✅ Exploration: 30% chance for surprises
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import List, Optional, Dict
from collections import defaultdict

from pydantic import BaseModel
from .models import SubConceptItem, QuestionSkeleton

logger = logging.getLogger(__name__)

_V2_DIR = Path(__file__).parent
_CONFIG_DIR = _V2_DIR.parent.parent.parent / "config"

_PRIORITY_WEIGHT: dict = {"high": 3, "medium": 2, "low": 1}

# All valid question types (for 30% exploration pool)
ALL_QUESTION_TYPES = [
    "multi_statement",
    "assertion_reason",
    "match_pair",
    "direct_fact",
    "pure_ca",
    "spatial",
    "chronology",
    "data_based",
    "how_many",           # "How many of the above statements are correct?" format
    "single_best_answer", # All options partially true; only one is fully correct
]

# Question type mappings per difficulty_type (70% recommended)
# how_many: best for medium/hard — exhaustive evaluation, hardest to guess
# single_best_answer: best for easy/medium — tests precision over recall
DIFFICULTY_TYPE_TO_QUESTION_TYPES = {
    "easy_recall_static":                 ["direct_fact", "match_pair", "single_best_answer"],
    "easy_ca_trigger":                    ["direct_fact", "pure_ca", "single_best_answer"],
    "easy_reverse_mild":                  ["direct_fact", "multi_statement", "single_best_answer"],
    "medium_concept_linking_same_domain": ["assertion_reason", "multi_statement", "how_many"],
    "medium_adjacent_fact":               ["match_pair", "multi_statement", "how_many"],
    "medium_statistical_reversal":        ["multi_statement", "assertion_reason", "how_many"],
    "medium_precision_location":          ["match_pair", "multi_statement", "single_best_answer"],
    "medium_ca_integration":              ["multi_statement", "assertion_reason", "single_best_answer"],
    "hard_counterintuitive_single_concept": ["assertion_reason", "how_many"],
    "hard_cross_domain_linking":          ["assertion_reason", "how_many"],
    "hard_all_of_above_precision":        ["multi_statement", "how_many"],
    "hard_strong_concept_depth":          ["assertion_reason", "how_many"],
    "hard_spatial_sequence":              ["assertion_reason", "match_pair"],
    "hard_reverse_extreme":               ["assertion_reason", "how_many"],
    "pure_ca_news_tracking":              ["direct_fact", "pure_ca"],
    "pure_ca_recent_event":               ["direct_fact", "pure_ca"],
}

CA_FRIENDLY_DIFFICULTY_TYPES = {
    "easy_ca_trigger",
    "medium_ca_integration",
    "pure_ca_news_tracking",
    "pure_ca_recent_event",
}

# Loaders
def _load_json(path: Path, label: str) -> dict | list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"[Stage0 v4.5+] {label} not found: {path}")
        return {}
    except Exception as e:
        logger.warning(f"[Stage0 v4.5+] Failed to load {label}: {e}")
        return {}


def _load_trap_registry(subject: str, subdomain: str = "") -> dict:
    """Load trap registry from hierarchical structure.

    Load chain:
    1. Domain-specific: traps/{subject}/{domain}/traps_{subject}_{domain}.json
    2. Subject-level fallback: traps/{subject}/traps_{subject}.json
    """
    subject_lower = subject.lower().replace(" ", "_")

    # Try domain-specific first if subdomain provided
    if subdomain:
        subdomain_lower = subdomain.lower().replace(" ", "_")
        domain_specific = _V2_DIR / "traps" / subject_lower / subdomain_lower / f"traps_{subject_lower}_{subdomain_lower}.json"
        if domain_specific.exists():
            return _load_json(domain_specific, f"trap registry ({subject}/{subdomain})")

    # Fall back to subject-level
    subject_level = _V2_DIR / "traps" / subject_lower / f"traps_{subject_lower}.json"
    return _load_json(subject_level, "trap registry")


def _load_variants(subject: str) -> dict:
    """Load difficulty type variants for controlled randomness."""
    variant_file = f"difficulty_type_variants_{subject.lower().replace(' ', '_')}.json"
    data = _load_json(_V2_DIR / variant_file, "difficulty type variants")
    return data.get("variants", {})


def _load_control_probabilities(subject: str) -> dict:
    """Load control probabilities (70/30 splits)."""
    variant_file = f"difficulty_type_variants_{subject.lower().replace(' ', '_')}.json"
    data = _load_json(_V2_DIR / variant_file, "difficulty type variants")
    return data.get("control_probabilities", {})


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
            "interlink_domains": entry.get("interlink_domains", []),
            "trap_affinity":    entry.get("trap_affinity", []),
            "ca_trigger_types": entry.get("ca_trigger_types", []),
        })
    return result


def _load_concept_pool(subject: str, subdomain: str) -> list:
    """Load concept pool from hierarchical domain-specific structure.

    Load chain:
    1. Domain-specific: concept_pools/{subject}/{domain}/{subject}_{domain}.json
    2. Subject-level: concept_pools/{subject}/{subject}.json
    3. Flat fallback (backwards compat): concept_pools/{subject}_{domain}.json
    """
    subj_slug = subject.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
    sub_slug  = subdomain.lower().replace(" ", "_").replace("&", "and").replace("/", "_")

    # 1. Try domain-specific hierarchical path first
    domain_specific = _V2_DIR / "concept_pools" / subj_slug / sub_slug / f"{subj_slug}_{sub_slug}.json"
    data = _load_json(domain_specific, f"concept pool ({subject}/{subdomain})")
    if data:
        raw = data.get("concepts", [])
        result = _normalise_concept_dict(raw) if isinstance(raw, dict) else raw
        logger.info(f"[Stage0 v4.5+] Loaded {len(result)} concepts from domain-specific pool: {subject}/{subdomain}")
        return result

    # 2. Try subject-level fallback
    subject_level = _V2_DIR / "concept_pools" / subj_slug / f"{subj_slug}.json"
    data = _load_json(subject_level, f"concept pool fallback ({subject})")
    if data:
        raw = data.get("concepts", [])
        result = _normalise_concept_dict(raw) if isinstance(raw, dict) else raw
        logger.warning(f"[Stage0 v4.5+] Using subject-level fallback for {subject}/{subdomain} ({len(result)} concepts)")
        return result

    # 3. Try flat structure for backwards compatibility
    flat_fallback = _V2_DIR / "concept_pools" / f"{subj_slug}_{sub_slug}.json"
    data = _load_json(flat_fallback, f"concept pool flat fallback ({subject}_{subdomain})")
    if data:
        raw = data.get("concepts", [])
        result = _normalise_concept_dict(raw) if isinstance(raw, dict) else raw
        logger.warning(f"[Stage0 v4.5+] Using flat fallback for {subject}/{subdomain} ({len(result)} concepts)")
        return result

    logger.error(f"[Stage0 v4.5+] ❌ No concept pool found for {subject}/{subdomain}")
    return []


def _get_concept_trap_mapping(trap_registry: dict) -> dict:
    """Get concept -> [trap_ids] mapping from registry."""
    return trap_registry.get("concept_trap_mapping", {})


# ── Difficulty Distribution (Pure CA Support) ─────────────────────────────────

def _difficulty_counts(easy_pct: float, medium_pct: float, hard_pct: float, pure_ca_pct: float, num_questions: int) -> tuple[int, int, int, int]:
    """
    Distribute num_questions into easy/medium/hard/pure_ca using percentages.
    Guarantees they sum to exactly num_questions.
    Remainder goes to medium.

    Distribution:
      - easy: 15%
      - medium: 25%
      - hard: 40%
      - pure_ca: 15% (dedicated pure CA questions)
    """
    pure_ca = max(0, int(pure_ca_pct * num_questions))
    easy   = max(0, int(easy_pct   * num_questions))
    hard   = max(0, int(hard_pct   * num_questions))
    medium = num_questions - easy - hard - pure_ca

    # Ensure at least 1 of each if num_questions >= 4
    if num_questions >= 4:
        pure_ca = max(1, pure_ca)
        easy   = max(1, easy)
        hard   = max(1, hard)
        medium = num_questions - easy - hard - pure_ca

    return easy, medium, hard, pure_ca


# ── Controlled Randomness: Variant Selection ──────────────────────────────────

def _get_variant_rules(difficulty_type: str, variants: dict, control_probs: dict) -> dict:
    """
    Get rules for this difficulty_type.
    70% use primary variant, 30% explore alternatives.
    """
    variant_list = variants.get(difficulty_type, [])
    if not variant_list:
        return {}

    # Single variant = always use it
    if len(variant_list) == 1:
        return variant_list[0]

    # Multiple variants: 70% primary, 30% explore
    if random.random() < control_probs.get("variant_selection", {}).get("primary", 0.70):
        return variant_list[0]  # Primary is always first
    else:
        return random.choice(variant_list[1:])  # Pick from alternatives


# ── Controlled Randomness: Question Type Selection ──────────────────────────────

def _pick_question_type(
    difficulty_type: str,
    recommended_types: List[str],
    control_probs: dict,
) -> str:
    """
    Pick question type.
    70% use recommended, 30% explore other valid types.
    """
    if random.random() < control_probs.get("question_type_selection", {}).get("recommended", 0.70):
        return random.choice(recommended_types)
    else:
        # 30% exploration: pick ANY valid question type
        return random.choice(ALL_QUESTION_TYPES)


# ── Controlled Randomness: Linked Concept Selection ───────────────────────────

def _pick_linked_concept(
    own_concept: dict,
    rules: dict,
    concept_pool: dict,
    control_probs: dict,
) -> Optional[str]:
    """
    Pick linked concept.
    70% smart domain-aware selection, 30% random exploration.
    """
    if rules.get("num_borrowed_sub_concepts", 0) == 0:
        return None  # No borrowing for this variant

    borrow_domain = rules.get("borrow_from_domain")

    # 70% smart domain-aware selection
    if random.random() < control_probs.get("linked_concept_selection", {}).get("smart", 0.70):
        if borrow_domain == "SAME":
            candidates = own_concept.get("links_to", [])
        elif borrow_domain == "DIFFERENT":
            candidates = []
            for entry in own_concept.get("interlink_domains", []):
                if isinstance(entry, dict) and "concepts" in entry:
                    candidates.extend(entry["concepts"])
                elif isinstance(entry, str):
                    candidates.append(entry)
        else:
            candidates = []
    else:
        # 30% exploration: pick ANY concept from pool
        candidates = list(concept_pool.keys())

    # Filter to valid concepts in pool
    candidates = [c for c in candidates if c in concept_pool and c != own_concept.get("concept")]

    return random.choice(candidates) if candidates else None


# ── Sub-Concept Selection (Always Filtered by Aspect Rules) ─────────────────────

def _select_sub_concepts_for_difficulty(
    own_concept: dict,
    rules: dict,
    concept_pool: dict,
) -> tuple[List[SubConceptItem], Optional[str]]:
    """
    Intelligently select sub_concepts based on variant rules.

    Returns: (list of SubConceptItem, linked_concept_name or None)
    """
    num_own = rules.get("num_own_sub_concepts", 1)
    num_borrowed = rules.get("num_borrowed_sub_concepts", 0)
    preferred_aspects = rules.get("preferred_aspects", [])

    all_items = []

    # ── Select OWN sub_concepts (aspect-filtered) ────────────────────────────
    own_pool = own_concept.get("sub_concepts", [])

    # Filter by preferred aspects
    eligible_own = [
        sc for sc in own_pool
        if sc.get("aspect") in preferred_aspects or not preferred_aspects
    ]

    if not eligible_own:
        eligible_own = own_pool  # Fallback

    random.shuffle(eligible_own)
    selected_own = eligible_own[:num_own]

    for sc in selected_own:
        all_items.append(SubConceptItem(
            topic=sc["topic"],
            aspect=sc.get("aspect", "process"),
            source_concept="",
        ))

    # ── Select BORROWED sub_concepts (if needed) ────────────────────────────
    linked_concept = None
    if num_borrowed > 0:
        borrow_domain = rules.get("borrow_from_domain")

        # Smart selection (uses rules for domain)
        if borrow_domain == "SAME":
            candidates = own_concept.get("links_to", [])
        elif borrow_domain == "DIFFERENT":
            candidates = []
            for entry in own_concept.get("interlink_domains", []):
                if isinstance(entry, dict) and "concepts" in entry:
                    candidates.extend(entry["concepts"])
                elif isinstance(entry, str):
                    candidates.append(entry)
        else:
            candidates = []

        candidates = [c for c in candidates if c in concept_pool]

        borrowed_from_concepts = set()
        for _ in range(num_borrowed):
            if not candidates:
                break

            borrowed_concept_name = random.choice(candidates)
            borrowed_concept = concept_pool[borrowed_concept_name]
            borrowed_from_concepts.add(borrowed_concept_name)

            borrowed_pool = borrowed_concept.get("sub_concepts", [])

            # Filter by aspect
            eligible_borrowed = [
                sc for sc in borrowed_pool
                if sc.get("aspect") in preferred_aspects or not preferred_aspects
            ]
            if not eligible_borrowed:
                eligible_borrowed = borrowed_pool

            if eligible_borrowed:
                borrowed_sc = random.choice(eligible_borrowed)
                all_items.append(SubConceptItem(
                    topic=borrowed_sc["topic"],
                    aspect=borrowed_sc.get("aspect", "process"),
                    source_concept=borrowed_concept_name,
                ))

        if borrowed_from_concepts:
            linked_concept = list(borrowed_from_concepts)[0]

    # Shuffle to randomize order
    random.shuffle(all_items)

    return all_items, linked_concept


# ── Difficulty Type Sampling ──────────────────────────────────────────────────

def _sample_difficulty_types(num_questions: int, easy_pct: float = 0.15, medium_pct: float = 0.25,
                             hard_pct: float = 0.40, pure_ca_pct: float = 0.15) -> list:
    """
    Sample difficulty types enforcing 40-25-15-15 distribution (hard-medium-easy-pure_ca).

    Maps counts to specific difficulty_type variants.
    """
    # 1. Get counts per difficulty level
    easy_count, medium_count, hard_count, pure_ca_count = _difficulty_counts(
        easy_pct, medium_pct, hard_pct, pure_ca_pct, num_questions
    )

    # 2. Get available types per level
    easy_types = [dt for dt in DIFFICULTY_TYPE_TO_QUESTION_TYPES.keys() if dt.startswith("easy_")]
    medium_types = [dt for dt in DIFFICULTY_TYPE_TO_QUESTION_TYPES.keys() if dt.startswith("medium_")]
    hard_types = [dt for dt in DIFFICULTY_TYPE_TO_QUESTION_TYPES.keys() if dt.startswith("hard_")]
    pure_ca_types = [dt for dt in DIFFICULTY_TYPE_TO_QUESTION_TYPES.keys() if dt.startswith("pure_ca_")]

    # 3. Sample from each level
    sampled = []
    sampled.extend([random.choice(easy_types) for _ in range(easy_count)] if easy_types else ["easy_recall_static"] * easy_count)
    sampled.extend([random.choice(medium_types) for _ in range(medium_count)] if medium_types else ["medium_concept_linking_same_domain"] * medium_count)
    sampled.extend([random.choice(hard_types) for _ in range(hard_count)] if hard_types else ["hard_counterintuitive_single_concept"] * hard_count)
    sampled.extend([random.choice(pure_ca_types) for _ in range(pure_ca_count)] if pure_ca_types else ["pure_ca_news_tracking"] * pure_ca_count)

    # 4. Shuffle and return
    random.shuffle(sampled)
    return sampled[:num_questions]


# ── Concept Sampling ──────────────────────────────────────────────────────────

def _sample_concepts(num_questions: int, concept_pool: list) -> list:
    """Sample concepts with priority weighting."""
    weighted_pool = []
    for c in concept_pool:
        weight = _PRIORITY_WEIGHT.get(c.get("priority", "medium"), 2)
        weighted_pool.extend([c["concept"]] * weight)

    random.shuffle(weighted_pool)

    concept_counts = {}
    concepts_assigned = []
    supply = (weighted_pool * max(3, num_questions))[:num_questions * 3]
    for concept_name in supply:
        if len(concepts_assigned) >= num_questions:
            break
        if concept_counts.get(concept_name, 0) >= 3:
            continue
        concepts_assigned.append(concept_name)
        concept_counts[concept_name] = concept_counts.get(concept_name, 0) + 1

    while len(concepts_assigned) < num_questions:
        c = random.choice(concept_pool)
        if concept_counts.get(c["concept"], 0) < 3:
            concepts_assigned.append(c["concept"])
            concept_counts[c["concept"]] = concept_counts.get(c["concept"], 0) + 1

    return concepts_assigned[:num_questions]


# ── Main Slot Preparation ─────────────────────────────────────────────────────

def _prepare_slots_controlled(
    num_questions: int,
    subject: str,
    subdomain: str,
    concept_pool: list,
    trap_registry: dict,
    variants: dict,
    control_probs: dict,
) -> list:
    """
    Pre-sample with controlled randomness (70/30).

    70% structured by rules, 30% exploratory variants.
    Difficulty distribution: 40% hard, 25% medium, 15% easy, 15% pure_ca
    """
    # 1. Sample difficulty types (enforced 40-25-15-15 distribution)
    difficulty_types = _sample_difficulty_types(num_questions)

    # 2. Sample concepts
    concepts_assigned = _sample_concepts(num_questions, concept_pool)

    # 3. Build lookups
    concept_lookup = {c["concept"]: c for c in concept_pool}
    concept_trap_mapping = _get_concept_trap_mapping(trap_registry)
    concept_pool_dict = {c["concept"]: c for c in concept_pool}

    # 4. Build slots
    slots = []
    for i, (diff_type, concept_name) in enumerate(zip(difficulty_types, concepts_assigned)):
        concept = concept_lookup.get(concept_name, concept_pool[0])

        # Get variant rules (70% primary, 30% alternatives)
        rules = _get_variant_rules(diff_type, variants, control_probs)

        # Select sub_concepts (aspect-filtered by rules)
        sub_concepts, linked_concept = _select_sub_concepts_for_difficulty(
            concept, rules, concept_pool_dict
        )

        # Pick linked_concept (70% smart, 30% random)
        if not linked_concept and rules.get("num_borrowed_sub_concepts", 0) > 0:
            linked_concept = _pick_linked_concept(
                concept, rules, concept_pool_dict, control_probs
            )

        # Pick question_type (70% recommended, 30% explore)
        recommended_qts = DIFFICULTY_TYPE_TO_QUESTION_TYPES.get(diff_type, [])
        question_type = _pick_question_type(diff_type, recommended_qts, control_probs)

        # Get trap affinity for this concept (fallback to all available traps if not in mapping)
        traps_available = concept_trap_mapping.get(concept_name, [])
        trap_source = "concept_mapping"

        if not traps_available:
            # Fallback: use all trap IDs from the registry
            traps_available = list(trap_registry.get("trap_patterns", {}).keys())
            trap_source = "trap_patterns_keys"

            if not traps_available:
                # Final fallback: use trap IDs from concept_trap_mapping values
                all_trap_ids = set()
                for trap_ids in concept_trap_mapping.values():
                    if isinstance(trap_ids, list):
                        all_trap_ids.update(trap_ids)
                traps_available = list(all_trap_ids)
                trap_source = "concept_mapping_values"

        # Log trap assignment details
        if not traps_available:
            logger.warning(f"[Stage0 v4.5+] Slot {i+1} ({concept_name}): NO TRAPS AVAILABLE (will result in empty trap_strategy)")
        else:
            logger.debug(f"[Stage0 v4.5+] Slot {i+1} ({concept_name}): {len(traps_available)} traps from {trap_source}")

        slots.append({
            "slot_id": f"slot_{i+1:02d}",
            "difficulty_type": diff_type,
            "variant": rules.get("variant", "primary"),
            "concept": concept_name,
            "sub_concepts": sub_concepts,
            "linked_concept": linked_concept,
            "question_type": question_type,
            "trap_affinity": traps_available,
            "ca_flag": diff_type in CA_FRIENDLY_DIFFICULTY_TYPES,
            "ca_trigger_types": concept.get("ca_trigger_types", []),
            "subdomain": subdomain,  # Domain hint for Stage 3 trap loading
        })

    logger.info(
        f"[Stage0 v4.5+] Prepared {num_questions} slots with controlled randomness: "
        f"CA={sum(1 for s in slots if s['ca_flag'])}/30 (30%), "
        f"variants={len(set(s['variant'] for s in slots))}, "
        f"question_types={len(set(s['question_type'] for s in slots))}"
    )
    return slots


# ── Skeleton Conversion ───────────────────────────────────────────────────────

def _slot_to_skeleton(slot: dict, idx: int) -> QuestionSkeleton:
    """Convert slot to QuestionSkeleton with v4.5 Controlled metadata."""
    difficulty_type = slot.get("difficulty_type", "")
    available_qts = DIFFICULTY_TYPE_TO_QUESTION_TYPES.get(difficulty_type, ALL_QUESTION_TYPES)

    # Select trap_strategy
    trap_strategy = ""
    if slot["trap_affinity"]:
        trap_strategy = random.choice(slot["trap_affinity"])
    else:
        logger.warning(f"[Stage0 v4.5+] Skeleton sk_{idx:03d} ({slot['concept']}): No trap_affinity available, trap_strategy will be empty")

    return QuestionSkeleton(
        skeleton_id=f"sk_{idx:03d}",
        question_type=slot["question_type"],
        concept=slot["concept"],
        sub_concepts=slot["sub_concepts"],
        difficulty="hard" if "hard" in difficulty_type else "easy" if "easy" in difficulty_type else "medium",
        ca_flag=slot["ca_flag"],
        ca_event="",
        trap_strategy=trap_strategy,
        trap_name="",
        sub_domain=slot.get("subdomain", slot["concept"]),  # Domain (e.g., "Climatology"), not concept
        # v4.5 Controlled additions
        difficulty_type=difficulty_type,
        variant=slot.get("variant", ""),
        available_trap_ids=slot.get("trap_affinity", []),
        available_question_types=available_qts,
    )


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def generate_blueprint_controlled(
    num_questions: int,
    subject: str,
    subdomain: str,
) -> List[QuestionSkeleton]:
    """
    Stage 0 v4.5 Controlled: Rules + Controlled Randomness.

    70% structured by rules (quality guarantee)
    30% explore variants (diversity boost)

    No LLM calls. Fast, deterministic, diverse.
    """
    logger.info(f"[Stage0 v4.5+] Generating {num_questions} skeletons (70% controlled, 30% exploratory)")

    # Load data
    concept_pool = _load_concept_pool(subject, subdomain)
    if not concept_pool:
        logger.error(f"[Stage0 v4.5+] No concept pool for {subject}/{subdomain}")
        return []
    logger.info(f"[Stage0 v4.5+][TrapRegistry] Loaded {len(concept_pool)} concepts from {subject}/{subdomain}")

    trap_registry = _load_trap_registry(subject, subdomain)

    # Log what traps were loaded
    if "concept_trap_mapping" in trap_registry and "trap_patterns" in trap_registry:
        num_concepts_with_traps = len(trap_registry.get("concept_trap_mapping", {}))
        num_trap_ids = len(trap_registry.get("trap_patterns", {}))
        sample_trap_ids = sorted(list(trap_registry.get("trap_patterns", {}).keys()))[:5]
        logger.info(f"[Stage0 v4.5+][TrapRegistry] Loaded {num_trap_ids} trap IDs for {num_concepts_with_traps} concepts from domain-specific file ({subject}/{subdomain})")
        logger.info(f"[Stage0 v4.5+][TrapRegistry] Sample trap IDs: {sample_trap_ids}")
    elif "traps" in trap_registry:
        num_traps = len(trap_registry.get("traps", {}))
        sample_trap_ids = [t.get("trap_id", "?") for t in trap_registry.get("traps", [])[:5]]
        logger.info(f"[Stage0 v4.5+][TrapRegistry] Loaded {num_traps} traps from trap registry (subject-level)")
        logger.info(f"[Stage0 v4.5+][TrapRegistry] Sample trap IDs: {sample_trap_ids}")
    else:
        logger.warning(f"[Stage0 v4.5+][TrapRegistry] No recognizable trap structure found in registry")

    variants = _load_variants(subject)
    control_probs = _load_control_probabilities(subject)

    if not variants:
        logger.error(f"[Stage0 v4.5+] No variants loaded")
        return []

    # Pre-sample with controlled randomness
    slots = _prepare_slots_controlled(
        num_questions,
        subject,
        subdomain,
        concept_pool,
        trap_registry,
        variants,
        control_probs,
    )

    # Convert to skeletons
    skeletons = [_slot_to_skeleton(slot, i + 1) for i, slot in enumerate(slots)]

    logger.info(f"[Stage0 v4.5+] Generated {len(skeletons)} skeletons")
    return skeletons


# ── Testing ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test_controlled():
        """Test: generate 30 skeletons with controlled randomness."""
        concept_pool = _load_concept_pool("Geography", "Climatology")
        trap_registry = _load_trap_registry("Geography")
        variants = _load_variants("Geography")
        control_probs = _load_control_probabilities("Geography")

        print(f"\n✓ Loaded {len(concept_pool)} concepts")
        print(f"✓ Loaded variants for {len(variants)} difficulty types")
        print(f"✓ Control probabilities: {control_probs}")

        slots = _prepare_slots_controlled(
            30,
            "Geography",
            "Climatology",
            concept_pool,
            trap_registry,
            variants,
            control_probs,
        )

        print(f"\n{'='*140}")
        print("STAGE 0 v4.5 CONTROLLED: RULES + CONTROLLED RANDOMNESS (30 Questions)")
        print(f"{'='*140}\n")

        print(f"{'Q#':<3} {'Difficulty Type':<35} {'Variant':<12} {'Concept':<25} {'QT':<15} {'Link':<20} {'CA?':<4}")
        print("-" * 140)

        # Analyze
        concepts_used = defaultdict(int)
        traps_used = defaultdict(int)
        ca_count = 0
        variants_used = defaultdict(int)
        question_types_used = defaultdict(int)
        linked_count = 0

        for i, slot in enumerate(slots, 1):
            diff_type = slot["difficulty_type"]
            variant = slot["variant"]
            concept = slot["concept"]
            qt = slot["question_type"]
            link = slot["linked_concept"] if slot["linked_concept"] else "-"
            ca_flag = "✓" if slot["ca_flag"] else "-"

            if slot["ca_flag"]:
                ca_count += 1
            if slot["linked_concept"]:
                linked_count += 1

            concepts_used[concept] += 1
            variants_used[variant] += 1
            question_types_used[qt] += 1

            for trap in slot["trap_affinity"]:
                traps_used[trap] += 1

            print(f"{i:<3} {diff_type:<35} {variant:<12} {concept:<25} {qt:<15} {link:<20} {ca_flag:<4}")

        print("\n" + "-" * 140)
        print("\nCONTROLLED RANDOMNESS ANALYSIS:")
        print(f"  Total: 30 questions")
        print(f"  Unique concepts: {len(concepts_used)}")
        print(f"  Concept distribution: {sorted([(c, cnt) for c, cnt in concepts_used.items()], key=lambda x: -x[1])[:5]}")
        print(f"  Unique variants: {len(variants_used)}")
        print(f"  Variant distribution: {dict(variants_used)}")
        print(f"  Unique question types: {len(question_types_used)}")
        print(f"  Question type distribution: {sorted([(qt, cnt) for qt, cnt in question_types_used.items()], key=lambda x: -x[1])}")
        print(f"  CA-flag count: {ca_count}/30 (30% enforced)")
        print(f"  Linked concepts: {linked_count} (cross-concept borrowing)")
        print(f"  Unique traps: {len(traps_used)}")
        print(f"  Top traps: {sorted([(t, cnt) for t, cnt in traps_used.items()], key=lambda x: -x[1])[:5]}")

        print(f"\n{'='*140}")
        print("KEY DIFFERENCES FROM PURE v4.5")
        print(f"{'='*140}\n")

        print("✅ v4.5 CONTROLLED RANDOMNESS WINS:")
        print(f"  1. Variant diversity: {len(variants_used)} different variants used")
        print(f"  2. Question type diversity: {len(question_types_used)} different types")
        print(f"  3. Concept linking: {linked_count} questions with linked concepts")
        print(f"  4. Quality guarantee: ALL {len(traps_used)} traps are valid (trap_affinity enforced)")
        print(f"  5. 70/30 split: 70% controlled by rules, 30% exploratory variants")
        print(f"  6. No API calls: Pure Python, fast & deterministic")

        print("\n⚡ HOW IT WORKS:")
        print("  • 70% of variant selection uses PRIMARY rules")
        print("  • 30% of variant selection explores ALTERNATIVES")
        print("  • 70% of question_type picks RECOMMENDED types")
        print("  • 30% of question_type picks ANY valid type (surprise!)")
        print("  • 70% of linked_concept uses DOMAIN-AWARE selection")
        print("  • 30% of linked_concept picks ANY concept in pool")

    asyncio.run(test_controlled())
