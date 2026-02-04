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

def is_gibberish(text: str) -> bool:
    """
    Detect if text is gibberish (reversed text, random characters, etc.)
    Returns True if the text appears to be garbage.
    """
    import re
    
    if not text or len(text) < 5:
        return False
    
    # Check 1: Too many consecutive consonants (gibberish pattern)
    # Real English rarely has 5+ consonants in a row
    consonant_pattern = r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}'
    if re.search(consonant_pattern, text):
        # Check if it might be an acronym (all caps, short)
        if not (text.isupper() and len(text) < 10):
            return True
    
    # Check 2: Very low vowel ratio (gibberish has few vowels)
    vowels = sum(1 for c in text.lower() if c in 'aeiou')
    letters = sum(1 for c in text if c.isalpha())
    if letters > 10 and vowels / letters < 0.15:  # Less than 15% vowels
        return True
    
    # Check 3: Check if it's reversed text (common PDF issue)
    # Reversed text often has unusual letter patterns at start/end
    reversed_text = text[::-1]
    # Simple heuristic: if reversed version has more common word patterns
    common_starts = ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out']
    original_score = sum(1 for word in common_starts if word in text.lower())
    reversed_score = sum(1 for word in common_starts if word in reversed_text.lower())
    if reversed_score > original_score + 2 and len(text) > 15:
        return True  # Likely reversed text
    
    return False


def clean_gibberish_from_text(text: str) -> str:
    """Remove gibberish words and reversed text from extracted PDF text."""
    import re
    
    if not text:
        return ""
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Check if entire line is gibberish
        if is_gibberish(line.strip()):
            continue
        
        # Check individual words for gibberish (for mixed lines)
        words = line.split()
        cleaned_words = []
        for word in words:
            # Keep short words, check longer ones for gibberish
            if len(word) <= 4 or not is_gibberish(word):
                cleaned_words.append(word)
        
        if cleaned_words:
            cleaned_lines.append(' '.join(cleaned_words))
    
    return '\n'.join(cleaned_lines)


