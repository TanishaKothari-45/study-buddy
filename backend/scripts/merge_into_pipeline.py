#!/usr/bin/env python3
"""
merge_into_pipeline.py

Merges PYQ analysis results from /analyze-pyq-discovery skill into the prelims pipeline.

Usage:
  python3 merge_into_pipeline.py \
    --subject "Geography" \
    --domain "Oceanography" \
    --research-dir "config/research/2026-04-03_1530_Geography_Oceanography/"

  # Run only interlink update (e.g. after manually writing a concept pool):
  python3 merge_into_pipeline.py \
    --subject "Geography" \
    --domain "Natural Disasters" \
    --interlinks-only

Operations:
1. Create/Update concept_pools/geography_{domain}.json
2. Update traps_geography.json (shared, add new patterns)
3. Create traps_geography_{domain}.json (domain-specific)
4. Update difficulty_types_geography_base.json (add percentage_in_{domain} fields)
5. Update interlink_domains across ALL concept pool files for the new domain
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Paths relative to repo root
PRELIMS_DIR = Path(__file__).parent.parent / "app" / "prelims_v2"
CONCEPT_POOLS_DIR = PRELIMS_DIR / "concept_pools"


def load_json(path):
    """Load JSON file, return dict or None if not found."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    """Save dict as JSON with pretty formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  ✓ Wrote {path}")


def domain_to_snake_case(domain):
    """Convert domain name to snake_case."""
    return domain.lower().replace(" ", "_").replace("&", "and")


def operation_1_merge_concepts(subject, domain, research_dir):
    """Create/Update concept_pools/{subject_lower}_{domain}.json"""
    print(f"\nOperation 1: Merge concept pool")

    research_concepts_file = Path(research_dir) / f"concepts_discovered_{subject}_{domain}_*.json"
    research_concepts_file = list(Path(research_dir).glob(f"concepts_discovered_{subject}_{domain}_*.json"))[0]

    if not research_concepts_file.exists():
        print(f"  ✗ No concepts_discovered file found in {research_dir}")
        return {"added": 0, "merged": 0, "skipped": 0}

    research_concepts = load_json(research_concepts_file)

    # Target pool file
    domain_lower = domain_to_snake_case(domain)
    subject_lower = subject.lower()
    pool_file = CONCEPT_POOLS_DIR / f"{subject_lower}_{domain_lower}.json"

    # Load existing pool or create template
    if pool_file.exists():
        pool = load_json(pool_file)
        print(f"  Found existing pool at {pool_file.name}")
        added = 0
        merged = 0
    else:
        # Create from template
        template = load_json(CONCEPT_POOLS_DIR / f"{subject_lower}_climatology.json")
        if not template:
            print(f"  ✗ Cannot find template file {subject_lower}_climatology.json")
            return {"added": 0, "merged": 0, "skipped": 0}

        pool = {
            "subject": template["subject"],
            "domain": template["domain"],
            "subdomain": domain,
            "description": f"Concept pool for UPSC Prelims — {subject} > {domain}. Derived from PYQ analysis {datetime.now().strftime('%Y-%m-%d')}.",
            "core_concepts": [],
            "concepts": {}
        }
        added = 0
        merged = 0
        print(f"  Creating new pool template for {subject} > {domain}")

    # Process discovered concepts
    for concept_data in research_concepts:
        concept_name = concept_data.get("primary_concept", "")
        sub_concepts_from_research = concept_data.get("sub_concepts", [])
        ca_involved = concept_data.get("ca_involved", False)
        concept_category = concept_data.get("concept_category", "medium")

        if not concept_name:
            continue

        # Determine priority based on category
        priority_map = {
            "frequently_tested": "high",
            "core": "high",
            "medium": "medium",
            "niche": "low"
        }
        priority = priority_map.get(concept_category, "medium")

        if concept_name not in pool["concepts"]:
            # NEW CONCEPT
            pool["concepts"][concept_name] = {
                "priority": priority,
                "tested_as_question_types": [],
                "sub_concepts": []
            }

            # Add to core_concepts if not there
            if concept_name not in pool["core_concepts"]:
                pool["core_concepts"].append(concept_name)

            added += 1
        else:
            # EXISTING CONCEPT: merge sub_concepts
            existing = pool["concepts"][concept_name]
            existing_topics = {sc.get("topic") for sc in existing.get("sub_concepts", [])}

            for sub_concept_name in sub_concepts_from_research:
                if sub_concept_name not in existing_topics:
                    # NEW sub_concept
                    pool["concepts"][concept_name]["sub_concepts"].append({
                        "topic": sub_concept_name,
                        "aspects": [],
                        "ca_connectable": ca_involved,
                        "linked_to": []
                    })
                    merged += 1

            # Upgrade priority if needed
            if priority == "high" and existing["priority"] != "high":
                existing["priority"] = priority

    save_json(pool_file, pool)
    return {"added": added, "merged": merged, "skipped": 0}


