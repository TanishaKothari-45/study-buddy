"""
PDF text extraction and chunking utilities
"""

import logging
from pathlib import Path
from typing import List, Dict, Any
import pdfplumber
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Clean extracted text to handle common PDF issues"""
    import re
    # Remove repeated characters (like 'II' becoming 'I')
    text = re.sub(r'(.)\1+', r'\1', text)
    # Fix common OCR issues
    text = text.replace('II', 'I').replace('EE', 'E').replace('aa', 'a')
    # Remove non-standard whitespace
    text = ' '.join(text.split())
    return text

def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page by page from a PDF and returns a list of dictionaries,
    each containing the text and page number.
    """
    pages_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # First try to extract tables
                tables = page.extract_tables()
                page_text = ""
                
                if tables:
                    # If tables exist, format them properly
                    for table in tables:
                        if table:
                            # Convert table to formatted text
                            table_text = "\n".join(
                                " | ".join(str(cell) if cell else "" for cell in row)
                                for row in table
                            )
                            page_text += "\nTable:\n" + table_text + "\n"
                
                # Then extract regular text
                text = page.extract_text()
                if text:
                    page_text += "\n" + text
                
                if page_text.strip():
                    # Clean the text
                    cleaned_text = clean_text(page_text)
                    pages_content.append({
                        "page_number": i + 1,
                        "text": cleaned_text
                    })
                    
    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {e}")
        return []
    
    return pages_content

def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Chunks text into smaller pieces with a specified overlap.
    Preserves table structure and handles special content.
    """
    # Split text into sections (regular text and tables)
    sections = text.split("\nTable:\n")
    chunks = []
    
    for i, section in enumerate(sections):
        if not section.strip():
            continue
            
        # If this is a table section, keep it as one chunk
        if i > 0 or section.count("|") > 2:  # It's a table
            if len(section.split()) > 20:  # Only include substantial tables
                chunks.append(f"Table data:\n{section.strip()}")
            continue
            
        # For regular text, chunk by words
        words = section.split()
        j = 0
        while j < len(words):
            chunk = " ".join(words[j:j + chunk_size])
            if len(chunk.strip()) > 50:  # Only include substantial chunks
                chunks.append(chunk)
            j += chunk_size - chunk_overlap
            if j < 0:  # Ensure j doesn't go negative if chunk_overlap > chunk_size
                j = 0
                
    return chunks

def process_pdf_for_chunks(pdf_path: str, filename: str, chunk_size: int, chunk_overlap: int) -> List[Dict[str, Any]]:
    """
    Extracts text from a PDF, chunks it, and adds metadata.
    """
    all_chunks_with_metadata = []
    pages_content = extract_text_from_pdf(pdf_path)

    for page_data in pages_content:
        page_text = page_data["text"]
        page_number = page_data["page_number"]
        chunks = chunk_text(page_text, chunk_size, chunk_overlap)
        for chunk_text_content in chunks:
            if len(chunk_text_content.strip()) > 50:  # Only add substantial chunks
                all_chunks_with_metadata.append({
                    "content": chunk_text_content,
                    "metadata": {
                        "filename": filename,
                        "page_number": page_number,
                        "subject": "Geography"
                    }
                })
    return all_chunks_with_metadata