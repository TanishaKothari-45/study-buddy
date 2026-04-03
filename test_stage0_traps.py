#!/usr/bin/env python3
"""
Quick test to verify Stage 0 is loading domain-specific traps correctly
and assigning trap_strategy to all skeletons.
"""

import sys
import asyncio
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.prelims_v2.stage0_blueprint_v45_controlled import generate_blueprint_controlled

async def test_stage0_traps():
    """Test Stage 0 trap loading and assignment."""

    print("\n" + "="*70)
    print("TESTING STAGE 0 TRAP LOADING & ASSIGNMENT")
    print("="*70)

    # Test parameters
    num_questions = 5
    subject = "Geography"
    subdomain = "Oceanography"

    print(f"\n📝 Config: {num_questions} questions from {subject}/{subdomain}")
    print(f"   Expected: All skeletons should have non-empty trap_strategy")

    try:
        blueprint = await generate_blueprint_controlled(
            num_questions=num_questions,
            subject=subject,
            subdomain=subdomain
        )

        print(f"\n✅ Blueprint generated: {len(blueprint)} skeletons")

        # Analyze trap assignment
        print(f"\n🔍 TRAP STRATEGY ANALYSIS:")
        print(f"   {'-'*60}")

        empty_count = 0
        filled_count = 0

        for idx, skeleton in enumerate(blueprint, 1):
            trap_strategy = skeleton.trap_strategy if hasattr(skeleton, "trap_strategy") else ""
            concept = skeleton.concept if hasattr(skeleton, "concept") else "unknown"

            if not trap_strategy or trap_strategy == "":
                empty_count += 1
                print(f"   ❌ Skeleton {idx:2d} ({concept:25s}): trap_strategy = ''")
            else:
                filled_count += 1
                print(f"   ✅ Skeleton {idx:2d} ({concept:25s}): trap_strategy = {trap_strategy}")

        print(f"\n   {'-'*60}")
        print(f"   Filled: {filled_count}/{len(blueprint)}")
        print(f"   Empty:  {empty_count}/{len(blueprint)}")

        if empty_count == 0:
            print(f"\n   ✅ SUCCESS: All skeletons have valid trap_strategy!")
        else:
            print(f"\n   ⚠️  ISSUE: {empty_count} skeleton(s) have empty trap_strategy")

        # Show available_trap_ids for reference
        print(f"\n📦 AVAILABLE TRAP IDS (from trap_affinity):")
        print(f"   {'-'*60}")
        for idx, skeleton in enumerate(blueprint, 1):
            available = skeleton.available_trap_ids if hasattr(skeleton, "available_trap_ids") else []
            concept = skeleton.concept if hasattr(skeleton, "concept") else "unknown"
            print(f"   Skeleton {idx:2d} ({concept:25s}): {len(available)} traps → {available[:2] if available else 'NONE'}")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n" + "="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(test_stage0_traps())
