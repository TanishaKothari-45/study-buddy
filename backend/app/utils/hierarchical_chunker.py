"""
Hybrid Hierarchical Chunker
Visual + Index based (default) with optional Semantic fallback.
"""

import re
import logging
from typing import List, Dict, Any
import fitz  # PyMuPDF
import nltk
from difflib import SequenceMatcher
from nltk.tokenize import sent_tokenize
from openai import OpenAI

# ---- CONFIG ----
USE_SEMANTIC_FALLBACK = True  # toggle to False to skip embeddings for cost saving
SEMANTIC_THRESHOLD = 0.80
EMBED_BATCH_SIZE = 200  # words per embedding window

# ensure sentence tokenizer
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

logger = logging.getLogger(__name__)

# ---- Utility functions ----
def fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def extract_index_from_pages(pdf_path: str) -> List[str]:
    """Extract index/table of contents headings"""
    doc = fitz.open(pdf_path)
    toc_pages_text = []
    found_contents = False
    for i, page in enumerate(doc):
        text_blocks = page.get_text("blocks")
        for block in text_blocks:
            content = block[4].strip()
            if not content:
                continue
            if re.search(r"\b(contents?|index|table of contents)\b", content, re.I):
                found_contents = True
            if found_contents:
                toc_pages_text.append(content)
        if found_contents and i > 2:
            break
    doc.close()

    combined = "\n".join(toc_pages_text)
    lines = combined.splitlines()
    chapter_candidates = []
    ignore_keywords = ["rights", "committee", "advisory", "chairperson", "office"]

    for line in lines:
        line = line.strip()
        if not line or any(k in line.lower() for k in ignore_keywords):
            continue
        if re.match(r"^\d+\s*[A-Za-z]", line) or re.match(r"^[A-Z][A-Za-z\s,:'-]{3,}$", line):
            if 3 < len(line.split()) < 10 and not re.search(r"\d{4}", line):
                chapter_candidates.append(line)

    unique_headings = list(dict.fromkeys(chapter_candidates))
    logger.info(f"📑 Extracted {len(unique_headings)} index entries")
    for h in unique_headings[:10]:
        logger.info(f"   • {h}")
    return unique_headings


