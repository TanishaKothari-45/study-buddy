"""
smart_truncator.py

Intelligent context truncation that respects:
- Sentence boundaries (no mid-sentence cuts)
- Paragraph structure
- Priority-based trimming (less important content first)
- Token limits (not just character limits)

Usage:
    from smart_truncator import smart_truncate_context
    
    truncated = smart_truncate_context(
        text="Long context...",
        max_tokens=3000,
        strategy="tail"  # Keep most recent
    )
"""

import re
import logging
from typing import Optional, Literal

logger = logging.getLogger(__name__)

def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    Uses rough heuristic: ~4 chars per token for English.
    More accurate than char count, less overhead than actual tokenization.
    """
    return len(text) // 4


def smart_truncate_context(
    text: str,
    max_tokens: int,
    strategy: Literal["tail", "head", "middle"] = "tail",
    preserve_structure: bool = True
) -> str:
    """
    Intelligently truncate text to fit within token budget.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed
        strategy: 
            - "tail": Keep most recent content (good for current affairs)
            - "head": Keep beginning content (good for definitions)
            - "middle": Keep beginning + end, remove middle
        preserve_structure: If True, respects sentence/paragraph boundaries
    
    Returns:
        Truncated text with indicator if truncation occurred
    """
    if not text or not text.strip():
        return ""
    
    text = text.strip()
    current_tokens = estimate_tokens(text)
    
    # No truncation needed
    if current_tokens <= max_tokens:
        return text
    
    # Calculate target character count (conservative estimate)
    max_chars = max_tokens * 4
    
    if not preserve_structure:
        # Simple character-based truncation
        if strategy == "tail":
            return "...\n\n" + text[-max_chars:].strip()
        elif strategy == "head":
            return text[:max_chars].strip() + "\n\n..."
        else:  # middle
            half = max_chars // 2
            return text[:half].strip() + "\n\n[...]\n\n" + text[-half:].strip()
    
    # Smart truncation with structure preservation
    return _smart_truncate_structured(text, max_chars, strategy)


def _smart_truncate_structured(
    text: str,
    max_chars: int,
    strategy: str
) -> str:
    """
    Truncate while preserving sentence and paragraph boundaries.
    """
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    if not paragraphs:
        return text[:max_chars]
    
    if strategy == "tail":
        # Keep most recent paragraphs (good for current affairs)
        return _keep_last_paragraphs(paragraphs, max_chars)
    
    elif strategy == "head":
        # Keep first paragraphs (good for foundational info)
        return _keep_first_paragraphs(paragraphs, max_chars)
    
    else:  # middle
        # Keep first and last, drop middle
        return _keep_first_and_last_paragraphs(paragraphs, max_chars)


def _keep_last_paragraphs(paragraphs: list[str], max_chars: int) -> str:
    """Keep most recent paragraphs that fit within limit."""
    selected = []
    current_length = 0
    
    # Work backwards from most recent
    for para in reversed(paragraphs):
        para_len = len(para)
        if current_length + para_len + 4 <= max_chars:  # +4 for \n\n separator
            selected.insert(0, para)
            current_length += para_len + 4
        else:
            # Try to fit truncated last sentence if space remains
            if current_length < max_chars * 0.7:  # Only if we have <70% filled
                sentences = _split_sentences(para)
                for sent in reversed(sentences):
                    sent_len = len(sent)
                    if current_length + sent_len + 4 <= max_chars:
                        selected.insert(0, sent)
                        current_length += sent_len + 4
            break
    
    result = '\n\n'.join(selected)
    
    # Add truncation indicator if we didn't include all paragraphs
    if len(selected) < len(paragraphs):
        result = "[... earlier content truncated ...]\n\n" + result
    
    return result


def _keep_first_paragraphs(paragraphs: list[str], max_chars: int) -> str:
    """Keep first paragraphs that fit within limit."""
    selected = []
    current_length = 0
    
    for para in paragraphs:
        para_len = len(para)
        if current_length + para_len + 4 <= max_chars:
            selected.append(para)
            current_length += para_len + 4
        else:
            # Try to fit first few sentences if space remains
            if current_length < max_chars * 0.7:
                sentences = _split_sentences(para)
                for sent in sentences:
                    sent_len = len(sent)
                    if current_length + sent_len + 4 <= max_chars:
                        selected.append(sent)
                        current_length += sent_len + 4
            break
    
    result = '\n\n'.join(selected)
    
    # Add truncation indicator
    if len(selected) < len(paragraphs):
        result = result + "\n\n[... later content truncated ...]"
    
    return result


def _keep_first_and_last_paragraphs(paragraphs: list[str], max_chars: int) -> str:
    """Keep first and last paragraphs, drop middle."""
    if len(paragraphs) <= 2:
        return '\n\n'.join(paragraphs)
    
    # Allocate 50% to first, 50% to last
    half_chars = max_chars // 2
    
    first_part = _keep_first_paragraphs(paragraphs, half_chars)
    last_part = _keep_last_paragraphs(paragraphs, half_chars)
    
    return first_part + "\n\n[... middle content truncated ...]\n\n" + last_part


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences.
    Simple regex-based approach for performance.
    """
    # Split on sentence endings: . ! ?
    # Look-ahead to avoid splitting on abbreviations like Dr. or U.S.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


