#!/usr/bin/env python3
"""
vision_md_tuned.py  — Google Vision OCR → Clean Markdown with headings tuned
Usage:
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/creds.json
    python vision_md_tuned.py input.pdf            # whole PDF -> input_ocr.md
    python vision_md_tuned.py input.pdf 5         # single page -> input_p005_ocr.md

Notes:
- Tuned for scanned educational PDFs (like the sample you uploaded).
- Requires: google-cloud-vision, pymupdf (fitz)
"""
import os
import sys
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from google.cloud import vision
except Exception as e:
    raise ImportError("google-cloud-vision not installed or credentials missing.") from e

import fitz  # PyMuPDF

# --------- Configuration / Heuristics ----------
DPI = 300
Y_TOLERANCE = 10            # pixels to merge words into a same line
MIN_HEADING_FONT_BOOST = 1  # relative boost for numbered headings
CLEAN_URL_PATTERNS = [
    r'http\S+',
    r'www\.\S+',
    r't\.me\/\S+',
    r'telegram\.me\/\S+',
    r'nttpS?:\/\/\S+',
    r'ilttpS?:\/\/\S+',
    r'ÿth', r'ÿ', r'\ufffd'  # common garbage
]
NULL_CONTROL_RE = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]')

# Patterns that strongly indicate a heading (numbered or word markers)
NUMBERED_HEADING_RE = re.compile(r'^\s*(Chapter|CHAPTER|\d+(\.\d+)*\b)\s*[:\-\–.]?\s*(.+)?', re.I)
SHORT_HEADING_WORDS_MAX = 7  # headings usually short-ish


# --------- Helper functions ----------
def get_vision_client():
    return vision.ImageAnnotatorClient()

def clean_ocr_text_line(text: str) -> str:
    if not text:
        return ""
    # remove null/control characters
    text = NULL_CONTROL_RE.sub("", text)
    # replace weird isolated characters and sequences
    text = text.replace('ÿ', '').replace('�', '').replace('\ufeff', '')
    # fix common mangles
    text = re.sub(r'\bnttpS\b', 'http', text, flags=re.I)
    text = re.sub(r'\bilttpS\b', 'http', text, flags=re.I)
    # remove long repeated whitespace and control sequences
    text = re.sub(r'\s+', ' ', text).strip()
    # remove common URL-like garbage if standalone or at ends
    for p in CLEAN_URL_PATTERNS:
        text = re.sub(p, '', text, flags=re.I)
    # strip stray punctuation at line edges
    text = text.strip(" \t\n\r-–—•")
    return text

