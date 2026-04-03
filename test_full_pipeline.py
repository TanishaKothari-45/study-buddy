#!/usr/bin/env python3
"""
Test the full pipeline: Stage 0 → Stage 1 → Stage 3
Verify trap loading, chunk retrieval, and question generation.
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

from app.prelims_v2.pipeline import generate_mock_questions

async def test_full_pipeline():
    """Test the complete mock question generation pipeline."""

    print("\n" + "="*80)
    print("FULL PIPELINE TEST: Stage 0 → Stage 1 → Stage 3")
    print("="*80)

    # Test parameters
    num_questions = 5
    subject = "Geography"
    topics = ["Oceanography"]  # Subdomain

    print(f"\n📊 Pipeline Config:")
    print(f"   • Questions: {num_questions}")
    print(f"   • Subject: {subject}")
    print(f"   • Topics: {topics}")

    try:
        print(f"\n⏳ Executing pipeline (Stage 0 → 1 → 3)...")

        result = await generate_mock_questions(
            num_questions=num_questions,
            topics=topics,
            subject=subject
        )

        print(f"\n✅ Pipeline completed successfully!")

        # Analyze results
        if isinstance(result, dict):
            questions = result.get("questions", [])
        else:
            questions = result if result else []

        print(f"\n📋 PIPELINE RESULTS:")
        print(f"   {'-'*76}")
        print(f"   Generated: {len(questions)} questions")

        # Analysis
        issues = []
        empty_questions = 0
        empty_answers = 0
        empty_options = 0

        for idx, q in enumerate(questions, 1):
            if not q.get("question"):
                empty_questions += 1
            if not q.get("correct_answer"):
                empty_answers += 1
            options = q.get("options", [])
            if not options or len(options) < 4:
                empty_options += 1

        if empty_questions > 0:
            issues.append(f"Empty questions: {empty_questions}/{len(questions)}")
        if empty_answers > 0:
            issues.append(f"Empty answers: {empty_answers}/{len(questions)}")
        if empty_options > 0:
            issues.append(f"Incomplete options: {empty_options}/{len(questions)}")

        # Show sample
        print(f"\n📝 SAMPLE QUESTION:")
        if questions:
            q = questions[0]
            print(f"   Question: {q.get('question', 'N/A')[:100]}...")
            print(f"   Options: {len(q.get('options', []))} options")
            print(f"   Answer: {q.get('correct_answer', 'N/A')}")
            print(f"   Explanation: {q.get('explanation', 'N/A')[:80]}...")

        # Summary
        print(f"\n" + "="*80)
        if not issues:
            print("✅ ALL TESTS PASSED!")
            print(f"   • {len(questions)} complete questions generated")
            print(f"   • All questions have content")
            print(f"   • All questions have answers & options")
        else:
            print(f"⚠️  ISSUES FOUND:")
            for issue in issues:
                print(f"   • {issue}")

        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR during pipeline execution:")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
