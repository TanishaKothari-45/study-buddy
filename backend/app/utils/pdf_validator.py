"""
PDF and text validation utilities
Detects watermarks, poor extraction, gibberish, and other quality issues
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Common watermark patterns
WATERMARK_PATTERNS = [
    r'gc\s*leon',
    r'gc\s*leonard',
    r'www\.\w+\.com',
    r'www\.\w+\.in',
    r'copyright',
    r'©\s*\d{4}',
    r'confidential',
    r'draft',
    r'watermark',
    r'page\s*\d+\s*of\s*\d+',  # Page numbers that repeat
    r'^\d+$',  # Lines with only numbers (often page numbers)
]

# Patterns that indicate poor extraction
POOR_EXTRACTION_PATTERNS = [
    r'[^\w\s]{10,}',  # Too many special characters in a row
    r'[A-Z]{20,}',  # Too many consecutive capitals (often OCR errors)
    r'[a-z]{30,}',  # Too many consecutive lowercase (often OCR errors)
    r'\d{15,}',  # Very long number sequences (often noise)
]

def detect_watermarks(text: str, pages_content: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Detect watermarks and repeated noise in text.
    Uses multiple strategies to catch various watermark patterns.
    Returns dict with detection results.
    """
    text_lower = text.lower()
    watermark_matches = []
    
    # Strategy 1: Check for known watermark patterns
    for pattern in WATERMARK_PATTERNS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE | re.MULTILINE)
        if matches:
            watermark_matches.extend(matches)
    
    # Strategy 2: Check for excessive line repetition (most common watermark pattern)
    lines = text.split('\n')
    line_counts = {}
    for line in lines:
        line_stripped = line.strip()
        # Ignore very short lines and common page elements
        if len(line_stripped) > 5 and not line_stripped.isdigit():
            line_counts[line_stripped] = line_counts.get(line_stripped, 0) + 1
    
    # Find lines that repeat excessively (likely watermarks)
    # Threshold: if a line appears more than 3 times, it's suspicious
    # If it appears more than 10 times, it's definitely a watermark
    suspicious_lines = {line: count for line, count in line_counts.items() if count > 3}
    repeated_lines = {line: count for line, count in line_counts.items() if count > 10}
    
    # Strategy 3: Check for text that appears on every page (typical watermark behavior)
    page_watermarks = []
    if pages_content and len(pages_content) > 1:
        # Get text from each page
        page_texts = [page.get("text", "").lower() for page in pages_content if page.get("text")]
        
        # Find common phrases/words across pages
        if len(page_texts) > 1:
            # Split into words and find common ones
            all_words = []
            for page_text in page_texts:
                words = set(re.findall(r'\b\w{3,}\b', page_text))  # Words 3+ chars
                all_words.append(words)
            
            # Find words that appear in most pages (likely watermark)
            if all_words:
                common_words = set.intersection(*all_words[:5])  # Check first 5 pages
                # Filter out common English words
                common_english_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}
                watermark_words = common_words - common_english_words
                
                if len(watermark_words) > 0:
                    # Check if these words appear excessively
                    for word in list(watermark_words)[:10]:  # Check first 10
                        count = text_lower.count(word)
                        if count > len(pages_content) * 2:  # Appears more than 2x per page
                            page_watermarks.append((word, count))
    
    # Strategy 4: Check for common watermark phrases (any name/company)
    watermark_phrases = [
        'gc leon', 'gc leonard', 'www.', 'copyright', 'confidential',
        'watermark', 'draft', 'sample', 'preview', 'do not copy',
        'proprietary', 'internal use', 'restricted'
    ]
    found_phrases = []
    for phrase in watermark_phrases:
        if phrase in text_lower:
            count = text_lower.count(phrase)
            if count > 3:  # Appears multiple times
                found_phrases.append((phrase, count))
    
    # Strategy 5: Detect any text that appears too frequently (generic watermark detection)
    # Split text into sentences/phrases and check repetition
    sentences = re.split(r'[.!?\n]+', text)
    sentence_counts = {}
    for sentence in sentences:
        sentence_stripped = sentence.strip()
        if len(sentence_stripped) > 10 and len(sentence_stripped) < 200:  # Reasonable sentence length
            sentence_counts[sentence_stripped] = sentence_counts.get(sentence_stripped, 0) + 1
    
    # Find sentences that repeat (likely watermarks)
    repeated_sentences = {sent: count for sent, count in sentence_counts.items() if count > 5}
    
    # Strategy 6: Check for URL patterns (common in watermarks)
    url_pattern = r'https?://[^\s]+|www\.[^\s]+'
    urls = re.findall(url_pattern, text_lower)
    if len(urls) > 5:  # Multiple URLs suggest watermark
        watermark_matches.extend(urls[:10])
    
    # Strategy 7: Check for email patterns (common in watermarks)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text_lower)
    if len(emails) > 3:  # Multiple emails suggest watermark
        watermark_matches.extend(emails[:5])
    
    # Calculate total watermark indicators
    total_indicators = (
        len(watermark_matches) + 
        len(repeated_lines) + 
        len(found_phrases) + 
        len(page_watermarks) +
        len(repeated_sentences)
    )
    
    # Determine if watermarks are present
    # More lenient: need multiple indicators or very strong single indicator
    has_watermarks = (
        len(repeated_lines) > 0 or  # Strong indicator: lines repeating >10 times
        (len(suspicious_lines) > 3 and total_indicators > 5) or  # Multiple suspicious patterns
        len(repeated_sentences) > 2 or  # Sentences repeating
        len(page_watermarks) > 2  # Words appearing on every page
    )
    
    return {
        'has_watermarks': has_watermarks,
        'watermark_matches': watermark_matches[:10],  # Limit to first 10
        'repeated_lines': dict(list(repeated_lines.items())[:5]),  # Top 5 repeated lines
        'suspicious_lines': dict(list(suspicious_lines.items())[:10]),  # Top 10 suspicious lines
        'repeated_sentences': dict(list(repeated_sentences.items())[:5]),  # Top 5 repeated sentences
        'watermark_phrases': found_phrases,
        'page_watermarks': page_watermarks[:10],  # Words appearing on every page
        'total_watermark_indicators': total_indicators,
        'detection_methods': {
            'pattern_matches': len(watermark_matches),
            'repeated_lines': len(repeated_lines),
            'suspicious_lines': len(suspicious_lines),
            'repeated_sentences': len(repeated_sentences),
            'page_watermarks': len(page_watermarks),
            'known_phrases': len(found_phrases)
        }
    }

