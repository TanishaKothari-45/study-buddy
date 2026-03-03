import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock
from collections import defaultdict

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.utils.query_builder import build_query_text
from app.utils.mock_test_prompting import assemble_upsc_prompt, COGNITIVE_FRAMEWORK
from app.utils.batch_validator import validate_batch
from app.routes.mock_test import bucket_chunks_by_metadata

class TestMockTestPipelineAdvanced(unittest.TestCase):
    
    def test_query_builder_standardized(self):
        """Test if query builder is simplified and semantic-focused."""
        # Check that subject still changes tone
        query_ncert = build_query_text(major_domain="Geomorphology", subject="ncert")
        self.assertIn("fundamental NCERT-level", query_ncert)
        
        query_normal = build_query_text(major_domain="Climatology", subject="general")
        self.assertIn("advanced analytical and conceptual synthesis", query_normal)
        self.assertIn("UPSC analytical context:", query_normal)

    def test_metadata_bucketing(self):
        """Test hierarchical clustering by metadata."""
        chunks = [
            {"metadata": {"major_domain": "Physical Geography", "sub_domain": "Climatology", "section": "Atmosphere"}},
            {"metadata": {"major_domain": "Physical Geography", "sub_domain": "Oceanography", "section": "Tides"}},
            {"metadata": {"major_domain": "Human Geography", "sub_domain": "Population", "section": "Migration"}},
        ]
        
        # Level 1: No topic selection -> Bucket by Major Domain
        buckets1 = bucket_chunks_by_metadata(chunks, None, None)
        self.assertEqual(len(buckets1), 2)
        self.assertIn("Physical Geography", buckets1)
        self.assertIn("Human Geography", buckets1)
        
        # Level 2: Major Domain selected -> Bucket by Sub Domain
        buckets2 = bucket_chunks_by_metadata(chunks, "Physical Geography", None)
        self.assertIn("Climatology", buckets2)
        self.assertIn("Oceanography", buckets2)
        
        # Level 3: Sub Domain selected -> Bucket by Section
        buckets3 = bucket_chunks_by_metadata(chunks, "Physical Geography", "Climatology")
        self.assertIn("Atmosphere", buckets3)

    def test_prompt_no_trimming(self):
        """Test if prompt assembly passes full text without character limits."""
        long_text = "Context word " * 1000 # ~12000 chars
        long_examples = "Example word " * 500 # ~6000 chars
        
        prompt = assemble_upsc_prompt(
            topic="Test",
            num_questions=5,
            retrieved_static_text=long_text,
            pyq_examples=long_examples
        )
        
        # Verify no trimming occurred
        self.assertIn(long_text, prompt)
        self.assertIn(long_examples, prompt)

    def test_validator_upsc_rigor(self):
        """Test the enhanced validator with UPSC-grade questions."""
        valid_q = {
            "question": "Consider the following statements regarding the Himalayas:\n1. They are young fold mountains.\n2. They are increasing in height.\nWhich of the above is/are correct?",
            "options": ["(a) 1 only", "(b) 2 only", "(c) Both 1 and 2", "(d) Neither 1 nor 2"],
            "correct_answer": "C",
            "explanation": "Statement 1 is correct as Himalayas were formed in recent geological times. Statement 2 is correct because the plate collision continues, leading to rise."
        }
        
        valid_questions, errors = validate_batch([valid_q])
        self.assertEqual(len(valid_questions), 1)
        self.assertEqual(len(errors), 0)

if __name__ == "__main__":
    unittest.main()
