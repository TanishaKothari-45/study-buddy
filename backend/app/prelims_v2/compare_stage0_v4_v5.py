"""
Comparison: Stage 0 v4 vs v5 — 30 Questions from Climatology

Compare outputs on:
  1. Sub-concept diversity (how many unique sub_concepts appear?)
  2. Trap coverage (trap distribution, are they used well?)
  3. Inter-domain linking (how many questions link 2+ domains?)
  4. CA integration (% with ca_flag=true)
  5. Concept coverage (how many unique concepts appear?)
"""

import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.prelims_v2.stage0_blueprint_v5 import (
    _load_concept_pool,
    _load_trap_registry,
    _load_difficulty_types,
    _prepare_slots,
    _get_concept_trap_mapping,
    _sample_difficulty_types,
    _sample_concepts,
)

def test_v5_structure():
    """Test v5: produce 30 skeletons showing structural decisions."""
    print("\n" + "="*100)
    print("STAGE 0 v5: STRUCTURAL SAMPLING (30 Questions)")
    print("="*100 + "\n")

    # Load data
    concept_pool = _load_concept_pool("Geography", "Climatology")
    trap_registry = _load_trap_registry("Geography")
    difficulty_types_taxonomy = _load_difficulty_types("Geography", "Climatology")

    # Prepare 30 slots
    slots = _prepare_slots(
        30,
        "Geography",
        "Climatology",
        concept_pool,
        trap_registry,
        difficulty_types_taxonomy,
    )

    print(f"{'Q#':<3} {'Difficulty Type':<35} {'Concept':<25} {'Traps':<20} {'CA?':<4}")
    print("-" * 100)

    # Analyze
    concepts_used = Counter()
    traps_used = Counter()
    ca_count = 0
    linking_count = 0
    difficulty_distribution = Counter()

    for i, slot in enumerate(slots, 1):
        diff_type = slot["difficulty_type"]
        concept = slot["concept"]
        traps = ", ".join(slot["trap_affinity"][:2]) if slot["trap_affinity"] else "none"

        # Determine if this difficulty type expects linking
        from app.prelims_v2.stage0_blueprint_v5 import DIFFICULTY_TYPES_THAT_LINK, CA_FRIENDLY_DIFFICULTY_TYPES
        should_link = diff_type in DIFFICULTY_TYPES_THAT_LINK
        should_ca = diff_type in CA_FRIENDLY_DIFFICULTY_TYPES

        ca_flag = "✓" if (should_ca and slot["ca_connectable_overall"]) else "-"
        if ca_flag == "✓":
            ca_count += 1

        if should_link and slot["links_to"]:
            linking_count += 1

        concepts_used[concept] += 1
        for trap in slot["trap_affinity"]:
            traps_used[trap] += 1

        category = "EASY" if "easy" in diff_type else "MEDIUM" if "medium" in diff_type else "HARD" if "hard" in diff_type else "CA"
        difficulty_distribution[category] += 1

        print(f"{i:<3} {diff_type:<35} {concept:<25} {traps:<20} {ca_flag:<4}")

    print("\n" + "-" * 100)
    print("\nV5 ANALYSIS:")
    print(f"  Total questions: 30")
    print(f"  Unique concepts: {len(concepts_used)}")
    print(f"  Concepts used: {sorted([(c, cnt) for c, cnt in concepts_used.items()], key=lambda x: -x[1])[:5]}")
    print(f"  Total unique traps used: {len(traps_used)}")
    print(f"  Most used traps: {sorted([(t, cnt) for t, cnt in traps_used.items()], key=lambda x: -x[1])[:5]}")
    print(f"  CA-flag true count: {ca_count} ({ca_count/30*100:.1f}%)")
    print(f"  Linking opportunity count: {linking_count}")
    print(f"  Difficulty distribution: {dict(difficulty_distribution)}")
    print(f"  Question type enforcement: ENFORCED (LLM receives allowed types per difficulty_type)")

    return {
        "version": "v5",
        "total": 30,
        "unique_concepts": len(concepts_used),
        "unique_traps": len(traps_used),
        "ca_count": ca_count,
        "ca_pct": ca_count/30*100,
        "linking_count": linking_count,
        "concepts_distribution": dict(concepts_used),
        "traps_distribution": dict(traps_used),
        "difficulty_distribution": dict(difficulty_distribution),
    }


