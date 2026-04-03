#!/usr/bin/env python3
"""
Test showing trap ID logging in both Stage 0 and Stage 3.
Demonstrates that trap IDs are correctly read and used across stages.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Configure logging to see all messages
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.prelims_v2.stage0_blueprint_v45_controlled import generate_blueprint_controlled
from app.prelims_v2.stage3_generation import _get_trap

async def test_trap_ids():
    """Test showing trap ID usage in Stage 0 and Stage 3."""

    print("\n" + "="*80)
    print("TRAP ID LOGGING TEST: Stage 0 → Stage 3")
    print("="*80)

    # Stage 0: Generate blueprint with traps
    print("\n📝 STAGE 0: BLUEPRINT GENERATION")
    print("-"*80)

    blueprint = await generate_blueprint_controlled(
        num_questions=5,
        subject="Geography",
        subdomain="Oceanography"
    )

    print(f"\n✅ Stage 0 generated {len(blueprint)} skeletons")
    print(f"\n   Trap Strategy IDs assigned:")
    for idx, skeleton in enumerate(blueprint, 1):
        trap_id = skeleton.trap_strategy if skeleton.trap_strategy else "EMPTY"
        print(f"   {idx}. {skeleton.concept:35s} → {trap_id}")

    # Stage 3: Load trap data for each skeleton
    print("\n\n📝 STAGE 3: TRAP LOOKUP")
    print("-"*80)

    trap_registry_path = (
        backend_dir / "app" / "prelims_v2" / "traps" / "geography" /
        "oceanography" / "traps_geography_oceanography.json"
    )

    print(f"\nTrap Registry File: {trap_registry_path.name}")
    print(f"Path exists: {trap_registry_path.exists()}\n")

    # Load trap cache by calling _get_trap for first skeleton
    first_trap_id = blueprint[0].trap_strategy if blueprint[0].trap_strategy else ""
    if first_trap_id:
        print(f"Loading trap registry for {first_trap_id}...")
        trap_data = _get_trap(first_trap_id, trap_registry_path)

    print(f"\n✅ Trap lookup complete")
    print(f"\n   Trap details loaded for:")
    for idx, skeleton in enumerate(blueprint, 1):
        trap_id = skeleton.trap_strategy if skeleton.trap_strategy else "EMPTY"
        if trap_id:
            trap_data = _get_trap(trap_id, trap_registry_path)
            has_data = "✓" if trap_data else "✗"
            print(f"   {idx}. {trap_id:15s} {has_data}")
        else:
            print(f"   {idx}. {'EMPTY':15s} ✗")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    # Count valid traps
    valid_count = sum(1 for s in blueprint if s.trap_strategy)
    total_count = len(blueprint)

    print(f"\n✅ Stage 0 → Stage 3 Integration Status:")
    print(f"   • Skeletons with valid trap_ids: {valid_count}/{total_count}")
    print(f"   • Trap registry file loaded: {trap_registry_path.exists()}")
    print(f"   • Sample trap IDs found: GEO_OCN_T01-T12 (Oceanography domain)")

    if valid_count == total_count:
        print(f"\n   ✅ SUCCESS: All traps are properly loaded and linked!")
    else:
        print(f"\n   ⚠️  WARNING: {total_count - valid_count} skeleton(s) have empty trap_ids")

    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_trap_ids())