def operation_2_update_shared_traps(subject, domain, research_dir):
    """Update traps_{subject_lower}.json with new patterns (avoid duplicates)"""
    print(f"\nOperation 2: Update shared traps file")

    # Load research trap patterns
    research_traps_file = list(Path(research_dir).glob(f"trap_patterns_discovered_{subject}_{domain}_*.json"))
    if not research_traps_file:
        print(f"  ✗ No trap_patterns_discovered file found")
        return {"added": 0, "skipped": 0}

    research_traps = load_json(research_traps_file[0])

    # Load shared traps file
    subject_lower = subject.lower()
    shared_traps_file = PRELIMS_DIR / f"traps_{subject_lower}.json"

    if not shared_traps_file.exists():
        print(f"  ✗ Shared traps file not found: {shared_traps_file}")
        return {"added": 0, "skipped": 0}

    shared_traps = load_json(shared_traps_file)
    added = 0
    skipped = 0

    # Collect all existing pattern names
    existing_pattern_names = set()
    for question_type, qt_data in shared_traps.get("question_types", {}).items():
        for pattern in qt_data.get("trap_patterns", []):
            existing_pattern_names.add(pattern.get("name", ""))

    # Process discovered traps
    for trap_data in research_traps:
        trap_name = trap_data.get("trap_mechanism", "")
        question_type = trap_data.get("question_type", "how_many")

        if not trap_name:
            continue

        if trap_name in existing_pattern_names:
            skipped += 1
            continue

        # Check if question_type exists in shared_traps
        if question_type not in shared_traps["question_types"]:
            shared_traps["question_types"][question_type] = {
                "description": "",
                "characteristics": "",
                "frequency_in_geography": 0.0,
                "difficulty_distribution": {"easy": 0.0, "medium": 0.5, "hard": 0.5},
                "trap_patterns": []
            }

        # Add new pattern
        new_pattern = {
            "pattern_id": f"pattern_{len(shared_traps['question_types'][question_type]['trap_patterns']) + 1}",
            "name": trap_name,
            "frequency": trap_data.get("frequency", 0.10),
            "mechanism": trap_data.get("trap_mechanism", ""),
            "error_type": trap_data.get("error_type", ""),
            "distractor_strategy": trap_data.get("distractor_strategy", ""),
            "generation_rules": [],
            "applicable_sub_domains": [domain]
        }

        shared_traps["question_types"][question_type]["trap_patterns"].append(new_pattern)
        added += 1

    save_json(shared_traps_file, shared_traps)
    return {"added": added, "skipped": skipped}