def check_text_quality(text: str) -> Dict[str, Any]:
    """
    Check text quality - detect gibberish, poor extraction, etc.
    Returns dict with quality metrics and issues.
    """
    if not text or len(text.strip()) < 50:
        return {
            'is_valid': False,
            'reason': 'Text too short or empty',
            'quality_score': 0.0
        }
    
    issues = []
    quality_score = 100.0
    
    # Check 1: Ratio of alphabetic characters
    alpha_chars = sum(1 for c in text if c.isalpha())
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0
    
    if alpha_ratio < 0.5:
        issues.append(f'Low alphabetic ratio: {alpha_ratio:.2%} (expected >50%)')
        quality_score -= 30
    
    # Check 2: Excessive special characters
    special_chars = sum(1 for c in text if not c.isalnum() and c not in ' \n\t.,;:!?()-')
    special_ratio = special_chars / len(text) if len(text) > 0 else 0
    
    if special_ratio > 0.3:
        issues.append(f'Too many special characters: {special_ratio:.2%} (expected <30%)')
        quality_score -= 20
    
    # Check 3: Check for poor extraction patterns
    poor_extraction_found = False
    for pattern in POOR_EXTRACTION_PATTERNS:
        if re.search(pattern, text):
            poor_extraction_found = True
            issues.append(f'Poor extraction pattern detected: {pattern}')
            quality_score -= 15
            break
    
    # Check 4: Word length distribution (gibberish often has unusual word lengths)
    words = text.split()
    if words:
        avg_word_length = sum(len(w) for w in words) / len(words)
        if avg_word_length > 15:  # Unusually long words
            issues.append(f'Unusual average word length: {avg_word_length:.1f} (likely gibberish)')
            quality_score -= 20
        if avg_word_length < 2:  # Too many single characters
            issues.append(f'Too many single-character "words" (likely noise)')
            quality_score -= 15
    
    # Check 5: Repetition ratio (watermarks/noise have high repetition)
    unique_words = len(set(words))
    total_words = len(words)
    uniqueness_ratio = unique_words / total_words if total_words > 0 else 0
    
    if uniqueness_ratio < 0.3:  # Less than 30% unique words
        issues.append(f'High repetition: {uniqueness_ratio:.2%} unique words (likely watermark/noise)')
        quality_score -= 25
    
    # Check 6: Meaningful content ratio (check for actual sentences)
    sentences = re.split(r'[.!?]+\s+', text)
    meaningful_sentences = [s for s in sentences if len(s.split()) > 5]  # At least 5 words
    sentence_ratio = len(meaningful_sentences) / len(sentences) if sentences else 0
    
    if sentence_ratio < 0.3:
        issues.append(f'Low meaningful sentence ratio: {sentence_ratio:.2%} (likely noise)')
        quality_score -= 20
    
    # Check 7: Check for common watermark text (no pages_content for single text check)
    watermark_check = detect_watermarks(text, pages_content=None)
    if watermark_check['has_watermarks']:
        issues.append(f'Watermarks detected: {watermark_check["total_watermark_indicators"]} indicators')
        quality_score -= 30
    
    quality_score = max(0, quality_score)  # Don't go below 0
    
    return {
        'is_valid': quality_score >= 50 and len(issues) < 3,  # Valid if score >= 50 and < 3 major issues
        'quality_score': quality_score,
        'issues': issues,
        'metrics': {
            'alpha_ratio': alpha_ratio,
            'special_ratio': special_ratio,
            'uniqueness_ratio': uniqueness_ratio,
            'sentence_ratio': sentence_ratio,
            'avg_word_length': avg_word_length if words else 0,
            'total_words': total_words,
            'unique_words': unique_words
        },
        'watermark_check': watermark_check
    }