def fix_word_spacing(text: str) -> str:
    """
    Fix common word spacing issues from OCR/PDF extraction:
    - Split joined words: "theworld" → "the world"  
    - Join broken words: "th e" → "the", "don t" → "don't"
    - Fix hyphenation across lines: "administra-\ntion" → "administration"
    """
    import re
    
    if not text:
        return ""
    
    # Common English words for detection (expanded list)
    COMMON_WORDS = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 
        'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may',
        'new', 'now', 'old', 'see', 'way', 'who', 'did', 'get', 'let', 'put',
        'say', 'she', 'too', 'use', 'been', 'from', 'have', 'into', 'make',
        'than', 'that', 'them', 'then', 'this', 'what', 'when', 'will', 'with',
        'would', 'about', 'after', 'being', 'could', 'first', 'found', 'great',
        'india', 'indian', 'water', 'river', 'land', 'soil', 'forest', 'climate',
        'region', 'area', 'state', 'country', 'world', 'national', 'development',
        'resource', 'agriculture', 'industry', 'population', 'environment',
        'government', 'economic', 'social', 'political', 'cultural', 'natural'
    }
    
    # Step 1: Fix hyphenation across lines (administra-\ntion → administration)
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    # Also fix mid-line hyphenation: "administra- tion" → "administration"  
    text = re.sub(r'(\w+)-\s+(\w+)', lambda m: m.group(1) + m.group(2) if len(m.group(2)) > 2 else m.group(0), text)
    
    # Step 2: Fix common broken contractions
    contractions = [
        (r"\bdon\s+t\b", "don't"),
        (r"\bwon\s+t\b", "won't"),
        (r"\bcan\s+t\b", "can't"),
        (r"\bdidn\s+t\b", "didn't"),
        (r"\bdoesn\s+t\b", "doesn't"),
        (r"\bisn\s+t\b", "isn't"),
        (r"\baren\s+t\b", "aren't"),
        (r"\bweren\s+t\b", "weren't"),
        (r"\bwasn\s+t\b", "wasn't"),
        (r"\bhasn\s+t\b", "hasn't"),
        (r"\bhaven\s+t\b", "haven't"),
        (r"\bcouldn\s+t\b", "couldn't"),
        (r"\bwouldn\s+t\b", "wouldn't"),
        (r"\bshouldn\s+t\b", "shouldn't"),
        (r"\bi\s+m\b", "I'm"),
        (r"\bi\s+ve\b", "I've"),
        (r"\bi\s+ll\b", "I'll"),
        (r"\bit\s+s\b", "it's"),
        (r"\bthat\s+s\b", "that's"),
        (r"\bwhat\s+s\b", "what's"),
        (r"\bthere\s+s\b", "there's"),
        (r"\bwho\s+s\b", "who's"),
        (r"\blet\s+s\b", "let's"),
    ]
    for pattern, replacement in contractions:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Step 3: Fix single-letter broken words (th e → the, fo r → for)
    # Pattern: single letter + space + rest of word that makes a common word
    def fix_broken_word(match):
        full = match.group(1) + match.group(2)
        if full.lower() in COMMON_WORDS:
            return full
        return match.group(0)  # Return original if not a word
    
    # Fix "a bc" → "abc" patterns if result is a word
    text = re.sub(r'\b([a-zA-Z])\s+([a-zA-Z]{2,})\b', fix_broken_word, text)
    # Fix "ab c" → "abc" patterns  
    text = re.sub(r'\b([a-zA-Z]{2,})\s+([a-zA-Z])\b', lambda m: m.group(1) + m.group(2) if (m.group(1) + m.group(2)).lower() in COMMON_WORDS else m.group(0), text)
    
    # Step 4: Fix common OCR character confusions
    ocr_fixes = [
        (r'\brn\b', 'm'),  # "rn" alone → "m"
        (r'([a-z])rn([a-z])', r'\1m\2'),  # "arn" in word → "am"
        (r'([a-z])vv([a-z])', r'\1w\2'),  # "vv" → "w"
        (r'\bI\s+n\s+d\s+i\s+a\b', 'India'),  # Spaced out "India"
        (r'\b([A-Z])\s+([a-z])', r'\1\2'),  # "T he" → "The" (capital + space + lower)
    ]
    for pattern, replacement in ocr_fixes:
        text = re.sub(pattern, replacement, text)
    
    # Step 5: Split obvious joined words (limited to avoid false positives)
    def split_joined_words(text):
        """Split commonly joined words like 'theworld' → 'the world'"""
        # Only split if we find common word at start followed by another word-like pattern
        patterns = [
            (r'\b(the)([A-Z][a-z]+)\b', r'\1 \2'),  # theWorld → the World
            (r'\b(and)([A-Z][a-z]+)\b', r'\1 \2'),  # andThe → and The
            (r'\b(for)([A-Z][a-z]+)\b', r'\1 \2'),  # forThe → for The
            (r'\b(with)([A-Z][a-z]+)\b', r'\1 \2'), # withThe → with The
            (r'\b(from)([A-Z][a-z]+)\b', r'\1 \2'), # fromThe → from The
            (r'\b(this)([A-Z][a-z]+)\b', r'\1 \2'), # thisIs → this Is
            (r'\b(that)([A-Z][a-z]+)\b', r'\1 \2'), # thatIs → that Is
        ]
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text
    
    text = split_joined_words(text)
    
    # Step 6: Clean up extra spaces that might have been introduced
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n ', '\n', text)  # Remove space after newline
    text = re.sub(r' \n', '\n', text)  # Remove space before newline
    
    return text


