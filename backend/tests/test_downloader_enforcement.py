
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.utils.current_affairs_downloader import process_extracted_pdf

class TestDownloaderEnforcement(unittest.TestCase):
    
    @patch('app.utils.hierarchical_chunker.HierarchicalChunker')
    @patch('app.utils.pinecone_handler.PineconeHandler')
    @patch('app.utils.content_store.ContentStore')
    @patch('app.utils.metadata_enricher.classify_chunks_batch')
    @patch('app.routes.upload_content_store.match_and_store_pinecone_chunks')
    @patch('app.utils.pdf_section_extractor.extract_sections_with_validation')
    @patch('openai.OpenAI')
    def test_process_extracted_pdf_enforcement(self, mock_openai, mock_extract, mock_match, mock_classify, mock_store, mock_pinecone, mock_chunker):
        
        # Setup mocks
        mock_chunker_instance = mock_chunker.return_value
        mock_chunker_instance.process_pdf.return_value = ["chunk1"]
        mock_classify.return_value = [{"content": "chunk1", "metadata": {}}]
        mock_match.return_value = {"stored_count": 1, "match_rate": 1.0}
        
        # Case 1: File has _geo_env suffix -> Should proceed without extraction
        print("\nTesting Case 1: File with _geo_env suffix")
        result = process_extracted_pdf("test_file_geo_env.pdf")
        self.assertEqual(result["status"], "success")
        mock_extract.assert_not_called()
        print("✅ Case 1 Passed")
        
        # Case 2: File does NOT have suffix, Extraction Succeeds -> Should proceed
        print("\nTesting Case 2: File without suffix, Extraction Succeeds")
        mock_extract.return_value = "extracted_test_file_geo_env.pdf"
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            result = process_extracted_pdf("test_file.pdf")
            self.assertEqual(result["status"], "success")
            mock_extract.assert_called_once()
            # Verify chunker was called with the EXTRACTED file
            mock_chunker_instance.process_pdf.assert_called_with("extracted_test_file_geo_env.pdf", "extracted_test_file_geo_env.pdf")
        print("✅ Case 2 Passed")
        
        # Reset mocks
        mock_extract.reset_mock()
        mock_chunker_instance.reset_mock()
        
        # Case 3: File does NOT have suffix, Extraction Fails -> Should Fail
        print("\nTesting Case 3: File without suffix, Extraction Fails")
        mock_extract.return_value = None
        result = process_extracted_pdf("test_file_fail.pdf")
        self.assertEqual(result["status"], "failed")
        self.assertIn("Could not extract", result["reason"])
        mock_extract.assert_called_once()
        mock_chunker_instance.process_pdf.assert_not_called()
        print("✅ Case 3 Passed")

if __name__ == '__main__':
    unittest.main()
