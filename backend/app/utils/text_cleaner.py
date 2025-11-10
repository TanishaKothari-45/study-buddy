"""
Advanced text cleaning utilities for PDF and TXT files
Removes images, noise, headers/footers, and improves text quality
"""

import re
import unicodedata
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Common patterns for image placeholders and OCR artifacts
IMAGE_PATTERNS = [
    r'\[IMAGE\]', r'\[PICTURE\]', r'\[FIGURE\]', r'\[DIAGRAM\]',
    r'Image\s+\d+', r'Figure\s+\d+', r'Picture\s+\d+',
    r'^\s*\[.*?\]\s*$',  # Lines that are just brackets (image placeholders)
]

# Common header/footer patterns
HEADER_FOOTER_PATTERNS = [
    r'^\d+\s*$',  # Page numbers (standalone numbers)
    r'^Page\s+\d+\s+of\s+\d+$',  # Page X of Y
    r'^Chapter\s+\d+.*?Page\s+\d+$',  # Chapter X Page Y
]

# Copyright and legal text patterns
COPYRIGHT_PATTERNS = [
    r'©\s*\d{4}.*?',
    r'Copyright\s+\d{4}.*?',
    r'All rights reserved.*?',
    r'Published by.*?',
    r'ISBN.*?',
]

def remove_image_placeholders(text: str) -> str:
    """Remove image placeholders and OCR artifacts from images"""
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        # Skip lines that match image patterns
        is_image = False
        for pattern in IMAGE_PATTERNS:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                is_image = True
                break
        
        if is_image:
            continue
        
        # Skip lines that are mostly brackets or special chars (likely image OCR)
        if re.match(r'^[\s\[\]\(\)\{\}\-\+\*\#\@]{5,}$', line_stripped):
            continue
        
        # Skip lines with excessive punctuation (likely OCR noise from images)
        punct_ratio = sum(1 for c in line_stripped if not c.isalnum() and not c.isspace()) / len(line_stripped) if line_stripped else 0
        if len(line_stripped) > 10 and punct_ratio > 0.7:
            continue
        
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def remove_headers_footers(text: str, pages_content: List[Dict[str, Any]] = None) -> str:
    """Remove repeating headers and footers across pages"""
    if not pages_content or len(pages_content) < 3:
        # Not enough pages to detect patterns, just remove common patterns
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line_stripped = line.strip()
            # Skip common header/footer patterns
            skip = False
            for pattern in HEADER_FOOTER_PATTERNS:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    skip = True
                    break
            if not skip:
                cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)
    
    # Detect repeating lines across pages (likely headers/footers)
    page_texts = [page.get("text", "") for page in pages_content if page.get("text")]
    if len(page_texts) < 2:
        return text
    
    # Count line occurrences across pages
    line_counts = {}
    for page_text in page_texts:
        lines = page_text.split('\n')
        seen_in_page = set()
        for line in lines:
            line_stripped = line.strip()
            if len(line_stripped) > 3 and len(line_stripped) < 100:  # Reasonable header/footer length
                if line_stripped not in seen_in_page:
                    line_counts[line_stripped] = line_counts.get(line_stripped, 0) + 1
                    seen_in_page.add(line_stripped)
    
    # Lines that appear on most pages are likely headers/footers
    threshold = max(2, len(page_texts) * 0.5)  # Appear on at least 50% of pages
    header_footer_lines = {line: count for line, count in line_counts.items() if count >= threshold}
    
    if header_footer_lines:
        logger.info(f"   🧹 Detected {len(header_footer_lines)} header/footer lines to remove")
        for line in list(header_footer_lines.keys())[:5]:  # Log first 5
            logger.debug(f"      - '{line[:50]}...' (appears {header_footer_lines[line]} times)")
    
    # Remove header/footer lines from text
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped in header_footer_lines:
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def remove_copyright_notices(text: str) -> str:
    """Remove copyright notices and legal text"""
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        skip = False
        
        # Check copyright patterns
        for pattern in COPYRIGHT_PATTERNS:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                skip = True
                break
        
        if not skip:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def remove_urls_and_emails(text: str) -> str:
    """Remove URLs and email addresses (often noise in PDFs)"""
    # Remove URLs
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    # Remove emails
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
    return text

