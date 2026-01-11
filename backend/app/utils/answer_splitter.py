"""
Answer Splitter Utility
Detects answer boundaries in PDFs using regex patterns and splits into answer chunks.
Supports UPSC standard format: 2 pages for Q1-10 (10 markers), 3 pages for Q11-20 (15 markers).
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import fitz  # PyMuPDF

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not available, using PyMuPDF only")

logger = logging.getLogger(__name__)

# UPSC-specific patterns for detecting answer/question boundaries
ANSWER_BOUNDARY_PATTERNS = [
    # 1., 2., 12., etc. (most common UPSC format)
    r'^\s*(\d+)[\.\)]\s+',
    # Q1), Q2), q1), etc.
    r'^\s*[Qq]\s*(\d+)\)\s*',
    # Q1, Q2, Q3, etc.
    r'^\s*Q\s*(\d+)[\.\)\:\-]?\s*',
    # Question 1, Question 2, etc.
    r'^\s*Question\s+(\d+)[\.\)\:\-]?\s*',
    # Q.1, Q.2, etc.
    r'^\s*Q\.\s*(\d+)[\.\)\:\-]?\s*',
    # (1), (2), (3) at start of line
    r'^\s*\((\d+)\)\s+',
]

# Directive keywords (used softly - to detect but not reject)
DIRECTIVE_KEYWORDS = [
    "analyse", "discuss", "examine", "evaluate", "assess",
    "explain", "elucidate", "account", "identify", "outline",
    "describe", "comment", "critically", "critically examine",
    "compare", "contrast", "justify", "illustrate", "narrate"
]

# Marks detection patterns
MARKS_PATTERNS = [
    r'\b(10|15)\s*(marks?|mark|मार्क्स?)?\b',
    r'\b(10|15)\s*$',  # Just "10" or "15" at end of line
    r'\((\d+)\s*marks?\)',  # (10 marks) or (15 marks)
]


def contains_directive(text: str) -> bool:
    """
    Check if text contains directive keywords.
    Used softly - helps detect but doesn't reject if absent.
    """
    t = text.lower()
    return any(d in t for d in DIRECTIVE_KEYWORDS)


def is_likely_answer_start(line: str) -> bool:
    """
    Filters out false positives:
    - Very short numbered fragments
    - Lowercase continuation bullets inside answers
    - Internal list items
    
    Accepts if:
    - Contains directive keyword OR
    - Starts with capital letter after number
    """
    line = line.strip()
    
    # Reject very short numbered fragments
    if len(line) < 8:
        return False
    
    # Reject lowercase continuation bullets like "1. causes are..."
    if re.match(r'^\s*\d+[\.\)]\s+[a-z]', line):
        return False
    
    # Accept if directive present (soft check - helps but not required)
    if contains_directive(line):
        return True
    
    # Accept if capital letter start (UPSC answers usually start capitalized)
    # Pattern: optional bracket, number, optional dot/paren, space, capital letter
    if re.match(r'^\s*[\(\[]?\d+[\.\)]?\s*[A-Z]', line):
        return True
    
    # Also accept if it's a clear question number pattern at start
    # Even without capital, if it's clearly a question boundary
    if re.match(r'^\s*(\d+)[\.\)]\s+', line) and len(line) > 15:
        # If line is substantial and starts with number, likely a question
        return True
    
    return False


def detect_marks_near_question(lines: List[str], question_line_idx: int) -> Optional[int]:
    """
    Detect marks indicators (10 or 15) near a question line.
    Looks within 3-5 lines before and after the question line.
    
    Args:
        lines: List of text lines from the page
        question_line_idx: Index of the line containing the question number
    
    Returns:
        Detected marks (10 or 15) or None
    """
    # Search window: 3 lines before to 5 lines after
    start_idx = max(0, question_line_idx - 3)
    end_idx = min(len(lines), question_line_idx + 6)
    
    search_lines = lines[start_idx:end_idx]
    search_text = " ".join(search_lines).lower()
    
    for pattern in MARKS_PATTERNS:
        match = re.search(pattern, search_text, re.IGNORECASE)
        if match:
            marks_str = match.group(1) if match.lastindex >= 1 else match.group(0)
            try:
                marks = int(marks_str)
                if marks in [10, 15]:
                    logger.debug(f"Detected {marks} marks near question at line {question_line_idx + 1}")
                    return marks
            except ValueError:
                continue
    
    return None

def extract_text_from_page(pdf_path: str, page_num: int, use_pdfplumber: bool = True) -> str:
    """
    Extract text from a specific page of PDF.
    Tries pdfplumber first (better for structured text), falls back to PyMuPDF.
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        use_pdfplumber: Whether to try pdfplumber first (default: True)
    
    Returns:
        Extracted text from the page
    """
    try:
        # Try pdfplumber first (better text extraction)
        if use_pdfplumber and PDFPLUMBER_AVAILABLE:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    if page_num < len(pdf.pages):
                        page = pdf.pages[page_num]
                        text = page.extract_text()
                        if text:
                            return text.strip()
            except Exception as e:
                logger.debug(f"pdfplumber extraction failed for page {page_num + 1}, using PyMuPDF: {e}")
        
        # Fallback to PyMuPDF
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return ""
        
        page = doc[page_num]
        text = page.get_text("text")
        doc.close()
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from page {page_num}: {e}")
        return ""

def detect_answer_boundaries(
    pdf_path: str, 
    use_standard_format: bool = False,
    question_file_path: Optional[str] = None,
    question_texts: Optional[List[str]] = None
) -> List[Dict[str, int]]:
    """
    Detect answer boundaries in PDF using regex patterns with critical guards.
    Falls back to UPSC standard format if patterns not found.
    
    Args:
        pdf_path: Path to PDF file
        use_standard_format: If True, use UPSC standard (2 pages for Q1-10, 3 for Q11-20)
    
    Returns:
        List of dicts: [{"start_page": int, "q_num": int, "marks": Optional[int]}]
        Pages are 0-indexed. Preserves actual question numbers (not sequential).
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()
        
        logger.info(f"📄 Detecting answer boundaries in PDF with {total_pages} pages...")
        
        # Extract question texts from reference if provided
        reference_questions = []
        if question_file_path and Path(question_file_path).exists():
            logger.info(f"📋 Extracting questions from reference file: {question_file_path}")
            try:
                file_ext = Path(question_file_path).suffix.lower()
                is_pdf = file_ext == '.pdf'
                
                if is_pdf:
                    # PDF: Get total pages and extract from multiple pages
                    q_doc = fitz.open(question_file_path)
                    q_total_pages = len(q_doc)
                    q_doc.close()
                    
                    # Extract text from question file (try first few pages)
                    for page_idx in range(min(5, q_total_pages)):  # Check first 5 pages
                        question_text = extract_text_from_page(question_file_path, page_idx, use_pdfplumber=True)
                        if question_text:
                            # Try to extract question numbers and texts
                            lines = [l.strip() for l in question_text.split("\n") if l.strip()]
                            for line in lines:
                                for pattern in ANSWER_BOUNDARY_PATTERNS:
                                    match = re.match(pattern, line, re.IGNORECASE)
                                    if match:
                                        # Extract question text (everything after the number)
                                        q_text = re.sub(pattern, '', line, count=1, flags=re.IGNORECASE).strip()
                                        if q_text and len(q_text) > 10:  # Substantial question text
                                            reference_questions.append(q_text)
                                            break
                            if reference_questions:
                                break  # Found questions, stop searching
                else:
                    # Image: Use PyMuPDF to convert image to PDF-like structure, then extract
                    # For images, extract_text_from_page with page 0 should work
                    try:
                        question_text = extract_text_from_page(question_file_path, 0, use_pdfplumber=False)  # Use PyMuPDF for images
                        if question_text:
                            lines = [l.strip() for l in question_text.split("\n") if l.strip()]
                            for line in lines:
                                for pattern in ANSWER_BOUNDARY_PATTERNS:
                                    match = re.match(pattern, line, re.IGNORECASE)
                                    if match:
                                        q_text = re.sub(pattern, '', line, count=1, flags=re.IGNORECASE).strip()
                                        if q_text and len(q_text) > 10:
                                            reference_questions.append(q_text)
                                            break
                    except Exception as img_err:
                        logger.warning(f"⚠️ Failed to extract text from image question file: {img_err}")
                        # Try using pdfplumber if it supports images (it might not, but worth trying)
                        try:
                            question_text = extract_text_from_page(question_file_path, 0, use_pdfplumber=True)
                            if question_text:
                                lines = [l.strip() for l in question_text.split("\n") if l.strip()]
                                for line in lines:
                                    for pattern in ANSWER_BOUNDARY_PATTERNS:
                                        match = re.match(pattern, line, re.IGNORECASE)
                                        if match:
                                            q_text = re.sub(pattern, '', line, count=1, flags=re.IGNORECASE).strip()
                                            if q_text and len(q_text) > 10:
                                                reference_questions.append(q_text)
                                                break
                        except:
                            pass
                
                logger.info(f"✅ Extracted {len(reference_questions)} questions from reference file ({'PDF' if is_pdf else 'Image'})")
            except Exception as e:
                logger.warning(f"⚠️ Failed to extract questions from reference file: {e}")
        
        if question_texts:
            reference_questions = [q.strip() for q in question_texts if q.strip()]
            logger.info(f"📋 Using {len(reference_questions)} manually provided questions")
        
        # Extract text from pages to detect boundaries
        boundary_hits = []
        
        for page_num in range(total_pages):
            text = extract_text_from_page(pdf_path, page_num, use_pdfplumber=True)
            if not text:
                continue
            
            # Split into lines and filter empty
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue
            
            # --- SMART LINE SAMPLING ---
            # Top 15 lines (question area) + sparse mid-page scan (every 3rd line from 15-60)
            scan_lines = lines[:15] + (lines[15:60:3] if len(lines) > 15 else [])
            
            # Track which lines we've already checked to avoid duplicates
            checked_lines = set()
            
            for line in scan_lines:
                # Skip if already checked
                line_hash = hash(line)
                if line_hash in checked_lines:
                    continue
                checked_lines.add(line_hash)
                
                # Try each pattern
                for pattern in ANSWER_BOUNDARY_PATTERNS:
                    match = re.match(pattern, line, re.IGNORECASE)
                    if not match:
                        continue
                    
                    q_num = int(match.group(1))
                    
                    # CRITICAL: Apply guards to filter false positives
                    if not is_likely_answer_start(line):
                        logger.debug(f"Rejected false positive at page {page_num + 1}, line: {line[:50]}...")
                        continue
                    
                    # Detect marks nearby
                    line_idx = lines.index(line) if line in lines else len(lines) // 2
                    
                    # If we have reference questions, try to match this question number
                    # This helps validate the detection
                    if reference_questions and q_num <= len(reference_questions):
                        # Get surrounding text to check for question match
                        context_start = max(0, line_idx - 2)
                        context_end = min(len(lines), line_idx + 10)
                        context_text = " ".join(lines[context_start:context_end]).lower()
                        ref_question = reference_questions[q_num - 1].lower()
                        
                        # Soft match: check if key words from reference question appear in context
                        ref_words = set(ref_question.split())
                        context_words = set(context_text.split())
                        common_words = ref_words.intersection(context_words)
                        
                        # If significant overlap (at least 3 common words or 30% match), it's likely correct
                        match_ratio = len(common_words) / max(len(ref_words), 1)
                        if len(common_words) < 3 and match_ratio < 0.3:
                            logger.debug(f"⚠️ Question {q_num} at page {page_num + 1} doesn't match reference question well")
                            # Still accept but log warning
                        else:
                            logger.debug(f"✅ Question {q_num} matches reference question ({(match_ratio * 100):.0f}% match)")
                    marks = detect_marks_near_question(lines, line_idx)
                    
                    boundary_hits.append({
                        "start_page": page_num,
                        "q_num": q_num,
                        "marks": marks
                    })
                    
                    logger.info(f"✅ Found answer boundary at page {page_num + 1}: Q{q_num}" + 
                              (f" ({marks} marks)" if marks else "") +
                              (f" [matched reference]" if reference_questions and q_num <= len(reference_questions) else ""))
                    break  # Stop after first valid match per line
                else:
                    continue
                break  # Stop after processing this line
        
        # ---------- FALLBACK LOGIC ----------
        if not boundary_hits:
            if use_standard_format or total_pages >= 20:
                logger.info("📋 Using UPSC standard format: 2 pages for Q1-10, 3 pages for Q11-20")
                return _detect_upsc_standard_format_dict(total_pages)
            
            # Last resort: single answer
            logger.warning("⚠️ No answer boundaries detected. Treating as single answer.")
            return [{
                "start_page": 0,
                "q_num": 1,
                "marks": None
            }]
        
        # ---------- SORT & DEDUPE ----------
        # Sort by page number first, then by question number
        boundary_hits.sort(key=lambda x: (x["start_page"], x["q_num"]))
        
        # Remove duplicates (same page, same question number)
        deduped = []
        seen = set()
        for hit in boundary_hits:
            key = (hit["start_page"], hit["q_num"])
            if key not in seen:
                deduped.append(hit)
                seen.add(key)
        
        # Validate question order (warn if non-sequential but don't reject)
        if len(deduped) > 1:
            q_nums = [h["q_num"] for h in deduped]
            if q_nums != sorted(q_nums):
                logger.warning(f"⚠️ Non-sequential question numbers detected: {q_nums}")
                logger.info("💡 Tip: Ensure PDF pages are in correct order")
        
        logger.info(f"✅ Detected {len(deduped)} answer boundaries")
        return deduped
        
    except Exception as e:
        logger.error(f"❌ Error detecting answer boundaries: {e}", exc_info=True)
        # Fallback: try UPSC standard format
        if use_standard_format:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            return _detect_upsc_standard_format_dict(total_pages)
        # Last resort: single chunk with all pages
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()
        return [{
            "start_page": 0,
            "q_num": 1,
            "marks": None
        }]