def extract_visual_text(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract text + font size info"""
    doc = fitz.open(pdf_path)
    spans = []
    for page_num, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    spans.append({
                        "text": text,
                        "font_size": round(span["size"], 1),
                        "is_bold": "Bold" in span["font"],
                        "page": page_num + 1
                    })
    doc.close()
    return spans


def detect_heading_levels(spans: List[Dict[str, Any]]) -> Dict[float, str]:
    """Map font sizes → hierarchy levels"""
    sizes = sorted(list({s["font_size"] for s in spans}), reverse=True)
    level_map = {}
    if sizes:
        level_map[sizes[0]] = "chapter"
    if len(sizes) > 1:
        level_map[sizes[1]] = "section"
    if len(sizes) > 2:
        level_map[sizes[2]] = "subsection"
    logger.info(f"🎨 Heading levels: {level_map}")
    return level_map


def group_by_hierarchy(spans: List[Dict[str, Any]], level_map: Dict[float, str]) -> List[Dict[str, Any]]:
    """Build chapter/section structure from font hierarchy"""
    chapters = []
    current_chapter, current_section = {"title": None, "sections": [], "text": ""}, {"title": None, "text": ""}
    for s in spans:
        lvl = level_map.get(s["font_size"])
        text = s["text"].strip()

        if lvl == "chapter":
            if current_chapter["title"]:
                if current_section["text"]:
                    current_chapter["sections"].append(current_section)
                chapters.append(current_chapter)
            current_chapter = {"title": text, "sections": [], "text": ""}
            current_section = {"title": None, "text": ""}
        elif lvl == "section":
            if current_section["text"]:
                current_chapter["sections"].append(current_section)
            current_section = {"title": text, "text": ""}
        else:
            if current_section["title"]:
                current_section["text"] += " " + text
            else:
                current_chapter["text"] += " " + text

    if current_section["text"]:
        current_chapter["sections"].append(current_section)
    if current_chapter["title"]:
        chapters.append(current_chapter)
    logger.info(f"📘 Built {len(chapters)} chapters")
    return chapters


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split by sentences into word-length chunks"""
    sentences = sent_tokenize(text)
    chunks, current, length = [], [], 0
    for sent in sentences:
        words = sent.split()
        length += len(words)
        current.append(sent)
        if length >= chunk_size:
            chunks.append(" ".join(current))
            current, length = [], 0
    if current:
        chunks.append(" ".join(current))
    return [c.strip() for c in chunks if len(c.split()) > 20]


# ---- Semantic fallback ----
def semantic_split(text: str, client: OpenAI, threshold: float = SEMANTIC_THRESHOLD) -> List[str]:
    """Split text into semantically coherent chunks using embeddings"""
    words = text.split()
    windows = [" ".join(words[i:i + EMBED_BATCH_SIZE]) for i in range(0, len(words), EMBED_BATCH_SIZE)]
    if len(windows) < 2:
        return [text]

    embeddings = []
    for i in range(0, len(windows), 10):  # batch 10 windows per API call
        batch = windows[i:i + 10]
        resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
        embeddings.extend([d.embedding for d in resp.data])

    import numpy as np
    sims = []
    for i in range(len(embeddings) - 1):
        a, b = np.array(embeddings[i]), np.array(embeddings[i + 1])
        sims.append(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    chunks, current = [windows[0]], ""
    for i, sim in enumerate(sims):
        if sim < threshold:
            chunks.append(current.strip())
            current = ""
        current += " " + windows[i + 1]
    if current:
        chunks.append(current.strip())

    logger.info(f"🧠 Semantic fallback created {len(chunks)} chunks")
    return chunks


# ---- Main class ----
class HierarchicalChunker:
    def __init__(self, llm_client: OpenAI = None):
        self.llm_client = llm_client or OpenAI()

    def process_pdf(self, pdf_path: str, filename: str) -> List[Dict[str, Any]]:
        logger.info(f"🔍 Processing {filename}")
        index_entries = extract_index_from_pages(pdf_path)
        spans = extract_visual_text(pdf_path)
        level_map = detect_heading_levels(spans)
        structure = group_by_hierarchy(spans, level_map)

        # Validate visual structure - if too many chapters or suspicious, it's likely wrong
        is_valid_structure = (
            structure and 
            len(structure) < 100 and  # Reasonable number of chapters
            any(ch.get("title") for ch in structure)
        )
        
        # Try visual+index first if structure looks valid
        processed = []
        if is_valid_structure:
            logger.info(f"🧩 Strategy chosen: VISUAL+INDEX")
            for ci, chap in enumerate(structure, 1):
                chap_title = chap["title"] or f"Chapter {ci}"
                sections = chap.get("sections", []) or [{"title": "General", "text": chap["text"]}]
                
                for si, section in enumerate(sections, 1):
                    sec_title = section["title"] or f"Section {si}"
                    section_text = section.get("text", "").strip()
                    
                    if not section_text or len(section_text) < 50:
                        logger.debug(f"   ⚠️ Skipping empty section: {chap_title} > {sec_title}")
                        continue
                    
                    chunks = chunk_text(section_text)
                    if not chunks:
                        logger.debug(f"   ⚠️ No chunks created from section: {chap_title} > {sec_title}")
                        continue
                    
                    for chunk_i, chunk in enumerate(chunks, 1):
                        processed.append({
                            "content": chunk,
                            "metadata": {
                                "subject": "Geography",
                                "chapter": chap_title,
                                "section": sec_title,
                                "chunk_id": f"{ci}_{si}_{chunk_i}",
                                "filename": filename
                            }
                        })
            
            logger.info(f"   📊 Visual+Index created {len(processed)} chunks")
        
        # Fallback to semantic if visual produced no chunks or structure was invalid
        if not processed and USE_SEMANTIC_FALLBACK and self.llm_client:
            logger.warning(f"⚠️ Visual+Index produced 0 chunks. Falling back to SEMANTIC chunking...")
            try:
                doc_text = " ".join([s["text"] for s in spans])
                if len(doc_text.strip()) > 200:  # Only use semantic if we have substantial text
                    semantic_chunks = semantic_split(doc_text, self.llm_client)
                    for i, chunk in enumerate(semantic_chunks, 1):
                        processed.append({
                            "content": chunk,
                            "metadata": {
                                "subject": "Geography",
                                "chapter": "Semantic Segment",
                                "section": f"Segment {i}",
                                "chunk_id": f"S_{i}",
                                "filename": filename
                            }
                        })
                    logger.info(f"   📊 Semantic fallback created {len(processed)} chunks")
                else:
                    logger.warning(f"   ⚠️ Text too short for semantic chunking ({len(doc_text)} chars)")
            except Exception as e:
                logger.error(f"   ❌ Semantic fallback failed: {e}")
        
        # Final fallback: simple text splitting
        if not processed:
            logger.warning(f"⚠️ All strategies failed. Using simple text splitting...")
            doc_text = " ".join([s["text"] for s in spans])
            if len(doc_text.strip()) > 200:
                simple_chunks = chunk_text(doc_text, chunk_size=500, overlap=50)
                for i, chunk in enumerate(simple_chunks, 1):
                    processed.append({
                        "content": chunk,
                        "metadata": {
                            "subject": "Geography",
                            "chapter": "Document",
                            "section": f"Chunk {i}",
                            "chunk_id": f"F_{i}",
                            "filename": filename
                        }
                    })
                logger.info(f"   📊 Simple fallback created {len(processed)} chunks")

        logger.info(f"✅ Completed {filename}: {len(processed)} chunks created")
        return processed
