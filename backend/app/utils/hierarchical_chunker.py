import re
import logging
from typing import List, Dict, Tuple, Optional
import nltk
from openai import OpenAI
import time
import pdfplumber

# Ensure NLTK sentence tokenizer is available
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab")

logger = logging.getLogger(__name__)


class HierarchicalChunker:
    """
    Improved hierarchical chunker that:
    1. Uses PDF structure (font sizes, positions) to detect headings
    2. Uses LLM-based detection for robust chapter/section identification
    3. Uses semantic chunking (by sentences/topics) instead of pure word count
    4. Preserves hierarchical metadata
    """

    def __init__(self, llm_client: OpenAI, embedder=None):
        """
        Initialize chunker.
        embedder parameter kept for backward compatibility but not used.
        """
        self.llm_client = llm_client

    # ---------- PDF STRUCTURE ANALYSIS ----------
    def extract_with_structure(self, pdf_path: str) -> List[Dict]:
        """
        Extract text with structure information (font sizes, positions) to detect headings.
        Returns text with metadata about potential headings.
        """
        structured_text = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract text with layout information
                    words = page.extract_words()
                    lines = []
                    current_line = []
                    current_y = None
                    
                    for word in words:
                        if current_y is None:
                            current_y = word['top']
                        
                        # If y position changed significantly, it's a new line
                        if abs(word['top'] - current_y) > 5:
                            if current_line:
                                lines.append({
                                    'text': ' '.join([w['text'] for w in current_line]),
                                    'font_size': current_line[0].get('size', 0),
                                    'is_bold': any(w.get('fontname', '').lower().find('bold') >= 0 for w in current_line),
                                    'y_position': current_y,
                                    'page': page_num
                                })
                            current_line = [word]
                            current_y = word['top']
                        else:
                            current_line.append(word)
                    
                    # Add last line
                    if current_line:
                        lines.append({
                            'text': ' '.join([w['text'] for w in current_line]),
                            'font_size': current_line[0].get('size', 0),
                            'is_bold': any(w.get('fontname', '').lower().find('bold') >= 0 for w in current_line),
                            'y_position': current_y,
                            'page': page_num
                        })
                    
                    structured_text.extend(lines)
        
        except Exception as e:
            logger.warning(f"Structure extraction failed, using plain text: {e}")
            # Fallback to plain text extraction
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                return [{'text': text, 'font_size': 0, 'is_bold': False, 'page': 1}]
        
        return structured_text

    def detect_headings_from_structure(self, structured_lines: List[Dict]) -> List[Tuple[int, str, str]]:
        """
        Detect headings based on font size, boldness, and formatting.
        Returns list of (index, heading_type, heading_text) tuples.
        """
        headings = []
        if not structured_lines:
            return headings
        
        # Calculate average font size
        font_sizes = [line.get('font_size', 0) for line in structured_lines if line.get('font_size', 0) > 0]
        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10
        
        for i, line in enumerate(structured_lines):
            text = line['text'].strip()
            font_size = line.get('font_size', 0)
            is_bold = line.get('is_bold', False)
            
            # Check if it's a potential heading
            is_large_font = font_size > avg_font_size * 1.2
            is_all_caps = text.isupper() and len(text) > 3
            is_short_line = len(text.split()) <= 10
            starts_with_number = bool(re.match(r'^\d+[\.\)\-\s]', text))
            
            # Heading detection criteria
            if (is_large_font or is_bold) and is_short_line:
                heading_type = "chapter" if (is_all_caps or starts_with_number) else "section"
                headings.append((i, heading_type, text))
            elif is_all_caps and is_short_line:
                headings.append((i, "section", text))
        
        return headings

    # ---------- LLM-BASED DETECTION (FALLBACK/ENHANCEMENT) ----------
    def detect_structure_with_llm(self, text: str, chunk_size: int = 2000) -> Dict:
        """
        Use LLM to identify chapters and sections in text.
        Processes in chunks to avoid token limits.
        """
        if not self.llm_client:
            return {"chapters": [], "sections": []}
        
        try:
            # Split text into manageable chunks for analysis
            words = text.split()
            chunks = []
            for i in range(0, len(words), chunk_size):
                chunk = ' '.join(words[i:i + chunk_size])
                chunks.append(chunk)
            
            prompt = f"""Analyze this NCERT Geography textbook text and identify:
1. Chapter titles (main topics, usually in ALL CAPS or numbered)
2. Section headings (subtopics within chapters, usually shorter, in ALL CAPS or bold)

For each chapter and section, provide:
- The exact heading text
- The line number or approximate position

Text to analyze:
{chunks[0][:1500]}  # Analyze first chunk only

Return format:
CHAPTERS:
- Chapter 1: [title]
- Chapter 2: [title]

SECTIONS:
- Section 1.1: [title]
- Section 1.2: [title]
"""
            
            response = self.llm_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing textbook structure and identifying hierarchical headings."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.0
            )
            
            result = response.choices[0].message.content
            # Parse result (simplified - you might want more robust parsing)
            return {"chapters": [], "sections": []}  # Placeholder
            
        except Exception as e:
            logger.warning(f"LLM structure detection failed: {e}")
            return {"chapters": [], "sections": []}

    # ---------- IMPROVED CHAPTER SPLITTING ----------
    def split_into_chapters(self, text: str, pdf_path: Optional[str] = None) -> List[Tuple[str, Dict]]:
        """
        Improved chapter detection using multiple strategies:
        1. PDF structure analysis (if pdf_path provided)
        2. Regex patterns (multiple variations)
        3. LLM-based detection (fallback)
        
        Returns list of (chapter_text, chapter_metadata) tuples.
        """
        chapters = []
        
        # Strategy 1: PDF structure analysis
        if pdf_path:
            try:
                structured_lines = self.extract_with_structure(pdf_path)
                headings = self.detect_headings_from_structure(structured_lines)
                if headings:
                    logger.info(f"📘 Detected {len(headings)} headings from PDF structure")
                    # Reconstruct chapters based on headings
                    for i, (idx, heading_type, heading_text) in enumerate(headings):
                        if heading_type == "chapter":
                            start_idx = idx
                            end_idx = headings[i + 1][0] if i + 1 < len(headings) else len(structured_lines)
                            chapter_text = '\n'.join([line['text'] for line in structured_lines[start_idx:end_idx]])
                            chapters.append((chapter_text, {"title": heading_text, "type": "structure_detected"}))
                    if chapters:
                        return chapters
            except Exception as e:
                logger.warning(f"PDF structure analysis failed: {e}")

        # Strategy 2: Enhanced regex patterns
        patterns = [
            # Old NCERT style
            r'(?:^|\n)(?:CHAPTER|Chapter|Unit|Lesson)\s*[-:]?\s*\d+\s*(?:\.|\s|:|-)\s*[A-Z][^\n]{0,100}',
            # New NCERT style - uppercase titles
            r'\n([A-Z][A-Z\s\-\&]{4,80})\n(?=\n|.{200,})',
            # Numbered headings
            r'(?:^|\n)\d+[\.\)]\s*[A-Z][^\n]{0,100}',
            # Bold/emphasized headings (if marked in text)
            r'\n\*\*([A-Z][^\n]{0,100})\*\*\n',
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))
            if matches:
                logger.info(f"📘 Detected {len(matches)} chapters using pattern: {pattern[:50]}")
                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                    chapter_text = text[start:end].strip()
                    if len(chapter_text) > 200:
                        chapters.append((chapter_text, {"title": match.group(0).strip(), "type": "regex_detected"}))
                if chapters:
                    return chapters

        # Strategy 3: LLM-based detection
        llm_result = self.detect_structure_with_llm(text)
        if llm_result.get("chapters"):
            logger.info("📘 Using LLM-detected chapters")
            # Parse and use LLM results (implementation needed)
            pass

        # Fallback: Semantic splitting by topic changes
        if not chapters:
            logger.warning("⚠️ No chapters detected — using semantic fallback")
            chapters = self._semantic_fallback_split(text)
        
        logger.info(f"✅ Final chapter count: {len(chapters)}")
        return chapters

    def _semantic_fallback_split(self, text: str, target_chunk_size: int = 3000) -> List[Tuple[str, Dict]]:
        """
        Fallback: Split by sentence boundaries and topic shifts.
        More intelligent than pure word count.
        """
        sentences = nltk.sent_tokenize(text)
        chapters = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            current_chunk.append(sentence)
            current_size += len(sentence.split())
            
            # Check for topic shift indicators
            is_topic_shift = any([
                sentence.strip().isupper() and len(sentence.split()) <= 8,
                bool(re.match(r'^\d+[\.\)]', sentence.strip())),
                len(sentence) < 50 and sentence.strip().endswith(':')
            ])
            
            if current_size >= target_chunk_size or is_topic_shift:
                if current_chunk:
                    chapter_text = ' '.join(current_chunk)
                    if len(chapter_text.strip()) > 200:
                        chapters.append((chapter_text, {"title": "Auto-detected Section", "type": "semantic_fallback"}))
                    current_chunk = []
                    current_size = 0
        
        # Add remaining
        if current_chunk:
            chapter_text = ' '.join(current_chunk)
            if len(chapter_text.strip()) > 200:
                chapters.append((chapter_text, {"title": "Auto-detected Section", "type": "semantic_fallback"}))
        
        return chapters

    # ---------- IMPROVED SECTION SPLITTING ----------
    def split_into_sections(self, chapter_text: str, chapter_metadata: Dict) -> List[Tuple[str, Dict]]:
        """
        Improved section detection using:
        1. Heading patterns (uppercase, bold markers)
        2. Numbered subsections
        3. Semantic boundaries
        """
        sections = []
        
        # Pattern 1: Uppercase headings
        pattern_uppercase = re.compile(r'\n([A-Z][A-Z\s\-\&]{3,60})\n')
        matches = list(pattern_uppercase.finditer(chapter_text))
        
        if matches:
            logger.info(f"📖 Found {len(matches)} uppercase section headings")
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(chapter_text)
                section_text = chapter_text[start:end].strip()
                if len(section_text) > 100:
                    sections.append((section_text, {"title": match.group(1), "type": "uppercase_heading"}))
            return sections

        # Pattern 2: Numbered subsections
        pattern_numbered = re.compile(r'\n\d+[\.\)]\s*([A-Z][^\n]{0,80})\n')
        matches = list(pattern_numbered.finditer(chapter_text))
        
        if matches:
            logger.info(f"📖 Found {len(matches)} numbered sections")
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(chapter_text)
                section_text = chapter_text[start:end].strip()
                if len(section_text) > 100:
                    sections.append((section_text, {"title": match.group(1), "type": "numbered"}))
            return sections

        # Fallback: Paragraph-based with semantic grouping
        paragraphs = [p.strip() for p in chapter_text.split("\n\n") if len(p.strip()) > 50]
        if len(paragraphs) > 1:
            # Group paragraphs into logical sections
            current_section = []
            current_section_size = 0
            target_size = 500  # words
            
            for para in paragraphs:
                current_section.append(para)
                current_section_size += len(para.split())
                
                if current_section_size >= target_size:
                    section_text = "\n\n".join(current_section)
                    sections.append((section_text, {"title": "Subsection", "type": "paragraph_group"}))
                    current_section = []
                    current_section_size = 0
            
            if current_section:
                section_text = "\n\n".join(current_section)
                sections.append((section_text, {"title": "Subsection", "type": "paragraph_group"}))
        
        if not sections:
            sections = [(chapter_text, {"title": chapter_metadata.get("title", "Chapter"), "type": "single_section"})]
        
        logger.info(f"✅ Section count: {len(sections)}")
        return sections

    # ---------- SEMANTIC CHUNK SPLITTING ----------
    def split_into_chunks(self, section_text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Improved chunking: Split by sentences first, then combine intelligently.
        Preserves sentence boundaries better than word-based splitting.
        """
        try:
            sentences = nltk.sent_tokenize(section_text)
        except Exception as e:
            logger.warning(f"Sentence tokenization failed: {e}, using word-based")
            sentences = section_text.split('. ')
        
        chunks = []
        current_chunk = []
        current_word_count = 0
        
        for sentence in sentences:
            words_in_sentence = len(sentence.split())
            
            # If adding this sentence exceeds chunk size, save current chunk
            if current_word_count + words_in_sentence > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                # Start new chunk with overlap (last few sentences)
                overlap_sentences = []
                overlap_words = 0
                for s in reversed(current_chunk):
                    overlap_words += len(s.split())
                    if overlap_words < overlap:
                        overlap_sentences.insert(0, s)
                    else:
                        break
                current_chunk = overlap_sentences
                current_word_count = sum(len(s.split()) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_word_count += words_in_sentence
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        # Filter out very short chunks
        chunks = [c for c in chunks if len(c.split()) > 50]
        
        logger.info(f"✂️ Created {len(chunks)} semantic chunks")
        return chunks

    # ---------- METADATA ENRICHMENT ----------
    def enrich_metadata_basic(self, chunk_index: int, chapter_index: int, section_index: int, 
                            source_name: str, chapter_metadata: Dict, section_metadata: Dict) -> Dict:
        """Enhanced metadata with structure information"""
        metadata = {
            "subject": "Geography",
            "chapter_id": chapter_index,
            "chapter_title": chapter_metadata.get("title", f"Chapter {chapter_index}"),
            "section_id": section_index,
            "section_title": section_metadata.get("title", f"Section {section_index}"),
            "chunk_id": f"{chapter_index}_{section_index}_{chunk_index}",
            "source_name": source_name,
            "detection_method": f"{chapter_metadata.get('type', 'unknown')}_{section_metadata.get('type', 'unknown')}",
            "domain": "TBD",  # For LLM enrichment later
            "topic": "TBD",   # For LLM enrichment later
        }
        return metadata

    # ---------- MAIN PROCESS ----------
    def process_text(self, text: str, source_name: str, pdf_path: Optional[str] = None) -> List[Dict]:
        """
        Full pipeline with improved detection methods.
        """
        logger.info(f"📘 Starting improved text processing for {source_name}...")
        start_time = time.time()

        # Get chapters with metadata
        chapters_with_metadata = self.split_into_chapters(text, pdf_path)
        processed_data = []

        for chapter_index, (chapter_text, chapter_metadata) in enumerate(chapters_with_metadata, start=1):
            logger.info(f"Processing chapter {chapter_index}: {chapter_metadata.get('title', 'Unknown')}")
            
            # Get sections with metadata
            sections_with_metadata = self.split_into_sections(chapter_text, chapter_metadata)
            
            for section_index, (section_text, section_metadata) in enumerate(sections_with_metadata, start=1):
                logger.info(f"  Processing section {section_index}: {section_metadata.get('title', 'Unknown')}")
                
                # Split into chunks
                chunks = self.split_into_chunks(section_text)
                
                for chunk_index, chunk in enumerate(chunks, start=1):
                    metadata = self.enrich_metadata_basic(
                        chunk_index, chapter_index, section_index,
                        source_name, chapter_metadata, section_metadata
                    )
                    processed_data.append({"text": chunk, "metadata": metadata})
                    logger.debug(f"    ✅ Chunk {chunk_index}: {metadata.get('chapter_title')} > {metadata.get('section_title')}")

        elapsed = round(time.time() - start_time, 2)
        logger.info(f"✅ Completed processing for {source_name} in {elapsed}s. Total chunks: {len(processed_data)}")
        return processed_data


# ---------- DEV TEST ----------
if __name__ == "__main__":
    sample_text = """
    RESOURCES AND DEVELOPMENT
    You have studied that resources are everything available in our environment which can be used to satisfy our needs.

    TYPES OF RESOURCES
    On the basis of origin – biotic and abiotic.

    SOIL DEGRADATION
    Soil erosion and depletion are serious problems.

    WATER RESOURCES
    India has large freshwater reserves but faces seasonal shortages.
    """
    import os
    source_name = "NCERT Class 10 Geography"
    llm_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    chunker = HierarchicalChunker(llm_client=llm_client)
    result = chunker.process_text(sample_text, source_name)
    print(f"Total chunks created: {len(result)}")
    for item in result[:3]:
        print(item)
