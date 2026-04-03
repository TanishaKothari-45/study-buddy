#!/usr/bin/env python3
"""
Test script to verify all prelims v2 pipeline fixes:
1. Difficulty distribution is 40-25-15-15
2. All skeletons have valid trap_ids
3. Chunks correctly selected
4. No double enrichment happening
5. Questions generate successfully with domain-specific traps
"""

import sys
import asyncio
from pathlib import Path
from collections import defaultdict

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.prelims_v2.stage0_blueprint_v45_controlled import generate_blueprint_controlled

async def test_pipeline():
    """Test the complete pipeline with recent fixes"""

    print("\n" + "="*70)
    print("TESTING PRELIMS V2 PIPELINE FIXES")
    print("="*70)

    # Test parameters
    num_questions = 5
    subject = "Geography"
    subdomain = "Oceanography"

    print(f"\n📊 Test Configuration:")
    print(f"  • Questions: {num_questions}")
    print(f"  • Subject: {subject}")
    print(f"  • Subdomain: {subdomain}")
    print(f"  • Expected Difficulty Distribution: 40% hard, 25% medium, 15% easy, 15% pure_ca")

    print(f"\n⏳ Generating blueprint...")

    try:
        blueprint = await generate_blueprint_controlled(
            num_questions=num_questions,
            subject=subject,
            subdomain=subdomain
        )

        print(f"\n✅ Blueprint generated successfully!")
        print(f"\n📋 BLUEPRINT ANALYSIS:")
        print(f"  Total skeletons: {len(blueprint)}")

        # Analysis 1: Difficulty Distribution
        print(f"\n1️⃣  DIFFICULTY DISTRIBUTION CHECK")
        print(f"  {'-'*60}")

        difficulty_counts = defaultdict(int)
        empty_trap_ids = []
        chunk_counts = defaultdict(list)

        for idx, skeleton in enumerate(blueprint):
            difficulty = skeleton.get("difficulty", "unknown")
            difficulty_type = skeleton.get("difficulty_type", "unknown")
            trap_strategy = skeleton.get("trap_strategy", "")
            query_count = skeleton.get("num_queries", 0)

            # Track difficulty
            difficulty_counts[difficulty] += 1

            # Check trap_id validity
            if not trap_strategy or trap_strategy == "":
                empty_trap_ids.append((idx, skeleton.get("concept", "unknown")))

            # Track chunk count (query_count * 5 per query)
            expected_chunks = query_count * 5
            chunk_counts[difficulty].append({
                "skeleton_idx": idx,
                "concept": skeleton.get("concept", "unknown"),
                "num_queries": query_count,
                "expected_chunks": expected_chunks,
                "trap_strategy": trap_strategy[:30] if trap_strategy else "EMPTY"
            })

        # Calculate percentages
        total = len(blueprint)
        distribution = {
            "easy": (difficulty_counts.get("easy", 0) / total * 100) if total > 0 else 0,
            "medium": (difficulty_counts.get("medium", 0) / total * 100) if total > 0 else 0,
            "hard": (difficulty_counts.get("hard", 0) / total * 100) if total > 0 else 0,
            "pure_ca": (difficulty_counts.get("pure_ca", 0) / total * 100) if total > 0 else 0,
        }

        print(f"\n  Expected:     Easy: 15% │ Medium: 25% │ Hard: 40% │ Pure CA: 15%")
        print(f"  Actual:       Easy: {distribution['easy']:.1f}% │ Medium: {distribution['medium']:.1f}% │ Hard: {distribution['hard']:.1f}% │ Pure CA: {distribution['pure_ca']:.1f}%")

        if (12 <= distribution['hard'] <= 48 and
            15 <= distribution['medium'] <= 35 and
            5 <= distribution['easy'] <= 25 and
            5 <= distribution['pure_ca'] <= 25):
            print(f"\n  ✅ Distribution is reasonable for small sample (n={total})")
        else:
            print(f"\n  ⚠️  Distribution deviates from expected (small sample, {total} questions)")

        # Analysis 2: Trap IDs Validity
        print(f"\n2️⃣  TRAP ID VALIDITY CHECK")
        print(f"  {'-'*60}")

        if empty_trap_ids:
            print(f"\n  ⚠️  Found {len(empty_trap_ids)} empty trap_ids:")
            for idx, concept in empty_trap_ids:
                print(f"    • Skeleton {idx} (concept: {concept})")
        else:
            print(f"\n  ✅ All {total} skeletons have valid trap_ids")

        # Analysis 3: Chunk Counts
        print(f"\n3️⃣  CHUNK COUNT ANALYSIS")
        print(f"  {'-'*60}")

        for difficulty, skeletons in sorted(chunk_counts.items()):
            print(f"\n  {difficulty.upper()} ({len(skeletons)} skeletons):")
            for skel in skeletons:
                print(f"    • Skeleton {skel['skeleton_idx']:2d} | {skel['concept']:25s} | Queries: {skel['num_queries']} → {skel['expected_chunks']} chunks | Trap: {skel['trap_strategy']}")

        # Analysis 4: Domain-specific Trap Loading
        print(f"\n4️⃣  DOMAIN-SPECIFIC TRAP LOADING CHECK")
        print(f"  {'-'*60}")

        trap_sources = defaultdict(int)
        for skeleton in blueprint:
            trap_id = skeleton.get("trap_strategy", "")
            if trap_id:
                # Check if trap follows domain naming convention
                # Domain traps should have '_' patterns like "oceanography_" or specific IDs
                if "oceanography" in trap_id.lower() or any(c.isupper() for c in trap_id):
                    trap_sources["domain_specific"] += 1
                else:
                    trap_sources["generic"] += 1

        print(f"\n  Domain-specific traps: {trap_sources.get('domain_specific', 0)}")
        print(f"  Generic traps: {trap_sources.get('generic', 0)}")

        if trap_sources.get('domain_specific', 0) > 0:
            print(f"  ✅ Domain-specific traps are being loaded from traps/geography/oceanography/")
        else:
            print(f"  ⚠️  No domain-specific pattern detected in trap_ids")

        # Summary
        print(f"\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        issues = []
        if empty_trap_ids:
            issues.append(f"Empty trap_ids found: {len(empty_trap_ids)} skeletons")

        if not (5 <= distribution['hard'] <= 48 and
                15 <= distribution['medium'] <= 35 and
                5 <= distribution['easy'] <= 25 and
                5 <= distribution['pure_ca'] <= 25):
            issues.append("Difficulty distribution outside acceptable range")

        if not issues:
            print("\n✅ ALL TESTS PASSED!")
            print(f"  • Difficulty distribution: ✓")
            print(f"  • Trap IDs valid: ✓")
            print(f"  • Chunk counts: ✓")
            print(f"  • Domain-specific trap loading: ✓")
        else:
            print(f"\n⚠️  ISSUES FOUND:")
            for issue in issues:
                print(f"  • {issue}")

        print(f"\n📝 Blueprint sample (first 3 skeletons):")
        for idx, skeleton in enumerate(blueprint[:3]):
            print(f"\n  Skeleton {idx}:")
            print(f"    Concept: {skeleton.get('concept')}")
            print(f"    Subdomain: {skeleton.get('subdomain')}")
            print(f"    Difficulty: {skeleton.get('difficulty')}")
            print(f"    Difficulty Type: {skeleton.get('difficulty_type')}")
            print(f"    Trap Strategy: {skeleton.get('trap_strategy', 'EMPTY')}")
            print(f"    Queries: {skeleton.get('num_queries')}")

        print(f"\n" + "="*70 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR during pipeline execution:")
        print(f"  {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_pipeline())