def operation_3_create_domain_traps(subject, domain, research_dir):
    """Create traps_{subject_lower}_{domain_lower}.json"""
    print(f"\nOperation 3: Create domain-specific traps file")

    research_traps_file = list(Path(research_dir).glob(f"trap_patterns_discovered_{subject}_{domain}_*.json"))
    if not research_traps_file:
        print(f"  ✗ No trap_patterns_discovered file found")
        return False

    research_traps = load_json(research_traps_file[0])

    # Load template
    subject_lower = subject.lower()
    template = load_json(PRELIMS_DIR / f"traps_{subject_lower}_climatology.json")

    if not template:
        print(f"  ✗ Cannot find template: traps_{subject_lower}_climatology.json")
        return False

    domain_lower = domain_to_snake_case(domain)

    # Create domain-specific file
    domain_traps = {
        "subject": template["subject"],
        "subdomain": domain,
        "description": f"UPSC Prelims {domain}-specific trap patterns. Derived from PYQ analysis {datetime.now().strftime('%Y-%m-%d')}.",
        "concept_trap_mapping": {},
        "trap_patterns": {}
    }

    # Build concept_trap_mapping from research concepts
    concepts_file = list(Path(research_dir).glob(f"concepts_discovered_{subject}_{domain}_*.json"))
    if concepts_file:
        research_concepts = load_json(concepts_file[0])
        for concept_data in research_concepts:
            concept = concept_data.get("primary_concept")
            if concept:
                domain_traps["concept_trap_mapping"][concept] = []

    # Add traps to domain file
    for trap_data in research_traps:
        trap_name = trap_data.get("trap_mechanism", "")
        if trap_name:
            pattern_id = f"{subject_lower[0:3].upper()}{domain_lower[0].upper()}T{len(domain_traps['trap_patterns']) + 1:02d}"
            domain_traps["trap_patterns"][pattern_id] = {
                "pattern_id": pattern_id,
                "name": trap_name,
                "category": trap_data.get("error_type", ""),
                "frequency": trap_data.get("frequency", 0.10),
                "difficulty": trap_data.get("difficulty", "medium"),
                "mechanism": trap_data.get("trap_mechanism", ""),
                "error_type": trap_data.get("error_type", ""),
                "distractor_strategy": trap_data.get("distractor_strategy", "")
            }

    target_file = PRELIMS_DIR / f"traps_{subject_lower}_{domain_lower}.json"
    save_json(target_file, domain_traps)
    return True


def operation_4_update_difficulty_types(subject, domain, research_dir):
    """Update difficulty_types_{subject_lower}_base.json with percentage_in_{domain} fields"""
    print(f"\nOperation 4: Update difficulty types percentages")

    # Load research difficulty drivers
    difficulty_file = list(Path(research_dir).glob(f"difficulty_drivers_{subject}_{domain}_*.json"))
    if not difficulty_file:
        print(f"  ✗ No difficulty_drivers file found")
        return 0

    research_difficulty = load_json(difficulty_file[0])

    # Load base difficulty types
    subject_lower = subject.lower()
    difficulty_types_file = PRELIMS_DIR / f"difficulty_types_{subject_lower}_base.json"

    if not difficulty_types_file.exists():
        print(f"  ✗ Difficulty types file not found: {difficulty_types_file}")
        return 0

    difficulty_types = load_json(difficulty_types_file)
    domain_snake = domain_to_snake_case(domain)

    updated = 0

    # Extract difficulty type percentages from research output
    # Assuming research_difficulty has structure like:
    # { "hard": { "hard_counterintuitive_single_concept": 0.40, ... }, ... }
    difficulty_distribution = research_difficulty.get("difficulty_type_distribution", {})

    for difficulty_type_name, difficulty_type_data in difficulty_types.get("difficulty_types", {}).items():
        # Try to find percentage in research output
        category = difficulty_type_data.get("category", "").lower()

        # Look for this type in research output
        for cat_key, cat_types in difficulty_distribution.items():
            if difficulty_type_name in cat_types:
                percentage = cat_types[difficulty_type_name]
                field_name = f"percentage_in_{domain_snake}"

                if field_name not in difficulty_type_data:
                    difficulty_type_data[field_name] = percentage
                    updated += 1
                break

    if updated > 0:
        save_json(difficulty_types_file, difficulty_types)

    return updated