def test_v4_structure():
    """Test v4: produce 30 skeletons (old pre-sampling method)."""
    print("\n" + "="*100)
    print("STAGE 0 v4: LEGACY PRE-SAMPLING (30 Questions)")
    print("="*100 + "\n")

    # Import v4 (if it still exists, use old hard-coded logic)
    from app.prelims_v2.stage0_blueprint import (
        _load_concept_pool as _load_pool_v4,
        _load_trap_registry as _load_trap_v4,
        _pre_sample_slots as _pre_sample_v4,
        get_subject_config,
    )

    # Load
    cfg = get_subject_config("Geography")
    concept_pool_v4 = _load_pool_v4("Geography", "Climatology")
    trap_registry_v4 = _load_trap_v4(cfg)

    # Pre-sample 30 slots
    slots_v4 = _pre_sample_v4(cfg, 30, concept_pool_v4, trap_registry_v4, None)

    print(f"{'Q#':<3} {'Difficulty':<12} {'Concept':<25} {'Sub-concepts':<35} {'Trap':<15} {'CA?':<4}")
    print("-" * 100)

    # Analyze
    concepts_used = Counter()
    traps_used = Counter()
    ca_count = 0
    sub_concept_topics = Counter()
    difficulty_distribution = Counter()
    interdomain_links = 0

    for i, slot in enumerate(slots_v4, 1):
        difficulty = slot["difficulty"]
        concept = slot["concept"]
        trap_id = slot["trap_id"]
        ca_linked = slot["ca_linked"]

        # Analyze sub_concepts
        sub_concepts_str = ""
        source_concepts = set()
        for sc in slot["sub_concepts"]:
            sub_concepts_str += sc.topic[:20] + " "
            sub_concept_topics[sc.topic[:20]] += 1
            if sc.source_concept:
                source_concepts.add(sc.source_concept)
                interdomain_links += 1

        ca_flag = "✓" if ca_linked else "-"
        if ca_linked:
            ca_count += 1

        concepts_used[concept] += 1
        if trap_id:
            traps_used[trap_id] += 1

        difficulty_distribution[difficulty.upper()] += 1

        print(f"{i:<3} {difficulty:<12} {concept:<25} {sub_concepts_str[:35]:<35} {trap_id:<15} {ca_flag:<4}")

    print("\n" + "-" * 100)
    print("\nV4 ANALYSIS:")
    print(f"  Total questions: 30")
    print(f"  Unique concepts: {len(concepts_used)}")
    print(f"  Concepts used: {sorted([(c, cnt) for c, cnt in concepts_used.items()], key=lambda x: -x[1])[:5]}")
    print(f"  Unique sub-concept topics: {len(sub_concept_topics)}")
    print(f"  Sub-concepts used: {sorted([(s, cnt) for s, cnt in sub_concept_topics.items()], key=lambda x: -x[1])[:5]}")
    print(f"  Total unique traps used: {len(traps_used)}")
    print(f"  Most used traps: {sorted([(t, cnt) for t, cnt in traps_used.items()], key=lambda x: -x[1])[:5]}")
    print(f"  CA-flag true count: {ca_count} ({ca_count/30*100:.1f}%)")
    print(f"  Inter-domain links detected: {interdomain_links} (based on source_concept field)")
    print(f"  Difficulty distribution: {dict(difficulty_distribution)}")
    print(f"  Question type enforcement: LOOSE (LLM chose freely)")

    return {
        "version": "v4",
        "total": 30,
        "unique_concepts": len(concepts_used),
        "unique_traps": len(traps_used),
        "unique_sub_concepts": len(sub_concept_topics),
        "ca_count": ca_count,
        "ca_pct": ca_count/30*100,
        "interdomain_links": interdomain_links,
        "concepts_distribution": dict(concepts_used),
        "traps_distribution": dict(traps_used),
        "sub_concepts_distribution": dict(sub_concept_topics),
        "difficulty_distribution": dict(difficulty_distribution),
    }


