"""
PDF text extraction and chunking utilities
"""

import logging
from pathlib import Path
from typing import List, Dict, Any
import pdfplumber
from tqdm import tqdm
from .text_cleaner import clean_text_advanced
from .pdf_precleaner import clean_text_basic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Clean extracted text to handle common PDF issues and remove noise"""
    import re
    import unicodedata
    
    if not text:
        return ""
    
    # Step 1: Remove control characters and non-printable characters (except newlines and tabs)
    # Keep only printable characters, newlines, tabs, and common whitespace
    cleaned = []
    for char in text:
        if char == '\n' or char == '\t':
            cleaned.append(char)
        elif char.isspace():
            cleaned.append(' ')  # Normalize all whitespace to space
        elif unicodedata.category(char)[0] != 'C':  # Not a control character
            cleaned.append(char)
        # Skip control characters
    text = ''.join(cleaned)
    
    # Step 2: Remove excessive special symbols and decorative characters
    # Keep only standard punctuation and alphanumeric characters
    # Remove symbols that are likely noise (decorative, mathematical symbols used as noise, etc.)
    # Keep: letters, numbers, spaces, and common punctuation: . , ; : ! ? - ( ) [ ] { } " ' / \ | _ = + < > @ # $ % & * ~
    # Remove: decorative symbols, box-drawing characters, mathematical operators used as noise
    
    # Pattern to keep: alphanumeric, common punctuation, and whitespace
    # Remove everything else that's not a standard character
    text = re.sub(r'[^\w\s\.\,\;\:\!\?\-\_\(\)\[\]\{\}\"\'\`\/\\\|\=\+\<\>\@\#\$\%\&\*\~\n\t]', ' ', text)
    
    # Step 3: Remove sequences of special characters (likely noise)
    # Remove patterns like "✁✁ ✂ ✄" - sequences of non-alphanumeric characters
    text = re.sub(r'[^\w\s]{3,}', ' ', text)  # Remove 3+ consecutive special chars
    
    # Step 4: Remove excessive whitespace and normalize
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to max 2
    
    # Step 5: Fix common OCR issues
    text = text.replace('II', 'I').replace('EE', 'E').replace('aa', 'a')
    
    # Step 6: Remove lines that are mostly special characters or very short noise
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            cleaned_lines.append('')
            continue
        
        # Skip lines that are mostly special characters (less than 30% alphanumeric)
        alnum_count = sum(1 for c in line_stripped if c.isalnum())
        if len(line_stripped) > 0 and alnum_count / len(line_stripped) < 0.3:
            # This line is mostly noise, skip it
            continue
        
        # Skip very short lines that are just symbols
        if len(line_stripped) < 3 and not any(c.isalnum() for c in line_stripped):
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Step 7: Final cleanup - remove leading/trailing whitespace
    text = text.strip()
    
    # Step 8: Remove excessive repeated characters (but keep intentional ones like "III" in Roman numerals)
    # Only remove if it's 4+ repetitions of the same character
    text = re.sub(r'(.)\1{3,}', r'\1\1\1', text)  # Max 3 repetitions
    
    return text

def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page by page from a PDF and returns a list of dictionaries,
    each containing the text and page number.
    """
    pages_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"📖 Opening PDF: {pdf_path}")
            logger.info(f"   • Total pages in PDF: {total_pages}")
            
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
                    # First apply basic pre-cleaning (removes obvious garbage)
                    precleaned_text = clean_text_basic(page_text)
                    # Then apply advanced cleaning (removes headers/footers, etc.)
                    cleaned_text = clean_text_advanced(precleaned_text, pages_content=None)  # Will clean per-page first
                    if cleaned_text.strip():  # Only add if there's content after cleaning
                        pages_content.append({
                            "page_number": i + 1,
                            "text": cleaned_text
                        })
                    
                    # Log first page extraction for verification
                    if i == 0:
                        logger.info(f"   • Page 1 text extraction:")
                        logger.info(f"     - Raw length: {len(page_text)} chars")
                        logger.info(f"     - Cleaned length: {len(cleaned_text)} chars")
                        logger.info(f"     - Sample (first 300 chars): {cleaned_text[:300].replace(chr(10), ' ')}...")
                        if tables:
                            logger.info(f"     - Found {len(tables)} table(s) on page 1")
                    
    except Exception as e:
        logger.error(f"❌ Error extracting text from {pdf_path}: {e}")
        return []
    
    logger.info(f"   • Successfully extracted text from {len(pages_content)}/{total_pages} pages")
    
    # Apply advanced cleaning across all pages (for header/footer detection)
    if pages_content:
        logger.info(f"   🧹 Applying advanced text cleaning (removing headers/footers, images, noise)...")
        full_text = "\n".join(page.get("text", "") for page in pages_content)
        cleaned_full_text = clean_text_advanced(full_text, pages_content)
        
        # Split back into pages (approximate - this is a simplification)
        # In practice, headers/footers are already removed per-page above
        # This is mainly for final cleanup
        cleaned_pages = cleaned_full_text.split('\n\n')  # Rough page split
        
        # Update pages_content with cleaned text
        for i, page in enumerate(pages_content):
            if i < len(cleaned_pages):
                page["text"] = cleaned_pages[i].strip()
            else:
                # Re-clean individual page if split didn't work
                page["text"] = clean_text_advanced(page.get("text", ""), pages_content=None)
    
    return pages_content

def extract_text_with_logging(pdf_path: str) -> str:
    """Extracts and logs the first 500 characters of text from a given PDF."""
    contents = extract_text_from_pdf(pdf_path)
    if not contents:
        return ""
    full_text = "\n".join(page["text"] for page in contents)
    print(full_text[:500])
    print(f"Text length: {len(full_text)}")
    return full_text

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
    pages_content = extract_text_with_logging(pdf_path)

    # Add guard for empty text
    if not pages_content.strip() or len(pages_content.strip()) < 200:
        logger.warning(f"Skipping {filename} — no valid text detected after extraction.")
        return []

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