def quantiles(values: List[float]):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return (12.0, 12.0, 12.0)
    return (s[max(0, n//4 - 1)], s[n//2], s[min(n-1, 3*n//4)])

def merge_spans_to_lines(spans: List[Dict[str, Any]], y_tol: int = Y_TOLERANCE) -> List[Dict[str, Any]]:
    """
    spans: list of {"text": str, "bbox": [x1,y1,x2,y2], "font_size": float}
    Returns list of lines with aggregated text and max font_size
    """
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    lines = []
    cur = spans[0].copy()
    for s in spans[1:]:
        if abs(s["bbox"][1] - cur["bbox"][1]) <= y_tol:
            # same horizontal line
            cur["text"] = cur["text"] + " " + s["text"]
            cur["bbox"][0] = min(cur["bbox"][0], s["bbox"][0])
            cur["bbox"][1] = min(cur["bbox"][1], s["bbox"][1])
            cur["bbox"][2] = max(cur["bbox"][2], s["bbox"][2])
            cur["bbox"][3] = max(cur["bbox"][3], s["bbox"][3])
            cur["font_size"] = max(cur.get("font_size", 0), s.get("font_size", 0))
        else:
            lines.append(cur)
            cur = s.copy()
    lines.append(cur)
    return lines

def vision_page_lines(png_bytes: bytes) -> List[Dict[str, Any]]:
    """Run Google Vision on a PNG byte image and return merged lines with font sizes."""
    client = get_vision_client()
    image = vision.Image(content=png_bytes)
    resp = client.document_text_detection(image=image)
    pages = []
    lines: List[Dict[str, Any]] = []
    for page in resp.full_text_annotation.pages:
        # iterate symbols -> words -> paragraphs -> blocks per page
        word_spans = []
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join([s.text for s in word.symbols])
                    # bounding box vertices may be missing or zero; handle safely
                    verts = word.bounding_box.vertices
                    if not verts or len(verts) < 4:
                        continue
                    bbox = [verts[0].x or 0, verts[0].y or 0, verts[2].x or 0, verts[2].y or 0]
                    # font size info is not always present; compute if available
                    font_sizes = [getattr(s, "font_size", 0) for s in word.symbols if hasattr(s, "font_size")]
                    font_size = max(font_sizes) if font_sizes else 12.0
                    word_spans.append({"text": text, "bbox": bbox, "font_size": float(font_size)})
        # merge word spans -> lines
        lines = merge_spans_to_lines(word_spans, y_tol=Y_TOLERANCE)
    # final cleaning for texts
    for l in lines:
        l["text"] = clean_ocr_text_line(l["text"])
    return lines

def page_to_png_bytes(pdf_path: str, page_number: int, dpi: int = DPI) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        pix = doc.load_page(page_number).get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()

def promote_numbered_heading(line_text: str, font_size: float) -> float:
    """If a line looks like '2. Climate' or 'Chapter 3', increase its font-size artificially
       so it becomes a heading. This helps badly-scanned PDFs where font metrics are noisy."""
    if NUMBERED_HEADING_RE.match(line_text):
        return font_size + MIN_HEADING_FONT_BOOST * 2.0
    # also if line short and contains Title-Case words, slightly boost
    words = line_text.split()
    if 1 < len(words) <= SHORT_HEADING_WORDS_MAX and sum(1 for w in words if w[0].isupper()) >= max(1, len(words)//2):
        return font_size + MIN_HEADING_FONT_BOOST
    return font_size

def lines_to_markdown(lines: List[Dict[str, Any]]) -> str:
    """Convert list of lines (with font_size) into markdown with headings."""
    if not lines:
        return ""
    sizes = [promote_numbered_heading(l["text"], l.get("font_size", 12.0)) for l in lines if l.get("text")]
    q25, q50, q75 = quantiles(sizes)
    md_lines = []
    last_was_heading = False
    for l in lines:
        text = l.get("text", "").strip()
        if not text:
            # blank line -> paragraph break
            md_lines.append("")
            last_was_heading = False
            continue
        fs = promote_numbered_heading(text, l.get("font_size", 12.0))
        # choose heading level by quantile thresholds
        if fs >= q75 and len(text.split()) <= 20:
            md_lines.append(f"# {text}")
            last_was_heading = True
        elif fs >= q50 and len(text.split()) <= 30:
            md_lines.append(f"## {text}")
            last_was_heading = True
        elif fs >= q25 and len(text.split()) <= 60 and NUMBERED_HEADING_RE.match(text):
            # number-based subsection
            md_lines.append(f"### {text}")
            last_was_heading = True
        else:
            # Normal paragraph line
            # If previous was heading, keep no prefix; else join lines into paragraphs
            if last_was_heading:
                md_lines.append(text)
                last_was_heading = False
            else:
                # Append to previous paragraph if previous item is not a heading and not blank
                if md_lines and not md_lines[-1].startswith("#") and md_lines[-1] != "":
                    md_lines[-1] = md_lines[-1] + " " + text
                else:
                    md_lines.append(text)
                last_was_heading = False
    # Post-clean: remove lines that are tiny garbage
    cleaned = []
    for l in md_lines:
        ls = l.strip()
        if not ls:
            cleaned.append("")
            continue
        # remove lines that are only stray punctuation or single characters
        if len(ls) < 3 and not ls.isalpha():
            continue
        cleaned.append(ls)
    # join paragraphs with double newlines
    return "\n\n".join(cleaned).strip()

# --------- High-level processing ----------
def process_pdf_to_markdown(pdf_path: str, out_path: Optional[str] = None, single_page: Optional[int] = None) -> str:
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(pdf_path)
    if out_path is None:
        out_path = str(pdf.with_suffix("")) + "_ocr.md"

    doc = fitz.open(pdf_path)
    pages = [single_page] if single_page is not None else list(range(doc.page_count))
    doc.close()

    all_pages_md = []
    for p in pages:
        print(f"→ Processing page {p+1}/{len(pages)} ...")
        try:
            png = page_to_png_bytes(pdf_path, p, dpi=DPI)
            lines = vision_page_lines(png)
            if not lines:
                raise RuntimeError("No lines returned from Vision; falling back to PyMuPDF text extraction.")
            page_md = lines_to_markdown(lines)
            # small extra cleaning on page-level
            page_md = re.sub(r'\n{3,}', '\n\n', page_md).strip()
            all_pages_md.append(page_md)
        except Exception as e:
            # fallback: try PyMuPDF text extraction + basic cleaning
            print(f"  ⚠️ Vision failed or produced no lines on page {p+1}: {e}")
            try:
                doc = fitz.open(pdf_path)
                text = doc.load_page(p).get_text("text")
                doc.close()
                text = clean_ocr_text_line(text)
                # naive break by double newlines
                page_md = "\n\n".join([line.strip() for line in text.splitlines() if line.strip()])
                all_pages_md.append(page_md)
            except Exception as e2:
                print(f"  ❌ Fallback also failed for page {p+1}: {e2}")
                continue

    final_md = "\n\n".join(all_pages_md)
    # Global cleanup: remove duplicate short lines, repeated page headers like 'Page 10' etc.
    final_md = re.sub(r'(?m)^\s*page\s*\d+\s*$', '', final_md, flags=re.I)
    final_md = re.sub(r'\n{3,}', '\n\n', final_md)
    # Remove leftover nulls/control
    final_md = NULL_CONTROL_RE.sub("", final_md)
    Path(out_path).write_text(final_md, encoding="utf-8")
    print("✅ Saved Markdown:", out_path)
    return out_path

# --------- CLI ----------
def print_usage():
    print("Usage: python vision_md_tuned.py <pdf_path> [page_number]")
    print("Example: python vision_md_tuned.py myfile.pdf")
    print("         python vision_md_tuned.py myfile.pdf 5")

# API wrapper functions for FastAPI routes
def process_pdf_page(pdf_path: str, page: int, dpi: int = 250) -> Dict[str, Any]:
    """Process a single page - API wrapper function"""
    png = page_to_png_bytes(pdf_path, page, dpi=dpi)
    lines = vision_page_lines(png)
    if not lines:
        # Fallback to PyMuPDF
        doc = fitz.open(pdf_path)
        text = doc.load_page(page).get_text("text")
        doc.close()
        text = clean_ocr_text_line(text)
        lines = [{"text": t, "bbox": [0, 0, 0, 0], "font_size": 12.0} for t in text.splitlines() if t.strip()]
    markdown = lines_to_markdown(lines)
    
    # Extract blocks and headings
    blocks = []
    headings = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading_text = re.sub(r'^#+\s+', '', line)
            level = len(line) - len(line.lstrip('#'))
            headings.append({"text": heading_text, "numbered_text": line, "level": level, "font_size": 14.0, "bbox": [0, 0, 0, 0]})
            blocks.append({"text": heading_text, "bbox": [0, 0, 0, 0], "font_size": 14.0})
        else:
            blocks.append({"text": line, "bbox": [0, 0, 0, 0], "font_size": 12.0})
    
    return {"blocks": blocks, "markdown": markdown, "headings": headings, "page": page, "num_blocks": len(blocks), "num_headings": len(headings)}

def process_pdf_all_pages(pdf_path: str, dpi: int = 250, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """Process all pages - API wrapper function"""
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    pages_to_process = min(total_pages, max_pages) if max_pages else total_pages
    doc.close()
    
    results = []
    for page_num in range(pages_to_process):
        result = process_pdf_page(pdf_path, page_num, dpi)
        results.append(result)
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    pdf_path = sys.argv[1]
    page_arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    out = process_pdf_to_markdown(pdf_path, single_page=(page_arg-1 if page_arg else None))
    print("Done.")
