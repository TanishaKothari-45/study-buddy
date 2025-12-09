"""
Example: Using pdf_precleaner standalone

This shows how to use the PDF precleaner before chunking.
"""

import sys
from pathlib import Path

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.utils.pdf_precleaner import preprocess_pdf, clean_text_basic

# Example 1: Preprocess entire PDF
pdf_path = "path/to/your/pdf.pdf"
clean_text = preprocess_pdf(pdf_path)

# Example 2: Use with hierarchical chunker (if available)
# from backend.app.utils.hierarchical_chunker import HierarchicalChunker
# from openai import OpenAI
# 
# clean_text = preprocess_pdf(pdf_path)
# chunker = HierarchicalChunker(llm_client=OpenAI(api_key="your-key"))
# chunks = chunker.process_txt(None, filename=pdf_path, subject="Geography", text_override=clean_text)

# Example 3: Clean text directly
raw_text = "Some text with visionias watermark and www.example.com URL"
cleaned = clean_text_basic(raw_text)
print(f"Cleaned: {cleaned}")