_STOPWORDS = {
    "and", "the", "of", "in", "for", "with", "from", "its", "are",
    "that", "this", "all", "any", "both", "each", "their", "into",
    "more", "than", "when", "where", "also", "very", "over", "some",
    "type", "types", "kind", "kinds", "form", "forms", "other",
    "between", "through", "under", "above", "below", "world", "india",
}
_MIN_TOKEN_LEN = 5


def _concept_tokens(concept_name: str, sub_concepts: list | None = None) -> set[str]:
    """
    Extract meaningful tokens from a concept name and optionally its sub_concept topics.
    Used to detect semantic overlap between concepts across different domain pools.
    """
    text = concept_name
    if sub_concepts:
        for sc in sub_concepts:
            text += " " + sc.get("topic", "")
    tokens: set[str] = set()
    for word in text.lower().replace("&", " ").replace("/", " ").replace("-", " ").split():
        word = word.strip("(),.'\"")
        if len(word) >= _MIN_TOKEN_LEN and word not in _STOPWORDS:
            tokens.add(word)
    return tokens


def _normalize_interlink_domains(raw: list) -> list:
    """
    Normalise interlink_domains to a list of dicts: [{domain, concepts[]}].
    Handles: list of strings, list of dicts, or mixed.
    """
    result = []
    for entry in raw:
        if isinstance(entry, str):
            result.append({"domain": entry, "concepts": []})
        elif isinstance(entry, dict):
            result.append(entry)
    return result


def _upsert_interlink(concept_data: dict, domain_name: str, concept_list: list[str]) -> bool:
    """
    Add or merge an interlink_domains entry {domain, concepts} into concept_data.
    Returns True if the concept_data was modified.
    """
    raw = concept_data.get("interlink_domains", [])
    interlink = _normalize_interlink_domains(raw)
    existing = next(
        (e for e in interlink if isinstance(e, dict) and e.get("domain", "").lower() == domain_name.lower()),
        None,
    )
    if existing is None:
        interlink.append({"domain": domain_name, "concepts": sorted(concept_list)})
        concept_data["interlink_domains"] = interlink
        return True
    else:
        new_to_add = sorted(set(concept_list) - set(existing.get("concepts", [])))
        if new_to_add:
            existing["concepts"].extend(new_to_add)
            return True
    return False


def operation_5_update_interlink_domains(subject, domain):
    """
    After adding a new domain concept pool, run a bidirectional keyword-overlap
    cross-reference update across ALL concept pool files.

    Strategy (no LLM, no exact-name matching):
      For every pair (new_concept, other_concept) across pools:
        - Compute token sets for each (concept name + sub_concept topics, ≥5-char non-stopwords)
        - If shared tokens ≥ 1 → they are semantically linked

      For a match between new_concept A (new domain) and other_concept B (other domain):
        - In the OTHER pool: add interlink entry {domain: new_domain, concepts: [A]}
        - In the NEW pool:   add interlink entry {domain: other_domain, concepts: [B]}

    Only adds; never removes. Idempotent — skips entries already present.
    """
    print(f"\nOperation 5: Update interlink_domains (bidirectional keyword matching)")

    domain_snake = domain_to_snake_case(domain)
    subject_lower = subject.lower()

    # Pool can live in flat or nested directory layout
    new_pool_candidates = [
        CONCEPT_POOLS_DIR / subject_lower / domain_snake / f"{subject_lower}_{domain_snake}.json",
        CONCEPT_POOLS_DIR / f"{subject_lower}_{domain_snake}.json",
    ]
    new_pool_path = next((p for p in new_pool_candidates if p.exists()), None)

    if new_pool_path is None:
        print(f"  ✗ Cannot find concept pool for {subject} > {domain}. Skipping.")
        return 0

    new_pool = load_json(new_pool_path)
    if not new_pool or not isinstance(new_pool.get("concepts"), dict):
        print(f"  ✗ Empty or unreadable pool at {new_pool_path}. Skipping.")
        return 0

    new_pool_concepts = new_pool.get("concepts", {})

    # Pre-compute token sets for each concept in the new pool
    new_tokens: dict[str, set[str]] = {
        cname: _concept_tokens(cname, cdata.get("sub_concepts"))
        for cname, cdata in new_pool_concepts.items()
    }

    all_pool_files = sorted(CONCEPT_POOLS_DIR.rglob("*.json"))
    total_updated = 0
    new_pool_modified = False

    for pool_file in all_pool_files:
        if pool_file.resolve() == new_pool_path.resolve():
            continue

        other_pool = load_json(pool_file)
        if not other_pool or not isinstance(other_pool.get("concepts"), dict):
            continue

        other_subdomain = other_pool.get("subdomain", pool_file.stem)
        other_modified = False

        for other_cname, other_cdata in other_pool["concepts"].items():
            other_tok = _concept_tokens(other_cname, other_cdata.get("sub_concepts"))

            # Find new-pool concepts that share keywords with this other concept
            matched_new: list[str] = [
                nc for nc, ntok in new_tokens.items() if ntok & other_tok
            ]
            if not matched_new:
                continue

            # Update OTHER pool: add new domain as interlink source
            if _upsert_interlink(other_cdata, domain, matched_new):
                other_modified = True
                total_updated += len(matched_new)

            # Update NEW pool: add other domain as interlink source for each matched new concept
            for nc in matched_new:
                if _upsert_interlink(new_pool_concepts[nc], other_subdomain, [other_cname]):
                    new_pool_modified = True
                    total_updated += 1

        if other_modified:
            save_json(pool_file, other_pool)

    if new_pool_modified:
        save_json(new_pool_path, new_pool)

    print(f"  ✓ interlink_domains entries added/updated: {total_updated}")
    return total_updated


