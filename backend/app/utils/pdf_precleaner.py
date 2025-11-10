"""
pdf_precleaner.py

------------------------------------------------------------

Removes only *obvious* garbage from PDFs before chunking:

- URLs, institute names, headers/footers, phone numbers, OCR noise

- Normalizes Unicode, trims whitespace

- Keeps *all* pages to avoid losing valuable content

"""

import re
import fitz  # PyMuPDF
import unicodedata
import logging
from typing import Union

try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ chardet not available. Install with: pip install chardet")

logger = logging.getLogger(__name__)

# === Comprehensive garbage patterns (no content-risk) ===

garbage_patterns = [
    # === UTF / OCR Encoding Artifacts ===
    r'ÿ[þth]*',                # UTF16 BOM or OCR variant (ÿþ, ÿth)
    r'\\u0000',                # literal null byte escapes
    r'\x00',                   # actual null byte
    r'[\x00-\x1F\x7F-\x9F]',   # invisible control chars
    r'—', r'–', r''', r''', r'"', r'"', r'•', r'…', r'→', r'←',  # fancy unicode symbols
    
    # === Broken / OCR URLs and Handles ===
    r'\b[hntpHTP]{3,5}s?[:：／\\\\]+[^\s]+',  # broken http/https/t.me OCR forms
    r'nttp\S*', r'htp\S*', r'vs://\S*',       # fake OCR URL starts
    r'ilttp\S*', r'ittp\S*', r'htt\S*',      # more broken URL variants
    r't\.me\S*', r'tme\S*', r'wa\.me\S*',    # Telegram / WhatsApp links (with OCR errors)
    r'facebook\.com/\S*', r'twitter\.com/\S*',
    r'instagram\.com/\S*', r'youtube\.com/\S*',
    r'Website\s+\S*',                        # OCR "Website …" lines
    r'www\s*[.,]',                           # broken www.
    r'https?://\S+',                         # normal URLs
    r'\bupscpdf', r'\btelegram', r'\bchannel',  # residual Telegram words
    r'\bnic\.in\b', r'\b\.gov\b', r'\b\.in\b', # domain fragments
    r'www\.[a-z0-9\-\.]+',                   # www URLs
    r'[A-Z]:\\[^\s]+',                       # Windows file paths
    r'UPSC[_-]?PDF', r'upsc[_-]?pdf',        # UPSC PDF references
    
    # === Coaching / Institute Branding ===
    r'visionias', r'gsscore', r'forumias', r'vajiram', r'insightsonindia',
    r'byjus', r'drishtiias', r'upscpathshala', r'unacademy', r'nextias',
    r'iasscore', r'civilsdaily', r'iasbaba', r'arihant', r'madeeasy',
    r'arihantpublications', r'arihantseries', r'compilation', r'handout',
    r'mentorship', r'coaching\s*institute', r'www\.ncert\.nic\.in',
    
    # === Headers / Footers / Boilerplate ===
    r'page\s*\d+(\s*of\s*\d+)?',
    r'(test\s*series|class\s*notes|study\s*material)',
    r'(current\s*affairs|monthly\s*magazine)',
    r'(module\s*\d+|paper\s*\d+|set\s*\d+)',
    r'\b(pdf|version|file|subject|exercise|chapter|unit|class)\b\s*[:\-\d]*',
    r'\b(2020|2021|2022|2023|2024|2025)\b',
    r'\bfig\.\s*\d+', r'\btable\s*\d+', r'\bdiagram\s*\d+', r'figure\s*\d+', r'\bchart\s*\d+',
    
    # === NCERT-Specific Noise Patterns ===
    r'\b\d{4}–\d{2}\b',                       # "2021–22", "2018–19" (year ranges)
    r'\bN\s*C\s*E\s*R\s*T\b',                 # "N C E R T" spaced out
    r'\bNational Council of Educational Research and Training\b',  # Full NCERT name
    r'\bResources\s+and\s+Development\b',     # Common NCERT footer text
    r'\bGeography\s+\d{4}–\d{2}\b',           # "Geography 2021–22"
    r'\bPage\s*\d+\b',                        # "Page 13" (standalone)
    r'\bClass\s*\d+\b',                       # "Class 9", "Class X"
    r'\bExercise\s*\d*[\.:]?\s*',             # "Exercise 5.1" or "Exercise:"
    r'\bActivity\s*[\.:]?\s*',                # "Activity:" or "Activity"
    r'\bProject\s*[\.:]?\s*',                 # "Project:" or "Project"
    r'\bFig\.\s*\d+[:\-]?',                   # "Fig. 5.2:" or "Fig. 5.2-"
    r'\bTable\s*\d+[:\-]?',                   # "Table 6.1 -" or "Table 6.1:"
    
    # === Contacts / Misc Footers ===
    r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b',  # emails
    r'\b\d{6,}\b',                                # phone numbers
    r'\bcontact\s+us\b', r'\bcall\s+(us|on)\b',
    
    # === Misc Marketing / Website Junk ===
    r'\bread\s*more\b', r'\bdownload\s*now\b',
    r'\bplease\s*(refer|visit)\b', r'\bfor\s+more\s+details\b',
    
    # === Pure formatting noise ===
    r'^\W+$',  # punctuation-only lines (----, ***)
]