def compare(v4_stats, v5_stats):
    """Compare v4 vs v5 on key metrics."""
    print("\n" + "="*100)
    print("COMPARISON: v4 vs v5")
    print("="*100 + "\n")

    metrics = [
        ("CA Integration", "ca_pct", "%", lambda v4, v5: v5 > v4),
        ("Unique Concepts Used", "unique_concepts", "count", lambda v4, v5: v5 >= v4),
        ("Unique Traps Used", "unique_traps", "count", lambda v4, v5: v5 >= v4),
        ("Unique Sub-concepts (v4 only)", "unique_sub_concepts", "count", lambda v4, v5: True),
    ]

    print(f"{'Metric':<35} {'v4':<15} {'v5':<15} {'Better':<10}")
    print("-" * 75)

    for metric_name, key, unit, winner_fn in metrics:
        v4_val = v4_stats.get(key, 0)
        v5_val = v5_stats.get(key, 0)

        if key == "unique_sub_concepts":
            print(f"{metric_name:<35} {v4_val:<15} {'N/A':<15} {'v4 (LLM chose)':<10}")
        else:
            better = "v5" if winner_fn(v4_val, v5_val) else "v4" if v4_val > v5_val else "tie"
            if unit == "%":
                print(f"{metric_name:<35} {v4_val:<14.1f}% {v5_val:<14.1f}% {better:<10}")
            else:
                print(f"{metric_name:<35} {v4_val:<15} {v5_val:<15} {better:<10}")

    print("\n" + "-" * 75)
    print("\nQUALITATIVE DIFFERENCES:")
    print("\nv4 Strengths:")
    print("  ✓ Sub-concept diversity: LLM freely picked from any concept")
    print("  ✓ Question type freedom: LLM could choose any type (less constrained)")
    print(f"  ✓ Generated {v4_stats['unique_sub_concepts']} unique sub-concept topics")
    print("\nv4 Weaknesses:")
    print("  ✗ No difficulty_type differentiation (just easy/medium/hard)")
    print("  ✗ Pre-sampling could repeat same sub_concepts")
    print("  ✗ LLM lazy: tended toward easy question types")
    print(f"  ✗ Only {v4_stats['ca_pct']:.1f}% CA integration (target: 30%)")

    print("\nv5 Strengths:")
    print("  ✓ 15 specific difficulty types (ensures question diversity)")
    print("  ✓ Question type enforced per difficulty (hard→assertion_reason, easy→direct_fact)")
    print("  ✓ Trap affinity matched to concept (no invalid trap-concept pairs)")
    print(f"  ✓ {v5_stats['ca_pct']:.1f}% CA integration (better targeting)")
    print("  ✓ Clear linking expectations (LLM knows when to link)")

    print("\nv5 Trade-offs:")
    print("  ⚠ Sub-concept selection delegated to LLM (need prompt quality)")
    print(f"  ⚠ Only {v5_stats['unique_concepts']} unique concepts (not higher diversity)")
    print("  ⚠ Requires Stage 0 LLM call (more expensive than Python sampling)")

    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100 + "\n")
    print("v5 is BETTER for question structure but needs:")
    print("  1. Ensure CA_FRIENDLY_DIFFICULTY_TYPES hit 30% target by sampling percentages")
    print("  2. Stage 0 LLM prompt must guide sub_concept selection well")
    print("  3. Monitor: does LLM consistently pick good sub_concepts?")
    print("\nNext step: Run full pipeline (Stage 0→1→3) and compare actual question quality")


if __name__ == "__main__":
    v4_stats = test_v4_structure()
    v5_stats = test_v5_structure()
    compare(v4_stats, v5_stats)