def fix_common_ocr_errors(text: str) -> str:
    """
    Fix common OCR misreads that create nonsense words.
    """
    import re
    
    if not text:
        return ""
    
    # Common OCR character confusions (word-level fixes)
    word_fixes = {
        # Common misreads
        'rnany': 'many',
        'sorne': 'some', 
        'tirne': 'time',
        'clirnate': 'climate',
        'developrnent': 'development',
        'governrnent': 'government',
        'environrnent': 'environment',
        'movernent': 'movement',
        'rnovement': 'movement',
        'rnountain': 'mountain',
        'rnonth': 'month',
        'rnain': 'main',
        'rnake': 'make',
        'rnade': 'made',
        'frorn': 'from',
        'thern': 'them',
        'vvater': 'water',
        'vvorld': 'world',
        'vvith': 'with',
        'vvhere': 'where',
        'vvhat': 'what',
        'vvhen': 'when',
        'vvhich': 'which',
        'vvhy': 'why',
        'nurnber': 'number',
        'rnernber': 'member',
        'rernainder': 'remainder',
        'assernbly': 'assembly',
        'problern': 'problem',
        'systern': 'system',
        'rnillion': 'million',
        # "l" and "1" confusion
        'l00': '100',
        'l0': '10',
        'lndia': 'India',
        'lndian': 'Indian',
    }
    
    # Apply word-level fixes (case-insensitive, preserve case)
    for wrong, right in word_fixes.items():
        # Match whole words only
        pattern = r'\b' + re.escape(wrong) + r'\b'
        text = re.sub(pattern, right, text, flags=re.IGNORECASE)
    
    # Fix patterns where 'rn' appears where 'm' should be (within words)
    # Only fix if result looks more like a word
    def fix_rn_to_m(match):
        word = match.group(0)
        fixed = word.replace('rn', 'm')
        # Simple heuristic: if fixed version has better letter distribution, use it
        # Count vowels - real words typically have ~40% vowels
        orig_vowels = sum(1 for c in word.lower() if c in 'aeiou')
        fixed_vowels = sum(1 for c in fixed.lower() if c in 'aeiou')
        if len(word) > 4:
            orig_ratio = orig_vowels / len(word) 
            fixed_ratio = fixed_vowels / len(fixed)
            # If fixed version has better vowel ratio (closer to 0.35-0.45), use it
            if abs(fixed_ratio - 0.4) < abs(orig_ratio - 0.4):
                return fixed
        return word
    
    # Look for words with 'rn' that might be 'm'
    text = re.sub(r'\b\w*rn\w*\b', fix_rn_to_m, text)
    
    return text


def clean_text(text: str) -> str:
    """
    Clean extracted text to handle common PDF/OCR issues and remove noise.
    
    Pipeline:
    1. Remove gibberish/reversed text
    2. Remove control characters
    3. Fix word spacing and hyphenation
    4. Fix common OCR character errors
    5. Remove noise and special symbols
    """
    import re
    import unicodedata
    
    if not text:
        return ""
    
    # Step 0: Remove gibberish and reversed text first
    text = clean_gibberish_from_text(text)
    
    # Step 1: Remove control characters and non-printable characters (except newlines and tabs)
    cleaned = []
    for char in text:
        if char == '\n' or char == '\t':
            cleaned.append(char)
        elif char.isspace():
            cleaned.append(' ')  # Normalize all whitespace to space
        elif unicodedata.category(char)[0] != 'C':  # Not a control character
            cleaned.append(char)
    text = ''.join(cleaned)
    
    # Step 2: Fix word spacing issues (broken words, hyphenation, contractions)
    text = fix_word_spacing(text)
    
    # Step 3: Fix common OCR character errors (rn→m, vv→w, etc.)
    text = fix_common_ocr_errors(text)
    
    # Step 4: Remove excessive special symbols and decorative characters
    # Keep: letters, numbers, spaces, and common punctuation
    text = re.sub(r'[^\w\s\.\,\;\:\!\?\-\_\(\)\[\]\{\}\"\'\`\/\\\|\=\+\<\>\@\#\$\%\&\*\~\n\t]', ' ', text)
    
    # Step 5: Remove sequences of special characters (likely noise)
    text = re.sub(r'[^\w\s]{3,}', ' ', text)  # Remove 3+ consecutive special chars
    
    # Step 6: Remove excessive whitespace and normalize
    text = re.sub(r' +', ' ', text)  # Multiple spaces to single space
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to max 2
    
    # Step 7: Remove lines that are mostly special characters or very short noise
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
            continue
        
        # Skip very short lines that are just symbols
        if len(line_stripped) < 3 and not any(c.isalnum() for c in line_stripped):
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Step 8: Final cleanup
    text = text.strip()
    
    # Step 9: Remove excessive repeated characters (keep III for Roman numerals)
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
                    # If tables exist, format them properly (but skip gibberish tables)
                    for table in tables:
                        if table:
                            # Convert table to formatted text
                            table_text = "\n".join(
                                " | ".join(str(cell) if cell else "" for cell in row)
                                for row in table
                            )
                            # Skip tables that are mostly gibberish
                            if not is_gibberish(table_text) and len(table_text.strip()) > 10:
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