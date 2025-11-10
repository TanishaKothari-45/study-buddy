"""
Hierarchical chunker for PDFs and text files

Detects document structure (chapters, sections) and chunks accordingly.
Uses font size analysis for PDFs to detect hierarchy.
"""

import logging
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
        
    def process_pdf(self, pdf_path: str, filename: str, subject: str = "Geography") -> List[Dict[str, Any]]:
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
            
            # Extract text from PDF using pdf_reader
            pages_content = extract_text_from_pdf(pdf_path)
            
            if not pages_content:
                logger.warning(f"⚠️ No content extracted from {filename}")
                return []
            
            # Detect structure from PDF (chapters, sections)
            structure = self._detect_pdf_structure(pdf_path)
            
            # Chunk the content hierarchically
            chunks = self._chunk_hierarchically(pages_content, filename, subject, structure)
            
            logger.info(f"✅ Created {len(chunks)} chunks from {filename}")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ Error processing PDF {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
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
    
    def _detect_pdf_structure(self, pdf_path: str) -> Dict[str, Any]:
        """
        Detect document structure from PDF using font size analysis.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with structure information (chapters, sections, etc.)
        """
        structure = {
            "chapters": [],
            "sections": [],
            "page_structure": {}
        }
        
        try:
            doc = fitz.open(pdf_path)
            
            # Analyze font sizes to detect hierarchy
            font_sizes = {}
            for page_num in range(min(10, len(doc))):  # Analyze first 10 pages
                page = doc[page_num]
                blocks = page.get_text("dict")["blocks"]
                
                for block in blocks:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                size = span["size"]
                                text = span["text"].strip()
                                
                                if size not in font_sizes:
                                    font_sizes[size] = []
                                font_sizes[size].append(text)
            
            doc.close()
            
            # Identify chapter/section patterns from font sizes
            # Larger fonts are likely chapter titles
            if font_sizes:
                sorted_sizes = sorted(font_sizes.keys(), reverse=True)
                # Largest fonts are likely chapters
                if len(sorted_sizes) > 0:
                    structure["chapter_font_size"] = sorted_sizes[0]
                if len(sorted_sizes) > 1:
                    structure["section_font_size"] = sorted_sizes[1]
            
        except Exception as e:
            logger.warning(f"⚠️ Could not detect PDF structure: {e}")
        
        return structure
    
    def _chunk_hierarchically(
        self, 
        pages_content: List[Dict[str, Any]], 
        filename: str,
        subject: str,
        structure: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Chunk pages content hierarchically.
        
        Args:
            pages_content: List of page dictionaries with 'text' and 'page_number'
            filename: Name of the file
            subject: Subject area
            structure: Structure information from PDF analysis
            
        Returns:
            List of chunk dictionaries
        """
        chunks = []
        current_chunk = []
        current_words = 0
        current_chapter = "Introduction"
        current_section = "General"
        chunk_id = 1
        
        for page_data in pages_content:
            page_text = page_data.get("text", "")
            page_number = page_data.get("page_number", 0)
            
            if not page_text.strip():
                continue
            
            # Split into paragraphs
            paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
            
            for para in paragraphs:
                para_words = len(para.split())
                
                # Check if paragraph looks like a chapter/section header
                # (short, all caps, or starts with number)
                if para_words < 10 and (para.isupper() or para[0].isdigit()):
                    # Save current chunk before starting new section
                    if current_chunk:
                        chunk_text = '\n\n'.join(current_chunk)
                        if len(chunk_text.split()) >= self.min_words_per_chunk:
                            chunks.append({
                                "content": chunk_text,
                                "metadata": {
                                    "filename": filename,
                                    "subject": subject,
                                    "chapter": current_chapter,
                                    "section": current_section,
                                    "page_start": page_number,
                                    "page_end": page_number,
                                    "chunk_id": f"{filename}_{chunk_id}"
                                }
                            })
                            chunk_id += 1
                    
                    # Update chapter/section
                    if para_words < 5:
                        current_chapter = para[:100]  # Limit length
                    else:
                        current_section = para[:100]
                    
                    current_chunk = []
                    current_words = 0
                    continue
                
                # Add paragraph to current chunk
                if current_words + para_words > self.chunk_size_words and current_chunk:
                    # Save current chunk
                    chunk_text = '\n\n'.join(current_chunk)
                    if len(chunk_text.split()) >= self.min_words_per_chunk:
                        chunks.append({
                            "content": chunk_text,
                            "metadata": {
                                "filename": filename,
                                "subject": subject,
                                "chapter": current_chapter,
                                "section": current_section,
                                "page_start": page_number,
                                "page_end": page_number,
                                "chunk_id": f"{filename}_{chunk_id}"
                            }
                        })
                        chunk_id += 1
                    
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
                        "chapter": current_chapter,
                        "section": current_section,
                        "page_start": pages_content[-1].get("page_number", 0) if pages_content else 0,
                        "page_end": pages_content[-1].get("page_number", 0) if pages_content else 0,
                        "chunk_id": f"{filename}_{chunk_id}"
                    }
                })
        
        return chunks