def clean_text_advanced(text: str, pages_content: List[Dict[str, Any]] = None) -> str:
    """
    Comprehensive text cleaning for PDFs and TXT files.
    Removes images, noise, headers/footers, and improves quality.
    """
    if not text:
        return ""
    
    original_length = len(text)
    
    # Step 1: Remove image placeholders and OCR artifacts
    text = remove_image_placeholders(text)
    
    # Step 2: Remove URLs and emails (often noise)
    text = remove_urls_and_emails(text)
    
    # Step 3: Remove copyright notices
    text = remove_copyright_notices(text)
    
    # Step 4: Remove headers and footers (if pages_content provided)
    if pages_content:
        text = remove_headers_footers(text, pages_content)
    
    # Step 5: Remove decorative Unicode characters (circled numbers, enclosed alphanumerics, etc.)
    # Remove: ①②③④⑤⑥⑦⑧⑨⑩ (enclosed numbers)
    # Remove: ❹❽❼➃➃➅➈ (circled numbers, various Unicode ranges)
    # Remove: Other decorative/symbol characters
    text = re.sub(r'[\u2460-\u2473\u24B6-\u24E9\u2776-\u2793\u24EA-\u24FF]', '', text)  # Enclosed alphanumerics
    text = re.sub(r'[\u2780-\u27BF]', '', text)  # Dingbats
    text = re.sub(r'[\u2776-\u2793]', '', text)  # Dingbat circled numbers
    text = re.sub(r'[\u24B6-\u24E9]', '', text)  # Circled letters
    text = re.sub(r'[\u2460-\u2473]', '', text)  # Circled numbers 1-20
    text = re.sub(r'[\u24EA-\u24FF]', '', text)  # More circled numbers
    text = re.sub(r'[\u2776-\u2793]', '', text)  # Dingbat numbers
    # Remove other decorative Unicode ranges
    text = re.sub(r'[\u2600-\u26FF]', '', text)  # Miscellaneous Symbols
    text = re.sub(r'[\u2700-\u27BF]', '', text)  # Dingbats
    text = re.sub(r'[\uFE00-\uFE0F]', '', text)  # Variation Selectors
    
    # Step 6: Remove null bytes and control characters explicitly
    # Remove ALL null bytes (multiple passes to catch all)
    while '\x00' in text:
        text = text.replace('\x00', '')
    while '\u0000' in text:
        text = text.replace('\u0000', '')
    # Remove all control characters except newline, tab, carriage return
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # Step 6b: Fix common OCR misreads
    text = text.replace('þ', 'th')  # Replace thorn with 'th'
    text = text.replace('Þ', 'Th')  # Capital thorn
    
    # Step 6c: Remove control characters and non-printable characters
    cleaned = []
    for char in text:
        if char == '\n' or char == '\t':
            cleaned.append(char)
        elif char.isspace():
            cleaned.append(' ')
        elif unicodedata.category(char)[0] != 'C':  # Not a control character
            # Also skip symbols that are decorative (So category but not standard punctuation)
            cat = unicodedata.category(char)
            if cat.startswith('So'):  # Symbol, other
                # Keep only common symbols, skip decorative ones
                if char in '.,;:!?-()[]{}\'"`/\\|=+<>@#$%&*~':
                    cleaned.append(char)
                # Skip decorative symbols
                continue
            cleaned.append(char)
    text = ''.join(cleaned)
    
    # Step 7: Remove excessive special symbols - keep only standard punctuation
    text = re.sub(r'[^\w\s\.\,\;\:\!\?\-\_\(\)\[\]\{\}\"\'\`\/\\\|\=\+\<\>\@\#\$\%\&\*\~\n\t]', ' ', text)
    
    # Step 8: Remove sequences of special characters (likely noise)
    text = re.sub(r'[^\w\s]{3,}', ' ', text)
    
    # Step 9: Remove single character repetitions (like "s s s s s s s")
    text = re.sub(r'\b(\w)\s+(?:\1\s+){2,}', r'\1 ', text)  # Remove "s s s s s" → "s "
    text = re.sub(r'\b([a-zA-Z])\s+(?:\1\s+)+', r'\1 ', text)  # Remove repeated single chars
    
    # Step 10: Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 newlines
    
    # Step 11: Remove lines that are mostly noise
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
        
        # Skip lines that are just numbers (likely page numbers that weren't caught)
        if re.match(r'^\d+$', line_stripped):
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Step 13: Fix common OCR issues
    text = text.replace('II', 'I').replace('EE', 'E').replace('aa', 'a')
    
    # Step 14: Remove excessive repeated characters
    text = re.sub(r'(.)\1{3,}', r'\1\1\1', text)  # Max 3 repetitions
    
    # Step 15: Remove lines with mostly single characters separated by spaces (noise pattern)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        words = line.split()
        # Skip lines that are mostly single-character "words" (likely noise)
        if len(words) > 5:
            single_char_words = sum(1 for w in words if len(w) == 1 and w.isalpha())
            if single_char_words / len(words) > 0.7:  # More than 70% single chars
                continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    
    # Step 16: Final cleanup
    text = text.strip()
    
    cleaned_length = len(text)
    if original_length > 0:
        reduction_pct = ((original_length - cleaned_length) / original_length) * 100
        logger.debug(f"   🧹 Text cleaning: {original_length} → {cleaned_length} chars ({reduction_pct:.1f}% reduction)")
    
    return text

