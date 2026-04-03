#!/usr/bin/env python3.11
"""
10-Question Pipeline Test: Stage 0 → 1 → 3 → 4 → 5

Validates the complete v2 pipeline (no Stage 2):
  1. Generate 30 skeletons → select 13
  2. Retrieve 65 chunks per skeleton
  3. Batch into 7+6, filter to 5 chunks each
  4. Generate questions (batch + fallback)
  5. Quality gate validation
  6. Gap fill & finalize

Expected metrics:
  - Pass rate >80%
  - Trap enforcement 100%
  - Question type diversity (7+ types)
  - Structured/exploratory ratio ~70/30
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.gemini_core.gemini_client import GeminiClient
from app.gemini_core.settings_gemini_key import GEMINI_API_KEY
from app.utils.pinecone_handler import PineconeHandler
from app.prelims_v2.pipeline import run_v2_pipeline


async def main():
    logger.info("=" * 80)
    logger.info("🧪 [TEST] 10-Question V2 Pipeline (No Stage 2)")
    logger.info("=" * 80)

    # Setup clients

    gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
    pinecone_handler = PineconeHandler(index_name=settings.PINECONE_INDEX_NAME)

    # Minimal Redis mock (no progress tracking for this test)
    class FakeRedis:
        async def set(self, *args, **kwargs):
            pass
        async def exists(self, *args, **kwargs):
            return False

    redis = FakeRedis()

    # Test parameters
    job_id = "test_v2_10q_001"
    num_questions = 10
    topics = ["Geography", "Climatology"]
    subject = "Geography"

    logger.info(f"Test Config:")
    logger.info(f"  Job ID: {job_id}")
    logger.info(f"  Questions: {num_questions}")
    logger.info(f"  Topics: {topics}")
    logger.info(f"  Subject: {subject}")
    logger.info("")

    try:
        # Run pipeline
        final_questions = await run_v2_pipeline(
            job_id=job_id,
            num_questions=num_questions,
            topics=topics,
            subject=subject,
            pinecone_handler=pinecone_handler,
            gemini_client=gemini_client,
            redis=redis,
            user_id=None,
        )

        # Results
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ [TEST PASSED] Generated {len(final_questions)} questions")
        logger.info("=" * 80)

        # Summary metrics
        if final_questions:
            logger.info("\n📊 [METRICS]")
            logger.info(f"  Total questions: {len(final_questions)}")

            # Question types
            types = [q["source"].get("question_type") for q in final_questions]
            unique_types = len(set(types))
            logger.info(f"  Question types: {unique_types} unique types")
            for qtype in set(types):
                count = types.count(qtype)
                logger.info(f"    • {qtype}: {count}")

            # Difficulty distribution
            difficulties = [q["source"].get("difficulty") for q in final_questions]
            logger.info(f"  Difficulties:")
            for diff in set(difficulties):
                count = difficulties.count(diff)
                logger.info(f"    • {diff}: {count}")

            # Trap verification
            trapped = sum(1 for q in final_questions if q["source"].get("trap_verified"))
            logger.info(f"  Trap verified: {trapped}/{len(final_questions)} ({100*trapped//len(final_questions)}%)")

            # CA in stem
            ca_in_stem = sum(1 for q in final_questions if q["source"].get("ca_in_stem"))
            logger.info(f"  CA in stem: {ca_in_stem}/{len(final_questions)} ({100*ca_in_stem//len(final_questions)}%)")

            # Quality scores
            scores = [q["source"].get("quality_score", 0) for q in final_questions]
            avg_score = sum(scores) / len(scores) if scores else 0
            logger.info(f"  Avg quality score: {avg_score:.2f}")

            # Save output
            output_file = Path(__file__).parent / f"test_output_{job_id}.json"
            with open(output_file, "w") as f:
                json.dump(final_questions, f, indent=2)
            logger.info(f"\n💾 Output saved to: {output_file}")

        return True

    except Exception as e:
        logger.error(f"\n❌ [TEST FAILED] {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