def clean_text_basic(text: Union[bytes, str]) -> str:
    """
    Cleans text or binary input:
    - Detects encoding (UTF-8 / UTF-16)
    - Removes garbage patterns, null bytes, control chars
    - Normalizes Unicode and spaces
    """
    if not text:
        return ""
    
    # 1️⃣ Handle raw binary (sometimes fitz returns bytes)
    if isinstance(text, bytes):
        if CHARDET_AVAILABLE:
            try:
                detected = chardet.detect(text)
                enc = detected.get("encoding") or "utf-8"
                try:
                    text = text.decode(enc, errors="ignore")
                except Exception:
                    text = text.decode("utf-8", errors="ignore")
            except Exception:
                text = text.decode("utf-8", errors="ignore")
        else:
            # Fallback without chardet
            try:
                text = text.decode("utf-8", errors="ignore")
            except Exception:
                text = text.decode("latin-1", errors="ignore")
    
    # 2️⃣ Handle UTF-16 encoded text (starts with BOM "ÿþ")
    if isinstance(text, str) and (text.startswith("ÿþ") or "\x00" in text[:100]):
        try:
            # Try to decode as UTF-16
            text_bytes = text.encode("latin1") if isinstance(text, str) else text
            text = text_bytes.decode("utf-16", errors="ignore")
        except Exception:
            pass
    
    # 3️⃣ Remove UTF-16 BOM and null bytes if they slip through
    text = text.replace("\ufeff", "")  # BOM
    # Remove ALL null bytes (multiple passes)
    while '\x00' in text:
        text = text.replace('\x00', '')
    while '\u0000' in text:
        text = text.replace('\u0000', '')
    
    # 4️⃣ Normalize Unicode (this converts some OCR artifacts)
    text = unicodedata.normalize("NFKC", text)
    
    # 5️⃣ Remove common OCR misreads (thorn character often misread)
    text = text.replace('þ', 'th')  # Replace thorn with 'th'
    text = text.replace('Þ', 'Th')  # Capital thorn
    
    # 6️⃣ Remove control characters (except newline, tab, carriage return)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # 7️⃣ Apply garbage regex patterns (multiple passes for better coverage)
    for _ in range(2):  # Apply twice to catch overlapping patterns
        for p in garbage_patterns:
            text = re.sub(p, "", text, flags=re.I)
    
    # 8️⃣ Additional aggressive cleanup for common OCR errors
    # Remove lines that are mostly garbage
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        # Skip lines that are mostly URLs/garbage
        if any(garbage in line_stripped.lower() for garbage in ['t.me', 'telegram', 'website', 'nttp', 'vs://', 'ÿth', 'upscpdf']):
            continue
        # Skip lines that are mostly punctuation/special chars
        if len(line_stripped) > 0 and sum(1 for c in line_stripped if c.isalnum()) / len(line_stripped) < 0.3:
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    
    # 9️⃣ Collapse whitespace & clean up lines
    text = re.sub(r"\s+", " ", text)  # collapse spaces/newlines
    text = re.sub(r"^\W+$", "", text, flags=re.M)
    
    # 🔟 Final safety check - remove any remaining null bytes and garbage
    text = text.replace('\x00', '').replace('\u0000', '')
    # One more pass of garbage patterns
    for p in garbage_patterns[:10]:  # Apply key patterns one more time
        text = re.sub(p, "", text, flags=re.I)
    
    return text.strip()

def preprocess_pdf(pdf_path: str) -> str:
    """
    Extracts full text from PDF and cleans it line-by-line.
    Keeps all pages, removes only guaranteed garbage.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Cleaned text string with all pages joined
    """
    try:
        doc = fitz.open(pdf_path)
        cleaned_pages = []
        
        for i, page in enumerate(doc):
            # Get text - might return bytes or str
            raw_text = page.get_text("text")
            if not raw_text:
                continue
            
            # Clean text (handles both bytes and str)
            cleaned_text = clean_text_basic(raw_text)
            
            if not cleaned_text or not cleaned_text.strip():
                continue
            
            if len(cleaned_text.split()) > 10:
                cleaned_pages.append(cleaned_text)
            else:
                logger.debug(f"⚠️ Skipping near-empty page {i+1}")
        
        doc.close()
        
        joined = "\n\n".join(cleaned_pages)
        logger.info(f"✅ Pre-cleaned {len(cleaned_pages)} pages from {pdf_path}")
        
        return joined
        
    except Exception as e:
        logger.error(f"❌ Error preprocessing PDF {pdf_path}: {e}")
        # Fallback: return empty string if preprocessing fails
        return ""