def _detect_upsc_standard_format_dict(total_pages: int) -> List[Dict[str, int]]:
    """
    Detect answers using UPSC standard format:
    - Q1-10: 2 pages each (10 markers)
    - Q11-20: 3 pages each (15 markers)
    
    Args:
        total_pages: Total number of pages in PDF
    
    Returns:
        List of dicts: [{"start_page": int, "q_num": int, "marks": Optional[int]}]
    """
    chunks = []
    current_page = 0
    
    # First 10 questions: 2 pages each (10 marks)
    for q_num in range(1, 11):
        if current_page >= total_pages:
            break
        chunks.append({
            "start_page": current_page,
            "q_num": q_num,
            "marks": 10
        })
        logger.info(f"📝 Answer {q_num} (10 marks): starting at page {current_page + 1}")
        current_page += 2
    
    # Next 10 questions: 3 pages each (15 marks)
    for q_num in range(11, 21):
        if current_page >= total_pages:
            break
        chunks.append({
            "start_page": current_page,
            "q_num": q_num,
            "marks": 15
        })
        logger.info(f"📝 Answer {q_num} (15 marks): starting at page {current_page + 1}")
        current_page += 3
    
    return chunks

def split_pdf_by_answers(
    pdf_path: str, 
    output_dir: str,
    use_standard_format: bool = False,
    question_file_path: Optional[str] = None,
    question_texts: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Split PDF into answer chunks and save each chunk as a separate PDF.
    Preserves actual question numbers from detection.
    
    Args:
        pdf_path: Path to input PDF
        output_dir: Directory to save split PDFs
        use_standard_format: If True, use UPSC standard format fallback
    
    Returns:
        List of dictionaries with answer metadata:
        [
            {
                "answer_id": "a1",
                "question_number": 5,  # Actual question number (not sequential)
                "start_page": 0,
                "end_page": 2,
                "file_path": "/path/to/a1.pdf",
                "num_pages": 3,
                "marks": 10  # Optional
            },
            ...
        ]
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Detect boundaries (returns List[Dict] with actual question numbers)
    boundary_hits = detect_answer_boundaries(
        pdf_path, 
        use_standard_format=use_standard_format,
        question_file_path=question_file_path,
        question_texts=question_texts
    )
    
    if not boundary_hits:
        logger.warning("⚠️ No answer chunks detected")
        return []
    
    # Enforce max 20 answers
    if len(boundary_hits) > 20:
        logger.warning(f"⚠️ Found {len(boundary_hits)} answers, limiting to 20")
        boundary_hits = boundary_hits[:20]
    
    # Get total pages to calculate end pages
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()
    
    logger.info(f"📦 Splitting PDF into {len(boundary_hits)} answer chunks...")
    
    answer_files = []
    
    try:
        doc = fitz.open(pdf_path)
        
        # Create answer chunks with end pages
        for idx, boundary in enumerate(boundary_hits):
            start_page = boundary["start_page"]
            q_num = boundary["q_num"]  # Use actual question number
            marks = boundary.get("marks")
            
            # Calculate end page: start of next answer - 1, or last page if this is last
            if idx + 1 < len(boundary_hits):
                end_page = boundary_hits[idx + 1]["start_page"] - 1
            else:
                end_page = total_pages - 1
            
            # Ensure end_page >= start_page
            if end_page < start_page:
                end_page = start_page
            
            answer_id = f"a{idx + 1}"
            num_pages = end_page - start_page + 1
            
            # Create new PDF with pages for this answer
            answer_doc = fitz.open()
            answer_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
            
            # Save answer PDF
            answer_file_path = output_path / f"{answer_id}.pdf"
            answer_doc.save(str(answer_file_path))
            answer_doc.close()
            
            answer_metadata = {
                "answer_id": answer_id,
                "question_number": q_num,  # Preserve actual question number
                "start_page": start_page,
                "end_page": end_page,
                "file_path": str(answer_file_path),
                "num_pages": num_pages
            }
            
            # Add marks if detected
            if marks:
                answer_metadata["marks"] = marks
            
            answer_files.append(answer_metadata)
            
            marks_str = f" ({marks} marks)" if marks else ""
            logger.info(f"✅ Created {answer_id}.pdf: Q{q_num}{marks_str}, pages {start_page + 1}-{end_page + 1} ({num_pages} pages)")
        
        doc.close()
        
        logger.info(f"✅ Successfully split PDF into {len(answer_files)} answer chunks")
        return answer_files
        
    except Exception as e:
        logger.error(f"❌ Error splitting PDF: {e}", exc_info=True)
        return []