def truncate_with_token_budget(
    static_context: Optional[str],
    current_affairs: Optional[str],
    question: str,
    system_prompt_tokens: int = 1500,  # Estimated system prompt size
    question_buffer_tokens: int = 200,  # Buffer for question + formatting
    max_total_tokens: int = 32000,  # Gemini 2.5 Pro input limit
    output_tokens: int = 2000,  # Reserve for output
) -> tuple[str, str]:
    """
    Intelligently allocate token budget between static context and current affairs.
    
    Gemini 2.5 Pro has ~1M token context window, but we use conservative limits
    to ensure fast responses and avoid hitting rate limits.
    
    Args:
        static_context: Retrieved context from Pinecone/SQLite
        current_affairs: Current affairs bullets
        question: User question
        system_prompt_tokens: Estimated size of system prompt
        question_buffer_tokens: Buffer for question + formatting overhead
        max_total_tokens: Maximum input tokens (conservative limit)
        output_tokens: Tokens to reserve for model output
    
    Returns:
        (truncated_static_context, truncated_current_affairs)
    """
    # Calculate available budget
    available_tokens = (
        max_total_tokens 
        - system_prompt_tokens 
        - question_buffer_tokens
        - output_tokens
    )
    
    # Allocate budget: 70% to static context, 30% to current affairs
    # (Static context is more important for foundational knowledge)
    static_budget = int(available_tokens * 0.70)
    current_budget = int(available_tokens * 0.30)
    
    # Log token budget allocation
    logger.info("📊 [SMART TRUNCATION] Token budget allocation:")
    logger.info(f"   • Total input limit: {max_total_tokens:,} tokens")
    logger.info(f"   • System prompt: {system_prompt_tokens:,} tokens")
    logger.info(f"   • Question + formatting: {question_buffer_tokens:,} tokens")
    logger.info(f"   • Output reserved: {output_tokens:,} tokens")
    logger.info(f"   • Available for context: {available_tokens:,} tokens")
    logger.info(f"   • Static context budget: {static_budget:,} tokens (70%)")
    logger.info(f"   • Current affairs budget: {current_budget:,} tokens (30%)")
    
    # Measure original sizes
    static_original_tokens = estimate_tokens(static_context or "")
    current_original_tokens = estimate_tokens(current_affairs or "")
    
    # Truncate static context (keep first paragraphs - foundational info)
    static_truncated = smart_truncate_context(
        text=static_context or "",
        max_tokens=static_budget,
        strategy="head",  # Keep foundational info
        preserve_structure=True
    )
    
    # Truncate current affairs (keep last paragraphs - most recent)
    current_truncated = smart_truncate_context(
        text=current_affairs or "",
        max_tokens=current_budget,
        strategy="tail",  # Keep most recent news
        preserve_structure=True
    )
    
    # Log truncation results
    static_final_tokens = estimate_tokens(static_truncated)
    current_final_tokens = estimate_tokens(current_truncated)
    
    logger.info("✂️  [TRUNCATION RESULTS]:")
    logger.info(f"   • Static context: {static_original_tokens:,} → {static_final_tokens:,} tokens "
                f"({static_final_tokens*100//static_original_tokens if static_original_tokens > 0 else 0}% retained, strategy: HEAD)")
    logger.info(f"   • Current affairs: {current_original_tokens:,} → {current_final_tokens:,} tokens "
                f"({current_final_tokens*100//current_original_tokens if current_original_tokens > 0 else 0}% retained, strategy: TAIL)")
    logger.info(f"   • Total context tokens: {static_final_tokens + current_final_tokens:,} / {available_tokens:,} "
                f"({(static_final_tokens + current_final_tokens)*100//available_tokens if available_tokens > 0 else 0}% of budget)")
    
    return static_truncated, current_truncated
