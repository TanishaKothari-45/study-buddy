"""
Hybrid Hierarchical Chunker
Visual + Index based (default) with optional Semantic fallback.
"""

import re
import logging
import unicodedata
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


def clean_text_noise(text: str) -> str:
    """Clean noise characters from text using advanced cleaning"""
    from .text_cleaner import clean_text_advanced
    return clean_text_advanced(text, pages_content=None)

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
                    # Clean noise from extracted text
                    text = clean_text_noise(text)
                    if not text:  # Skip if cleaning removed everything
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
    """Split by sentences into word-length chunks with quality improvements"""
    from .text_cleaner import improve_chunk_quality
    
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
    
    # Filter out very short chunks
    chunks = [c.strip() for c in chunks if len(c.split()) > 20]
    
    # Improve chunk quality (merge small chunks, fix sentence boundaries)
    chunks = improve_chunk_quality(chunks, min_words=20)
    
    return chunks


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
                        chunk_data = {
                            "content": chunk,
                            "metadata": {
                                "subject": "Geography",
                                "chapter": chap_title,
                                "section": sec_title,
                                "chunk_id": f"{ci}_{si}_{chunk_i}",
                                "filename": filename
                            }
                        }
                        processed.append(chunk_data)
                        
                        # Log first chunk of each chapter for verification
                        if chunk_i == 1 and ci == 1:
                            logger.info(f"   📝 Sample chunk from {chap_title} > {sec_title}:")
                            logger.info(f"      Content: {chunk[:300].replace(chr(10), ' ')}...")
                            logger.info(f"      Length: {len(chunk)} chars")
            
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

    def detect_chapters_in_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect chapters in text using pattern matching.
        Looks for patterns like:
        - "Chapter 1 The Earth and the Universe"
        - "CHAPTER 1: Title"
        - "Chapter 1 - Title"
        """
        chapters = []
        
        # Pattern to match chapter headings
        # Matches: "Chapter 1", "CHAPTER 1", "Chapter 1:", "Chapter 1 -", etc.
        chapter_pattern = re.compile(
            r'^Chapter\s+(\d+)[\s:.\-]*(.+?)$',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Also match numbered chapters without "Chapter" keyword
        numbered_pattern = re.compile(
            r'^(\d+)[\.\s]+([A-Z][^\.\n]{5,100})$',
            re.MULTILINE
        )
        
        lines = text.split('\n')
        current_chapter = None
        current_content = []
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Check for chapter pattern
            chapter_match = chapter_pattern.match(line_stripped)
            numbered_match = numbered_pattern.match(line_stripped) if not chapter_match else None
            
            if chapter_match:
                # Save previous chapter if exists
                if current_chapter and current_content:
                    chapters.append({
                        "number": current_chapter["number"],
                        "title": current_chapter["title"],
                        "content": "\n".join(current_content).strip()
                    })
                
                # Start new chapter
                chapter_num = chapter_match.group(1)
                chapter_title = chapter_match.group(2).strip()
                current_chapter = {
                    "number": int(chapter_num),
                    "title": chapter_title
                }
                current_content = []
                logger.debug(f"   📖 Found Chapter {chapter_num}: {chapter_title}")
                
            elif numbered_match and len(current_content) == 0:
                # Potential chapter start (number at start of line, followed by title)
                num = numbered_match.group(1)
                title = numbered_match.group(2).strip()
                # Only treat as chapter if it's at the start or after a blank line
                if i == 0 or (i > 0 and not lines[i-1].strip()):
                    if current_chapter and current_content:
                        chapters.append({
                            "number": current_chapter["number"],
                            "title": current_chapter["title"],
                            "content": "\n".join(current_content).strip()
                        })
                    current_chapter = {
                        "number": int(num),
                        "title": title
                    }
                    current_content = []
                    logger.debug(f"   📖 Found numbered chapter {num}: {title}")
                else:
                    current_content.append(line)
            else:
                # Regular content line
                if current_chapter:
                    current_content.append(line)
                elif line_stripped:  # Content before first chapter
                    # Create a default first chapter
                    if not current_chapter:
                        current_chapter = {
                            "number": 0,
                            "title": "Introduction"
                        }
                        current_content = [line]
        
        # Add final chapter
        if current_chapter and current_content:
            chapters.append({
                "number": current_chapter["number"],
                "title": current_chapter["title"],
                "content": "\n".join(current_content).strip()
            })
        
        return chapters

    def preprocess_text(self, text: str) -> str:
        """
        Clean and preprocess text to remove noise and normalize.
        Uses advanced cleaning from text_cleaner module
        """
        if not text:
            return ""
        
        from .text_cleaner import clean_text_advanced
        
        # Use advanced cleaning (handles images, headers/footers, noise, etc.)
        text = clean_text_advanced(text, pages_content=None)
        
        # Additional preprocessing for TXT files
        # Normalize unicode quotes and dashes
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2018', "'").replace('\u2019', "'")
        text = text.replace('\u2013', '-').replace('\u2014', '--')
        
        # Remove BOM if present
        if text.startswith('\ufeff'):
            text = text[1:]
        
        return text.strip()

    def process_txt(self, txt_path: str, filename: str) -> List[Dict[str, Any]]:
        """
        Process a TXT file by reading it directly and chunking it.
        Now with chapter detection and aggressive preprocessing.
        Chunks are limited to ~1500 words to fit OpenAI embedding limits (8192 tokens).
        """
        logger.info(f"🔍 Processing TXT file: {filename}")
        
        try:
            # Read the text file with UTF-8 encoding, fallback to latin-1 if needed
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError:
                logger.warning(f"   ⚠️ UTF-8 decode failed, trying latin-1...")
                with open(txt_path, 'r', encoding='latin-1') as f:
                    text = f.read()
            
            if not text or len(text.strip()) < 50:
                logger.warning(f"   ⚠️ TXT file is empty or too short")
                return []
            
            # Preprocess text to remove noise
            logger.info(f"   🧹 Preprocessing text (removing noise, normalizing)...")
            original_length = len(text)
            text = self.preprocess_text(text)
            cleaned_length = len(text)
            logger.info(f"   • Original length: {original_length} chars")
            logger.info(f"   • Cleaned length: {cleaned_length} chars")
            logger.info(f"   • Sample text (first 300 chars): {text[:300].replace(chr(10), ' ')}...")
            
            # Detect chapters in the text
            chapters = self.detect_chapters_in_text(text)
            
            if chapters:
                logger.info(f"   📚 Detected {len(chapters)} chapters:")
                for ch in chapters[:5]:  # Show first 5
                    logger.info(f"      • Chapter {ch['number']}: {ch['title'][:50]}...")
                if len(chapters) > 5:
                    logger.info(f"      ... and {len(chapters) - 5} more chapters")
            else:
                logger.info(f"   ⚠️ No chapters detected, treating as single document")
                chapters = [{
                    "number": 1,
                    "title": "Document",
                    "content": text
                }]
            
            # MUCH MORE AGGRESSIVE limit: 1500 words ≈ 1950 tokens (very safe)
            # OpenAI limit is 8192 tokens, but we use 1500 words to be VERY safe
            MAX_WORDS_PER_CHUNK = 1500  # ~1950 tokens, well under 8192 limit
            processed = []
            
            # Process each chapter
            for chapter in chapters:
                chapter_num = chapter["number"]
                chapter_title = chapter["title"]
                chapter_content = chapter["content"]
                
                if not chapter_content or len(chapter_content.strip()) < 50:
                    logger.debug(f"   ⚠️ Skipping empty chapter: {chapter_title}")
                    continue
                
                # Chunk the chapter content
                # Use MUCH smaller chunks to prevent token limit errors
                chapter_chunks = chunk_text(chapter_content, chunk_size=1500, overlap=50)
                
                if not chapter_chunks:
                    logger.debug(f"   ⚠️ No chunks created from chapter: {chapter_title}")
                    continue
                
                # Process each chunk from this chapter
                for chunk_idx, chunk in enumerate(chapter_chunks, 1):
                    words = chunk.split()
                    word_count = len(words)
                    
                    # If chunk is too large, split it further
                    if word_count > MAX_WORDS_PER_CHUNK:
                        logger.warning(f"   ⚠️ Chunk {chunk_idx} in Chapter {chapter_num} is too large ({word_count} words), splitting...")
                        # Split into smaller sub-chunks
                        sub_chunk_size = MAX_WORDS_PER_CHUNK - 100
                        overlap_size = 50
                        
                        for sub_idx in range(0, word_count, sub_chunk_size - overlap_size):
                            sub_chunk_words = words[sub_idx:sub_idx + sub_chunk_size]
                            sub_chunk = " ".join(sub_chunk_words)
                            
                            # Double-check word count
                            final_word_count = len(sub_chunk.split())
                            if final_word_count > MAX_WORDS_PER_CHUNK:
                                logger.error(f"   ❌ Sub-chunk still too large ({final_word_count} words), truncating!")
                                truncated_words = sub_chunk.split()[:MAX_WORDS_PER_CHUNK]
                                sub_chunk = " ".join(truncated_words)
                            
                            if len(sub_chunk.strip()) > 50:
                                processed.append({
                                    "content": sub_chunk,
                                    "metadata": {
                                        "subject": "Geography",
                                        "chapter": chapter_title,
                                        "section": f"Part {sub_idx // sub_chunk_size + 1}",
                                        "chunk_id": f"CH{chapter_num}_{chunk_idx}_{sub_idx // sub_chunk_size + 1}",
                                        "filename": filename
                                    }
                                })
                    elif len(chunk.strip()) > 50:  # Only include substantial chunks
                        # Final safety check
                        final_word_count = len(chunk.split())
                        if final_word_count > MAX_WORDS_PER_CHUNK:
                            logger.warning(f"   ⚠️ Chunk exceeded limit ({final_word_count} words), truncating...")
                            words = chunk.split()
                            chunk = " ".join(words[:MAX_WORDS_PER_CHUNK])
                        
                        processed.append({
                            "content": chunk,
                            "metadata": {
                                "subject": "Geography",
                                "chapter": chapter_title,
                                "section": f"Section {chunk_idx}",
                                "chunk_id": f"CH{chapter_num}_{chunk_idx}",
                                "filename": filename
                            }
                        })
            
            logger.info(f"   📊 Created {len(processed)} chunks from {len(chapters)} chapters")
            if processed:
                sample_words = len(processed[0]['content'].split())
                sample_meta = processed[0]['metadata']
                logger.info(f"   📝 Sample chunk:")
                logger.info(f"      Chapter: {sample_meta['chapter']}")
                logger.info(f"      Section: {sample_meta['section']}")
                logger.info(f"      Content preview: {processed[0]['content'][:300].replace(chr(10), ' ')}...")
                logger.info(f"      Length: {len(processed[0]['content'])} chars, ~{sample_words} words")
            
            return processed
            
        except Exception as e:
            logger.error(f"   ❌ Error processing TXT file: {e}")
            import traceback
            traceback.print_exc()
            return []