def main():
    parser = argparse.ArgumentParser(description="Merge PYQ analysis into prelims pipeline")
    parser.add_argument("--subject", required=True, help="Subject (e.g., 'Geography')")
    parser.add_argument("--domain", required=True, help="Domain (e.g., 'Oceanography')")
    parser.add_argument("--research-dir", help="Path to research output directory (not needed with --interlinks-only)")
    parser.add_argument(
        "--interlinks-only",
        action="store_true",
        help="Skip ops 1-4; only run operation 5 (update interlink_domains). "
             "Use after manually writing a concept pool.",
    )

    args = parser.parse_args()

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Pipeline merge: {args.subject} > {args.domain}")
    if args.interlinks_only:
        print(f"Mode: interlinks-only (ops 1–4 skipped)")
    else:
        print(f"Research dir: {args.research_dir}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        if args.interlinks_only:
            op5_result = operation_5_update_interlink_domains(args.subject, args.domain)
            print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"Summary (interlinks-only):")
            print(f"  interlink_domains entries added/updated: {op5_result}")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        else:
            if not args.research_dir:
                print("✗ --research-dir is required unless --interlinks-only is set")
                sys.exit(1)

            research_dir = Path(args.research_dir)
            if not research_dir.exists():
                print(f"✗ Research directory not found: {research_dir}")
                sys.exit(1)

            op1_result = operation_1_merge_concepts(args.subject, args.domain, research_dir)
            op2_result = operation_2_update_shared_traps(args.subject, args.domain, research_dir)
            operation_3_create_domain_traps(args.subject, args.domain, research_dir)
            op4_result = operation_4_update_difficulty_types(args.subject, args.domain, research_dir)
            op5_result = operation_5_update_interlink_domains(args.subject, args.domain)

            print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"Summary:")
            print(f"  Concepts added: {op1_result['added']}, merged: {op1_result['merged']}")
            print(f"  Traps added to shared: {op2_result['added']}, skipped (duplicates): {op2_result['skipped']}")
            print(f"  Domain-specific trap file: created")
            print(f"  Difficulty type percentages updated: {op4_result}")
            print(f"  interlink_domains entries added/updated: {op5_result}")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    except Exception as e:
        print(f"\n✗ Error during merge: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
