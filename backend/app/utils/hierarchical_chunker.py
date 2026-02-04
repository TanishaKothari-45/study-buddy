"""
Hierarchical chunker for PDFs and text files

Detects document structure (chapters, sections) and chunks accordingly.
Uses font size analysis for PDFs to detect hierarchy.
"""

import logging
import json
import re
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import fitz  # PyMuPDF
from ..core.config import settings
from .pdf_reader import extract_text_from_pdf

logger = logging.getLogger(__name__)


class HierarchicalChunker:
    """
    Chunks documents hierarchically by detecting structure (chapters, sections).
    For PDFs: Uses font size analysis to detect hierarchy.
    For TXT: Uses simple paragraph-based chunking.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize the hierarchical chunker.
        
        Args:
            llm_client: Optional OpenAI client (for future LLM-based structure detection)
        """
        self.llm_client = llm_client
        self.chunk_size_words = settings.CHUNK_SIZE_WORDS
        self.chunk_overlap_percent = settings.CHUNK_OVERLAP_PERCENT
        self.min_words_per_chunk = settings.MIN_WORDS_PER_CHUNK
        
    def process_pdf(self, pdf_path: str, filename: str, subject: str = "Unclassified") -> List[Dict[str, Any]]:
        """
        Process a PDF file and return hierarchical chunks.
        
        Args:
            pdf_path: Path to the PDF file
            filename: Name of the file
            subject: Subject area (default: "Geography")
            
        Returns:
            List of chunk dictionaries with 'content' and 'metadata' keys
        """
        try:
            logger.info(f"📄 Processing PDF: {filename}")
            
            # Step 1: Extract text from PDF first
            pages_content = extract_text_from_pdf(pdf_path)
            if not pages_content:
                logger.warning(f"⚠️ No content extracted from {filename}")
                return []
            
            # TOC/Gemini Extraction disabled by user request. 
            # Treating all files as single chapters for now.
            logger.info(f"ℹ️ Skipping TOC extraction and treating {filename} as a single chapter.")
            return self.process_as_single_chunk(pages_content, filename, subject)
            
        except Exception as e:
            logger.error(f"❌ Error processing PDF {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def process_as_single_chunk(
        self, 
        pages_content: Optional[List[Dict[str, Any]]] = None, 
        filename: str = "document", 
        subject: str = "Unclassified",
        text_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert whole content into a single chunk after cleaning watermarks.
        Can take either PyMuPDF pages_content or a single string.
        """
        if text_override:
            full_text = text_override
        elif pages_content:
            full_text = "\n\n".join([p["text"] for p in pages_content]).strip()
        else:
            return []
            
        cleaned_text = self._clean_text(full_text)
        
        if not cleaned_text:
            return []
            
        return [{
            "content": cleaned_text,
            "metadata": {
                "filename": filename,
                "subject": subject,
                "chapter": filename.replace(".pdf", "").replace(".PDF", ""),
                "chunk_id": f"{filename}_chapter_1"
            }
        }]

    def process_txt(
        self, 
        txt_path: str, 
        filename: str, 
        subject: str = "Geography",
        text_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process a text file and return chunks.
        
        Args:
            txt_path: Path to the text file (can be None if text_override is provided)
            filename: Name of the file
            subject: Subject area (default: "Geography")
            text_override: Optional text content (if provided, txt_path is ignored)
            
        Returns:
            List of chunk dictionaries with 'content' and 'metadata' keys
        """
        try:
            logger.info(f"📝 Processing TXT file: {filename}")
            
            # Read text content
            if text_override:
                text = text_override
            else:
                if not txt_path or not os.path.exists(txt_path):
                    logger.error(f"❌ Text file not found: {txt_path}")
                    return []
                
                # Try multiple encodings to handle different file types
                encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
                text = None
                last_error = None
                
                for encoding in encodings:
                    try:
                        with open(txt_path, 'r', encoding=encoding) as f:
                            text = f.read()
                        break
                    except UnicodeDecodeError as e:
                        last_error = e
                        continue
                    except Exception as e:
                        # If file is binary (like PDF), detect and skip
                        if 'compressed' in txt_path.lower() or txt_path.endswith('.pdf'):
                            logger.warning(f"⚠️ File {txt_path} appears to be binary/compressed, skipping text processing")
                            return []
                        last_error = e
                        continue
                
                if text is None:
                    logger.error(f"❌ Could not read text file {txt_path} with any encoding: {last_error}")
                    # Check if it's actually a binary file
                    try:
                        with open(txt_path, 'rb') as f:
                            first_bytes = f.read(4)
                            # Check for PDF signature or other binary formats
                            if first_bytes.startswith(b'%PDF') or first_bytes[0] == 0xff:
                                logger.warning(f"⚠️ File {txt_path} is binary (PDF or compressed), not a text file")
                                return []
                    except:
                        pass
                    return []
            
            if not text or len(text.strip()) < 100:
                logger.warning(f"⚠️ Text file {filename} is too short or empty")
                return []
            
            # Split into paragraphs
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            
            # Create chunks from paragraphs
            chunks = []
            current_chunk = []
            current_words = 0
            
            for para in paragraphs:
                para_words = len(para.split())
                
                # If adding this paragraph would exceed chunk size, save current chunk
                if current_words + para_words > self.chunk_size_words and current_chunk:
                    chunk_text = '\n\n'.join(current_chunk)
                    if len(chunk_text.split()) >= self.min_words_per_chunk:
                        chunks.append({
                            "content": chunk_text,
                            "metadata": {
                                "filename": filename,
                                "subject": subject,
                                "chapter": "Text Document",
                                "section": "General",
                                "chunk_id": f"{filename}_{len(chunks) + 1}"
                            }
                        })
                    
                    # Start new chunk with overlap
                    overlap_words = int(self.chunk_size_words * self.chunk_overlap_percent)
                    overlap_text = ' '.join(chunk_text.split()[-overlap_words:])
                    current_chunk = [overlap_text] if overlap_text else []
                    current_words = len(overlap_text.split())
                
                current_chunk.append(para)
                current_words += para_words
            
            # Add final chunk
            if current_chunk:
                chunk_text = '\n\n'.join(current_chunk)
                if len(chunk_text.split()) >= self.min_words_per_chunk:
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "filename": filename,
                            "subject": subject,
                            "chapter": "Text Document",
                            "section": "General",
                            "chunk_id": f"{filename}_{len(chunks) + 1}"
                        }
                    })
            
            logger.info(f"✅ Created {len(chunks)} chunks from {filename}")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ Error processing TXT file {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _extract_toc_with_gemini(self, sample_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Use Gemini to extract Table of Contents from the first few pages of text.
        """
        if not self.llm_client:
            logger.warning("⚠️ No LLM client provided for Gemini TOC extraction")
            return []
            
        # Combine text from first 15 pages
        toc_text = "\n\n".join([f"PAGE {p['page_number']}:\n{p['text']}" for p in sample_pages])
        
        prompt = f"""
        You are a document structure analyst. I will provide the first few pages of a History/Geography book.
        Find the Table of Contents/Index and extract the major chapters and their starting page numbers.
        
        CRITICAL INSTRUCTIONS:
        1. Look for headings like "Contents", "List of Chapters", or "Index".
        2. Identify main chapters (Level 1) and their starting page numbers.
        3. Identify sub-chapters (Level 2) if they have clear page numbers.
        4. Return a clean JSON list of objects.
        
        Example format:
        [
          {{"title": "Introduction", "page_number": 1, "level": 1}},
          {{"title": "Chapter 1: The First Frontier", "page_number": 15, "level": 1}},
          {{"title": "1.1 The Landscape", "page_number": 17, "level": 2}}
        ]
        
        Note: The page_number should be the actual page number from the contents page.
        Only return the JSON list, no explanation or markdown blocks.
        
        TEXT TO ANALYZE:
        {toc_text[:15000]}
        """
        
        try:
            from .metadata_enricher import safe_json_parse
            
            response = self.llm_client.chat.completions.create(
                model="gpt-4o-mini", # Using mini for speed/cost, maybe Gemini 1.5 Flash if available?
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            output = response.choices[0].message.content
            toc_entries = safe_json_parse(output)
            
            if toc_entries:
                logger.info(f"✅ Gemini extracted {len(toc_entries)} TOC entries")
                return toc_entries
            else:
                logger.warning(f"⚠️ Gemini returned empty or invalid TOC JSON. Raw output: {output[:500]}...")
        except Exception as e:
            logger.error(f"❌ Gemini TOC extraction failed: {e}")
            
        return []

    def _clean_text(self, text: str) -> str:
        """
        Remove repetitive watermarks and administrative noise from text.
        """
        noise_strings = [
            "xaam.in", "Raz Kr", "Facebook Group", "Administrative Service", 
            "Telegram:", "Copyright", "All Rights Reserved", "[Live]",
            "Indian Administrative Service", "RazKr"
        ]
        
        cleaned = text
        for noise in noise_strings:
            # Case insensitive removal
            pattern = re.compile(re.escape(noise), re.IGNORECASE)
            cleaned = pattern.sub("", cleaned)
            
        # Clean up excess whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _should_filter_chunk(self, content: str) -> bool:
        """
        Identify and filter out ONLY truly empty or meta-only chunks.
        Book content with watermarks should NOT be filtered, but cleaned.
        """
        cleaned = self._clean_text(content)
        
        # 1. Filter if too short AFTER cleaning (meta-only chunks)
        if len(cleaned.split()) < 20:
            logger.info(f"🗑️ Filtering meta-only chunk (length {len(cleaned.split())} words)")
            return True
            
        # 2. High digit ratio often indicates index/biblio pages
        digit_ratio = sum(c.isdigit() for c in cleaned) / len(cleaned) if cleaned else 0
        if digit_ratio > 0.4 and len(cleaned) < 500:
            logger.info(f"🗑️ Filtering index-like chunk (high digit ratio)")
            return True
            
        return False

    def _extract_toc(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract Table of Contents (bookmarks) from PDF.
        
        Returns:
            List of dictionaries with 'title', 'page_number', and 'level'
        """
        toc_entries = []
        try:
            doc = fitz.open(pdf_path)
            toc = doc.get_toc()
            
            for entry in toc:
                level, title, page_num = entry
                toc_entries.append({
                    "level": level,
                    "title": title.strip(),
                    "page_number": page_num
                })
            
            doc.close()
            if toc_entries:
                logger.info(f"✅ Found {len(toc_entries)} TOC entries (bookmarks)")
        except Exception as e:
            logger.warning(f"⚠️ Could not extract PDF TOC: {e}")
        
        return toc_entries
    
    def _chunk_hierarchically(
        self, 
        pages_content: List[Dict[str, Any]], 
        filename: str,
        subject: str,
        toc: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Chunk content based on TOC-defined chapters.
        Keeps chapters whole unless they exceed 6000 words.
        If a chapter is too large, it attempts to use nested TOC levels for division.
        """
        chunks = []
        MAX_WORD_LIMIT = 6000
        
        # Sort TOC by page number
        sorted_toc = sorted(toc, key=lambda x: x["page_number"])
        
        # If no TOC, use heuristic: each page is a chunk or use simple paragraph chunking
        if not sorted_toc:
            logger.info("ℹ️ No TOC found, falling back to heuristic structural chunking")
            return self._chunk_heuristically(pages_content, filename, subject)
        
        logger.info(f"📊 Chunking by TOC boundaries ({len(sorted_toc)} entries)")
        
        # Identify major chapters (Level 1)
        major_chapters = [entry for entry in sorted_toc if entry["level"] == 1]
        
        # If no Level 1 entries, treat all as potential chapter boundaries
        if not major_chapters:
            major_chapters = sorted_toc
            
        for i, entry in enumerate(major_chapters):
            title = entry["title"]
            start_page = entry["page_number"]
            # End page is the start of next major chapter, or end of document
            end_page = major_chapters[i+1]["page_number"] - 1 if i + 1 < len(major_chapters) else pages_content[-1]["page_number"]
            
            # Extract text for this range
            chapter_text = []
            for p in pages_content:
                if start_page <= p["page_number"] <= end_page:
                    chapter_text.append(p["text"])
            
            full_text = "\n\n".join(chapter_text).strip()
            if not full_text:
                continue
                
            word_count = len(full_text.split())
            
            # If chapter is within 6000 words, keep as one chunk
            if word_count <= MAX_WORD_LIMIT:
                chunks.append({
                    "content": full_text,
                    "metadata": {
                        "filename": filename,
                        "subject": subject,
                        "chapter": title,
                        "page_start": start_page,
                        "page_end": end_page,
                        "chunk_id": f"{filename}_{title.replace(' ', '_')[:30]}"
                    }
                })
            else:
                # Chapter is too large, try to subdivide using nested TOC entries
                logger.info(f"⚠️ Chapter '{title}' exceeds {MAX_WORD_LIMIT} words ({word_count} words). Subdividing...")
                
                # Find all TOC entries that fall within this chapter's page range (Level 2 or 3)
                sub_entries = [t for t in sorted_toc if t["page_number"] >= start_page and t["page_number"] <= end_page and t != entry]
                
                if sub_entries:
                    logger.info(f"   🔍 Found {len(sub_entries)} sub-sections. Using them for division.")
                    # Sort sub-entries and current entry to create sub-boundaries
                    all_boundaries = sorted([entry] + sub_entries, key=lambda x: x["page_number"])
                    
                    for j, sub_entry in enumerate(all_boundaries):
                        sub_title = sub_entry["title"]
                        sub_start = sub_entry["page_number"]
                        sub_end = all_boundaries[j+1]["page_number"] - 1 if j + 1 < len(all_boundaries) else end_page
                        
                        sub_text_list = []
                        for p in pages_content:
                            if sub_start <= p["page_number"] <= sub_end:
                                sub_text_list.append(p["text"])
                        
                        sub_full_text = "\n\n".join(sub_text_list).strip()
                        if not sub_full_text:
                            continue
                            
                        # If sub-section is still too large, split it minimally
                        if len(sub_full_text.split()) > MAX_WORD_LIMIT:
                            chunks.extend(self._split_minimally(sub_full_text, f"{title} > {sub_title}", filename, subject, sub_start, sub_end, limit=MAX_WORD_LIMIT))
                        else:
                            chunks.append({
                                "content": sub_full_text,
                                "metadata": {
                                    "filename": filename,
                                    "subject": subject,
                                    "chapter": title,
                                    "section": sub_title,
                                    "page_start": sub_start,
                                    "page_end": sub_end,
                                    "chunk_id": f"{filename}_{sub_title.replace(' ', '_')[:30]}"
                                }
                            })
                else:
                    # No sub-entries found, fall back to minimal splitting
                    logger.info("   ⚠️ No sub-sections found in TOC. Splitting content minimally.")
                    chunks.extend(self._split_minimally(full_text, title, filename, subject, start_page, end_page, limit=MAX_WORD_LIMIT))
        
        # Clean and Filter out noise chunks before returning
        initial_count = len(chunks)
        cleaned_chunks = []
        for c in chunks:
            c["content"] = self._clean_text(c["content"])
            if not self._should_filter_chunk(c["content"]):
                cleaned_chunks.append(c)
                
        if len(cleaned_chunks) < initial_count:
            logger.info(f"🧹 Filtered out {initial_count - len(cleaned_chunks)} noise chunks from hierarchical path")
            
        return cleaned_chunks

    def _split_minimally(self, text: str, title: str, filename: str, subject: str, start: int, end: int, limit: int = 6000) -> List[Dict[str, Any]]:
        """Split a large text into chunks of specified limit while preserving context."""
        words = text.split()
        chunks = []
        overlap = 300  # Increased overlap for larger chunks
        
        for i in range(0, len(words), limit - overlap):
            chunk_content = " ".join(words[i : i + limit])
            if len(chunk_content.split()) < self.min_words_per_chunk:
                continue
            chunks.append({
                "content": chunk_content,
                "metadata": {
                    "filename": filename,
                    "subject": subject,
                    "chapter": title,
                    "page_start": start,
                    "page_end": end,
                    "chunk_id": f"{filename}_{title.replace(' ', '_')[:25]}_{len(chunks)+1}"
                }
            })
        return chunks

    def _chunk_heuristically(self, pages_content, filename, subject):
        """Standard chunking for cases with no TOC."""
        # For now, let's keep it simple and just use the previous logic
        # but optimized for larger chunks as requested.
        all_text = "\n\n".join(p["text"] for p in pages_content)
        words = all_text.split()
        chunks = []
        # Use larger chunk size to respect "avoid further division"
        size = 1500
        overlap = 150
        
        for i in range(0, len(words), size - overlap):
            chunk_content = " ".join(words[i : i + size])
            if len(chunk_content.split()) < self.min_words_per_chunk:
                continue
            chunks.append({
                "content": chunk_content,
                "metadata": {
                    "filename": filename,
                    "subject": subject,
                    "chapter": "General Content",
                    "chunk_id": f"{filename}_heur_{len(chunks)+1}"
                }
            })
            
        # Clean and Filter out noise chunks before returning
        initial_count = len(chunks)
        cleaned_chunks = []
        for c in chunks:
            c["content"] = self._clean_text(c["content"])
            if not self._should_filter_chunk(c["content"]):
                cleaned_chunks.append(c)
                
        if len(cleaned_chunks) < initial_count:
            logger.info(f"🧹 Filtered out {initial_count - len(cleaned_chunks)} noise chunks from heuristic path")
            
        return cleaned_chunks