def improve_chunk_quality(chunks: List[str], min_words: int = 20, max_words: int = 1500) -> List[str]:
    """
    Improve chunk quality by:
    - Removing very short chunks
    - Ensuring chunks don't start/end mid-sentence
    - Merging tiny chunks with neighbors
    - NEVER exceeding max_words limit (to prevent truncation in embedder)
    """
    if not chunks:
        return []
    
    improved_chunks = []
    
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        
        # Remove chunks that are too short
        word_count = len(chunk.split())
        if word_count < min_words:
            # Try to merge with next chunk if available
            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1].strip()
                if next_chunk:
                    merged = chunk + " " + next_chunk
                    merged_word_count = len(merged.split())
                    # Only merge if it doesn't exceed max_words
                    if merged_word_count >= min_words and merged_word_count <= max_words:
                        improved_chunks.append(merged)
                        chunks[i + 1] = ""  # Mark as merged
                        continue
            # Skip if can't merge
            continue
        
        # Ensure chunk doesn't start mid-sentence (starts with lowercase)
        if chunk and chunk[0].islower() and improved_chunks:
            # Merge with previous chunk ONLY if it won't exceed max_words
            prev_chunk = improved_chunks[-1]
            merged = prev_chunk + " " + chunk
            merged_word_count = len(merged.split())
            if merged_word_count <= max_words:
                improved_chunks[-1] = merged
                continue
            # If merge would exceed limit, keep chunks separate
            # (better to have mid-sentence split than exceed token limit)
        
        # Ensure chunk doesn't end mid-sentence (ends without punctuation)
        if chunk and not chunk[-1] in '.!?;:' and i < len(chunks) - 1:
            next_chunk = chunks[i + 1].strip()
            if next_chunk and next_chunk[0].islower():
                # Merge with next chunk ONLY if it won't exceed max_words
                merged = chunk + " " + next_chunk
                merged_word_count = len(merged.split())
                if merged_word_count <= max_words:
                    improved_chunks.append(merged)
                    chunks[i + 1] = ""  # Mark as merged
                    continue
                # If merge would exceed limit, keep chunks separate
        
        # If chunk itself exceeds max_words, split it (shouldn't happen, but safety check)
        if word_count > max_words:
            logger.warning(f"⚠️ Chunk {i+1} has {word_count} words (exceeds {max_words}), splitting...")
            words = chunk.split()
            # Split into multiple chunks
            for split_idx in range(0, word_count, max_words - 50):  # 50 word overlap
                split_chunk = " ".join(words[split_idx:split_idx + max_words])
                if len(split_chunk.split()) >= min_words:
                    improved_chunks.append(split_chunk)
            continue
        
        improved_chunks.append(chunk)
    
    # Final pass: remove empty chunks and verify all are under max_words
    final_chunks = []
    for chunk in improved_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        word_count = len(chunk.split())
        if word_count > max_words:
            logger.error(f"❌ CRITICAL: Chunk still exceeds {max_words} words ({word_count}), splitting...")
            words = chunk.split()
            for split_idx in range(0, word_count, max_words - 50):
                split_chunk = " ".join(words[split_idx:split_idx + max_words])
                if len(split_chunk.split()) >= min_words:
                    final_chunks.append(split_chunk)
        else:
            final_chunks.append(chunk)
    
    return final_chunks

