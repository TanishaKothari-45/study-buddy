"""
Extract specific sections (Geography/Environment) from PDF magazines
"""

import fitz  # PyMuPDF
import re
import logging
import os
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

def extract_relevant_sections(pdf_path: str, keywords: List[str] = None, output_suffix: str = "_geo_env") -> Optional[str]:
    """
    Extract pages containing Geography and Environment sections from a PDF magazine.
    
    Args:
        pdf_path: Path to the input PDF
        keywords: List of keywords to search for (default: ['geography', 'environment'])
        output_suffix: Suffix to add to output filename
        
    Returns:
        Path to the extracted PDF, or None if no sections found
    """
    if keywords is None:
        keywords = ['geography', 'environment']
    
    logger.info(f"📖 Extracting relevant sections from: {pdf_path}")
    logger.info(f"   Looking for sections: {keywords}")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        logger.info(f"   Total pages in PDF: {total_pages}")
        
        # Step 1: Read TOC (usually in first 5 pages)
        toc_text = ""
        toc_pages = min(5, total_pages)
        logger.info(f"   Reading TOC from first {toc_pages} pages...")
        
        for i in range(toc_pages):
            page = doc.load_page(i)
            toc_text += page.get_text("text")
        
        # Step 2: Find Environment and Geography sections by name in TOC
        logger.info("   🔍 Searching for section headings in TOC...")
        lines = [line.strip() for line in toc_text.split("\n") if line.strip()]
        
        # Extract all section headings with page numbers from TOC
        all_sections = []
        # Also track section headers without page numbers (e.g., "5. ENVIRONMENT")
        section_headers = {}  # Maps major section number to (name, line_index)
        
        for idx, line in enumerate(lines):
            # First, check for section headers like "5. ENVIRONMENT" (no page number)
            header_match = re.match(r'^(\d+)\.\s*([A-Z][A-Z\s&]+)$', line.strip())
            if header_match:
                major_num = int(header_match.group(1))
                section_name = header_match.group(2).strip()
                section_headers[major_num] = (section_name, idx)
                logger.debug(f"   Found section header: {major_num}. {section_name}")
                continue
            
            # Look for "Section Name ... PageNumber" pattern
            # Handle patterns like "5.1. 10 Years of SDGs... 30" 
            match = re.search(r'(.+?)[\s\x08\u200b\u200c\u200d\ufeff\.…�]+(\d{1,3})\s*$', line.strip())
            if match:
                section_name = match.group(1).strip()
                # Clean special characters from section name
                section_name = re.sub(r'[\x08\u200b\u200c\u200d\ufeff…�]+', '', section_name).strip()
                # Remove trailing dots
                section_name = section_name.rstrip('.')
                page_num = int(match.group(2))
                # Filter out lines that are just numbers or too short
                if len(section_name) > 2 and not section_name.isdigit() and page_num > 0:
                    all_sections.append((section_name, page_num, idx))
        
        logger.debug(f"   Found {len(all_sections)} sections with page numbers")
        logger.debug(f"   Found {len(section_headers)} section headers")
        
        # Find target sections - check both section headers and items
        target_sections = []
        
        # First, check section headers (e.g., "5. ENVIRONMENT")
        for major_num, (header_name, header_idx) in section_headers.items():
            header_lower = header_name.lower()
            for kw in keywords:
                if kw.lower() in header_lower:
                    # Find the first sub-section under this header to get the page number
                    # Look for items like "5.1. ..." 
                    for section_name, page_num, sec_idx in all_sections:
                        if section_name.startswith(f"{major_num}."):
                            target_sections.append((kw, page_num, f"{major_num}. {header_name}"))
                            logger.info(f"   ✅ Found '{kw}' section: '{major_num}. {header_name}' starting at page {page_num}")
                            break
                    break
        
        # Also check individual section items for keywords
        for section_name, page_num, sec_idx in all_sections:
            section_lower = section_name.lower()
            for kw in keywords:
                if kw.lower() in section_lower:
                    # Avoid duplicates
                    if not any(kw == t[0] and page_num == t[1] for t in target_sections):
                        target_sections.append((kw, page_num, section_name))
                        logger.info(f"   ✅ Found '{kw}' in section: '{section_name}' at page {page_num}")
                    break
        
        if not target_sections:
            logger.warning(f"⚠️ No {' or '.join(keywords)} sections found in TOC")
            doc.close()
            return None
        
        # Step 3: Determine page ranges for each target section
        # Sort all sections by page number to find boundaries
        # all_sections now has (name, page_num, idx) tuples
        all_sections_sorted = sorted(all_sections, key=lambda x: x[1])
        page_ranges = []
        
        for kw, start_page, section_name in target_sections:
            logger.info(f"\n   📑 Processing '{kw}' section (page {start_page})...")
            
            # Find the next MAJOR section after this one (not sub-sections)
            # Look for sections that start with a different major number (e.g., "5." -> "6.")
            current_major_num = None
            if section_name and re.match(r'^(\d+)\.', section_name):
                current_major_num = int(re.match(r'^(\d+)\.', section_name).group(1))
            
            end_page = total_pages
            next_section = None
            
            for name, page, idx in all_sections_sorted:
                if page > start_page:
                    # Check if this is a different major section
                    if current_major_num:
                        name_match = re.match(r'^(\d+)\.', name)
                        if name_match:
                            next_major_num = int(name_match.group(1))
                            # If it's a different major section, stop here
                            if next_major_num != current_major_num:
                                end_page = page - 1
                                next_section = name
                                logger.info(f"      📍 Ends at page {end_page} (before major section '{next_section}' at page {page})")
                                break
                    else:
                        # No major number detected, use first next section
                        end_page = page - 1
                        next_section = name
                        logger.info(f"      📍 Ends at page {end_page} (before '{next_section}' at page {page})")
                        break
            
            # If we didn't find a different major section, look for next section that's far enough away
            if end_page == total_pages:
                for name, page, idx in all_sections_sorted:
                    if page > start_page + 5:  # At least 5 pages away
                        end_page = page - 1
                        next_section = name
                        logger.info(f"      📍 Ends at page {end_page} (before '{next_section}' at page {page})")
                        break
            
            # Find the actual start page - look for the first page with this major section number
            # If section is "5.4. Environment", find the first page with "5.1." or "5. ENVIRONMENT"
            actual_start_page = start_page
            if current_major_num:
                # Look for the first subsection of this major section
                for name, page, idx in all_sections_sorted:
                    name_match = re.match(r'^(\d+)\.', name)
                    if name_match:
                        section_major_num = int(name_match.group(1))
                        if section_major_num == current_major_num and page < start_page:
                            actual_start_page = page
                            logger.info(f"      📍 Found earlier subsection '{name}' at page {page}, starting from there")
                            break
                
                # Also check if there's a major section heading page (like "5. ENVIRONMENT")
                # Look backwards from start_page for the major heading
                for check_page in range(max(1, start_page - 5), start_page):
                    try:
                        page_text = doc.load_page(check_page - 1).get_text("text")
                        # Check if this page has the major section heading
                        if re.search(rf'^{current_major_num}\.\s*{kw}', page_text, re.IGNORECASE | re.MULTILINE):
                            actual_start_page = min(actual_start_page, check_page)
                            logger.info(f"      📍 Found major section heading '{current_major_num}. {kw}' at page {check_page}")
                            break
                    except:
                        pass
            
            # Start from the actual start page (or 1 page before if we found a major heading)
            # If we found an earlier subsection, use that page directly (it's the first content page)
            start_idx = max(0, actual_start_page - 1)  # Start 1 page before to include any heading
            end_idx = min(end_page - 1, total_pages - 1)
            
            if end_idx >= start_idx:
                page_ranges.append((start_idx, end_idx))
                logger.info(f"      ✅ Range: pages {start_idx + 1}-{end_idx + 1}")
            else:
                logger.warning(f"      ⚠️ Invalid range for '{kw}' section")
        
        # Merge overlapping ranges
        merged_ranges = []
        for start, end in sorted(page_ranges):
            if merged_ranges and start <= merged_ranges[-1][1] + 1:
                # Merge with previous range
                merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))
            else:
                merged_ranges.append((start, end))
        
        logger.info(f"   📚 Extracting {len(merged_ranges)} page range(s)")
        
        # Step 4: Create new PDF with extracted pages
        new_doc = fitz.open()
        total_extracted = 0
        
        for start, end in merged_ranges:
            logger.info(f"   📥 Extracting pages {start + 1}-{end + 1}...")
            new_doc.insert_pdf(doc, from_page=start, to_page=end)
            total_extracted += (end - start + 1)
        
        # Generate output filename
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_dir = os.path.dirname(pdf_path)
        output_path = os.path.join(output_dir, f"{base_name}{output_suffix}.pdf")
        
        new_doc.save(output_path)
        new_doc.close()
        doc.close()
        
        logger.info(f"✅ Successfully extracted {total_extracted} pages")
        logger.info(f"   📁 Saved to: {output_path}")
        logger.info(f"   📊 Original: {total_pages} pages → Extracted: {total_extracted} pages")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Error extracting sections: {e}")
        import traceback
        traceback.print_exc()
        return None


def extract_sections_with_validation(pdf_path: str, keywords: List[str] = None) -> Optional[str]:
    """
    Extract sections and validate that we got meaningful content.
    
    Returns:
        Path to extracted PDF if successful, None otherwise
    """
    extracted_path = extract_relevant_sections(pdf_path, keywords)
    
    if not extracted_path or not os.path.exists(extracted_path):
        return None
    
    # Validate extracted PDF has content
    try:
        doc = fitz.open(extracted_path)
        if len(doc) == 0:
            logger.error("❌ Extracted PDF is empty")
            doc.close()
            os.remove(extracted_path)
            return None
        
        # Check if it has meaningful text (not just images)
        total_text = ""
        for i in range(min(3, len(doc))):
            total_text += doc.load_page(i).get_text("text")
        
        if len(total_text.strip()) < 100:
            logger.warning("⚠️ Extracted PDF has very little text (might be image-based)")
        
        doc.close()
        return extracted_path
        
    except Exception as e:
        logger.error(f"❌ Error validating extracted PDF: {e}")
        if os.path.exists(extracted_path):
            os.remove(extracted_path)
        return None

