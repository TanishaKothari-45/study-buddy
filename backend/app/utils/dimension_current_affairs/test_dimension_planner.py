"""
Test script for Dimension Query Planner

Run from backend directory:
    python -m app.utils.dimension_current_affairs.test_dimension_planner
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.utils.dimension_current_affairs import generate_dimension_plan, get_all_search_queries


# Test questions
TEST_QUESTIONS = [
    "Discuss the impact of climate change on tribal agriculture in India. What measures can be taken to ensure food security for tribal communities?",
    "Critically examine the role of civil society organizations in strengthening grassroots democracy in India.",
    "Analyze the significance of the India-Middle East-Europe Economic Corridor (IMEC) for India's strategic and economic interests.",
]


async def test_single_question(question: str, use_pro: bool = False):
    """Test dimension planning for a single question."""
    print(f"\n{'='*80}")
    print(f"QUESTION: {question[:70]}...")
    print(f"{'='*80}")
    
    try:
        plan = await generate_dimension_plan(
            question=question,
            use_pro_model=use_pro
        )
        
        print(f"\n📐 Generated {len(plan.dimensions)} dimensions:\n")
        
        for i, dim in enumerate(plan.dimensions, 1):
            print(f"{i}. {dim.dimension}")
            print(f"   Description: {dim.dimension_description}")
            print(f"   Queries:")
            for q in dim.search_queries:
                print(f"      • {q}")
            print()
        
        # Summary
        all_queries = get_all_search_queries(plan)
        print(f"📊 Total search queries: {len(all_queries)}")
        
        # Print raw JSON for debugging
        print(f"\n📄 Raw JSON output:")
        print(json.dumps(plan.model_dump(), indent=2, ensure_ascii=False))
        
        return plan
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run tests on sample questions."""
    print("🧪 Testing Dimension Query Planner")
    print("="*80)
    
    # Test first question with Flash (default)
    print("\n🔹 Testing with Gemini Flash (default)...")
    await test_single_question(TEST_QUESTIONS[0], use_pro=False)
    
    # Uncomment to test with Pro model
    # print("\n🔹 Testing with Gemini Pro...")
    # await test_single_question(TEST_QUESTIONS[0], use_pro=True)
    
    # Test remaining questions
    # for q in TEST_QUESTIONS[1:]:
    #     await test_single_question(q)


if __name__ == "__main__":
    asyncio.run(main())
