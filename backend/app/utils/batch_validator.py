"""
Batch Validation and Quality Checks for Mock Test Questions
"""
import logging
from typing import List, Dict, Tuple, Any

logger = logging.getLogger(__name__)


def validate_batch(questions: List[Dict[str, Any]]) -> Tuple[List[Dict], List[str]]:
    """
    Validate a batch of questions for schema and quality
    
    Args:
        questions: List of question dictionaries from LLM
    
    Returns:
        Tuple of (valid_questions, error_messages)
    """
    valid = []
    errors = []
    
    for i, q in enumerate(questions):
        question_num = i + 1
        
        # Schema validation - required fields
        required_fields = ["question", "options", "correct_answer", "explanation"]
        missing_fields = [f for f in required_fields if f not in q]
        if missing_fields:
            errors.append(f"Q{question_num}: Missing fields {missing_fields}")
            continue
        
        # Options validation - must have exactly 4
        options = q.get("options", [])
        if not isinstance(options, list):
            errors.append(f"Q{question_num}: Options must be a list")
            continue
        
        if len(options) != 4:
            errors.append(f"Q{question_num}: Must have exactly 4 options, got {len(options)}")
            continue
        
        # Unique options check
        if len(set(options)) != 4:
            errors.append(f"Q{question_num}: Duplicate options found")
            continue
        
        # Empty options check
        if any(not opt or not str(opt).strip() for opt in options):
            errors.append(f"Q{question_num}: Empty option(s) found")
            continue
        
        # Correct answer validation
        correct_answer = q.get("correct_answer", "").strip().upper()
        if correct_answer not in ["A", "B", "C", "D"]:
            errors.append(f"Q{question_num}: Invalid correct_answer '{correct_answer}', must be A/B/C/D")
            continue
        
        # Normalize correct_answer
        q["correct_answer"] = correct_answer
        
        # Minimum length checks (quality heuristic)
        question_text = str(q.get("question", "")).strip()
        if len(question_text) < 20:
            errors.append(f"Q{question_num}: Question too short ({len(question_text)} chars)")
            continue
        
        explanation = str(q.get("explanation", "")).strip()
        if len(explanation) < 30:
            errors.append(f"Q{question_num}: Explanation too short ({len(explanation)} chars)")
            continue
        
        # UPSC style check - basic heuristics
        question_lower = question_text.lower()
        upsc_indicators = [
            "which of the following",
            "consider the following",
            "with reference to",
            "statement-i", "statement-ii",
            "assertion", "reason",
            "select the correct",
            "choose the correct",
            "arrange the following"
        ]
        
        has_upsc_style = any(indicator in question_lower for indicator in upsc_indicators)
        if not has_upsc_style and len(question_text) < 50:
            # Allow short questions if they don't look like UPSC style
            # This is a soft warning, not a hard error
            logger.debug(f"Q{question_num}: May not follow UPSC style")
        
        # All validations passed
        valid.append(q)
    
    # Log validation results
    if errors:
        logger.warning(f"⚠️ Validation: {len(valid)}/{len(questions)} questions passed ({len(errors)} errors)")
        for error in errors[:3]:  # Show first 3 errors
            logger.warning(f"   - {error}")
        if len(errors) > 3:
            logger.warning(f"   - ... and {len(errors) - 3} more errors")
    else:
        logger.info(f"✅ Validation: All {len(valid)} questions passed")
    
    return valid, errors


def calculate_quality_score(question: Dict[str, Any]) -> float:
    """
    Calculate quality score for a question (0.0 to 1.0)
    
    Scoring factors:
    - Explanation quality (40%): Length, detail
    - Question complexity (30%): Length, structure
    - Option quality (30%): Length variance, detail
    """
    score = 0.0
    
    # Factor 1: Explanation quality (40 points)
    explanation = str(question.get("explanation", ""))
    exp_len = len(explanation)
    
    # Ideal explanation: 100-300 chars
    if exp_len >= 100:
        exp_score = min(exp_len / 250, 1.0) * 40
    else:
        exp_score = (exp_len / 100) * 40  # Penalty for short explanations
    
    score += exp_score
    
    # Factor 2: Question complexity (30 points)
    question_text = str(question.get("question", ""))
    q_len = len(question_text)
    
    # Ideal question: 80-200 chars
    if 80 <= q_len <= 200:
        q_score = 30
    elif q_len < 80:
        q_score = (q_len / 80) * 30
    else:
        q_score = 30 - min((q_len - 200) / 100, 0.5) * 10  # Slight penalty for very long
    
    score += q_score
    
    # Factor 3: Option quality (30 points)
    options = question.get("options", [])
    if len(options) == 4:
        # Check option lengths
        opt_lengths = [len(str(opt)) for opt in options]
        avg_opt_len = sum(opt_lengths) / 4
        
        # Ideal average option length: 20-60 chars
        if 20 <= avg_opt_len <= 60:
            opt_score = 30
        elif avg_opt_len < 20:
            opt_score = (avg_opt_len / 20) * 30
        else:
            opt_score = 30 - min((avg_opt_len - 60) / 40, 0.5) * 10
        
        score += opt_score
    
    # Normalize to 0-1 range
    return min(score / 100, 1.0)


def score_batch(questions: List[Dict[str, Any]]) -> List[Tuple[Dict, float]]:
    """
    Score all questions in a batch
    
    Returns:
        List of (question, quality_score) tuples
    """
    scored = []
    for q in questions:
        score = calculate_quality_score(q)
        scored.append((q, score))
    
    avg_score = sum(s for _, s in scored) / len(scored) if scored else 0
    logger.info(f"📊 Batch quality: avg={avg_score:.3f}, range=[{min(s for _, s in scored):.3f}, {max(s for _, s in scored):.3f}]")
    
    return scored