def validate_pdf_text(pages_content: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
    """
    Validate PDF text extraction quality.
    Returns validation result with recommendations.
    """
    if not pages_content:
        return {
            'is_valid': False,
            'reason': 'No text extracted from PDF',
            'recommendation': 'PDF may be image-based or corrupted. Try OCR or convert to images first.'
        }
    
    # Combine all pages
    full_text = "\n".join(page.get("text", "") for page in pages_content if page.get("text"))
    
    if not full_text or len(full_text.strip()) < 200:
        return {
            'is_valid': False,
            'reason': f'Very little text extracted ({len(full_text)} chars)',
            'recommendation': 'PDF may be scanned/image-based. Consider using OCR or converting to images first.'
        }
    
    # Check text quality
    quality_result = check_text_quality(full_text)
    
    # Check for watermarks (pass pages_content for page-level detection)
    watermark_result = detect_watermarks(full_text, pages_content)
    
    # Overall validation
    is_valid = quality_result['is_valid'] and not watermark_result['has_watermarks']
    
    result = {
        'is_valid': is_valid,
        'quality_score': quality_result['quality_score'],
        'issues': quality_result['issues'],
        'watermark_detected': watermark_result['has_watermarks'],
        'total_pages': len(pages_content),
        'total_text_length': len(full_text),
        'metrics': quality_result['metrics']
    }
    
    # Add recommendations
    if not is_valid:
        recommendations = []
        
        if watermark_result['has_watermarks']:
            recommendations.append('PDF contains watermarks or repeated noise. Consider using a clean version of the PDF.')
        
        if quality_result['quality_score'] < 50:
            recommendations.append('Text quality is poor. PDF may be scanned/image-based. Consider using OCR.')
        
        if len(quality_result['issues']) >= 3:
            recommendations.append('Multiple quality issues detected. PDF extraction may have failed. Check if PDF is corrupted.')
        
        result['recommendation'] = ' | '.join(recommendations) if recommendations else 'Please check PDF quality and try again.'
    else:
        result['recommendation'] = 'Text extraction looks good!'
    
    return result

def validate_txt_text(text: str, filename: str) -> Dict[str, Any]:
    """
    Validate TXT file text quality.
    Returns validation result with recommendations.
    """
    if not text or len(text.strip()) < 200:
        return {
            'is_valid': False,
            'reason': f'Text file is too short ({len(text)} chars)',
            'recommendation': 'File may be empty or corrupted.'
        }
    
    # Check text quality
    quality_result = check_text_quality(text)
    
    # Check for watermarks (no pages_content for TXT files)
    watermark_result = detect_watermarks(text, pages_content=None)
    
    # Overall validation
    is_valid = quality_result['is_valid'] and not watermark_result['has_watermarks']
    
    result = {
        'is_valid': is_valid,
        'quality_score': quality_result['quality_score'],
        'issues': quality_result['issues'],
        'watermark_detected': watermark_result['has_watermarks'],
        'total_text_length': len(text),
        'metrics': quality_result['metrics']
    }
    
    # Add recommendations
    if not is_valid:
        recommendations = []
        
        if watermark_result['has_watermarks']:
            recommendations.append('TXT file contains watermarks or repeated noise. Use a clean version.')
        
        if quality_result['quality_score'] < 50:
            recommendations.append('Text quality is poor. File may contain gibberish or noise.')
        
        result['recommendation'] = ' | '.join(recommendations) if recommendations else 'Please check file quality and try again.'
    else:
        result['recommendation'] = 'Text file looks good!'
    
    return result

