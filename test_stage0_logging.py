#!/usr/bin/env python3
"""
Test Stage 0 trap loading with detailed logging.
Shows which trap files are being loaded and trap assignments.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s | %(name)s | %(message)s'
)

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.prelims_v2.stage0_blueprint_v45_controlled import generate_blueprint_controlled

async def test_stage0_with_logging():
    """Test Stage 0 with logging to show trap loading."""

    print("\n" + "="*80)
    print("STAGE 0 TRAP LOADING TEST WITH DETAILED LOGGING")
    print("="*80)
    print("\nRunning: generate_blueprint_controlled(5, 'Geography', 'Oceanography')")
    print("-"*80 + "\n")

    blueprint = await generate_blueprint_controlled(
        num_questions=5,
        subject="Geography",
        subdomain="Oceanography"
    )

    print("\n" + "-"*80)
    print("\nRESULTS:")
    print("-"*80)

    print(f"\n✅ Generated {len(blueprint)} skeletons")

    # Show trap_strategy for each
    print(f"\nTrap Strategy Assignment:")
    for idx, skeleton in enumerate(blueprint, 1):
        trap = skeleton.trap_strategy if skeleton.trap_strategy else "EMPTY"
        concept = skeleton.concept
        print(f"  {idx}. {concept:35s} → {trap}")

    # Summary
    empty_count = sum(1 for s in blueprint if not s.trap_strategy)
    filled_count = len(blueprint) - empty_count

    print(f"\n{'-'*80}")
    print(f"Summary: {filled_count} filled, {empty_count} empty out of {len(blueprint)} total")

    if empty_count == 0:
        print("✅ SUCCESS: All traps assigned correctly!")
    else:
        print(f"⚠️  FAILURE: {empty_count} skeletons have empty trap_strategy")

    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_stage0_with_logging())
