"""
UPSC Prelims Mock Test Validator
--------------------------------
Validates generated MCQs against UPSC design principles and schema requirements.
"""

import re
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

def validate_mock_test_question(question: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a single UPSC mock test question.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # 1. Basic Schema Check
    required_fields = ["question", "options", "correct_answer", "explanation"]
    for field in required_fields:
        if field not in question or not question[field]:
            errors.append(f"Missing or empty required field: {field}")
            
    if errors:
        return False, errors

    # 2. Options Validation
    options = question["options"]
    if not isinstance(options, list) or len(options) != 4:
        errors.append(f"Options must be a list of 4 items, found {len(options) if isinstance(options, list) else 'non-list'}")
    else:
        # Check standard format (a) text, (b) text, etc.
        for i, opt in enumerate(options):
            prefix = chr(97 + i)  # a, b, c, d
            if not str(opt).strip().lower().startswith(f"({prefix})"):
                # We can auto-correct this usually, but for validation we flag it
                errors.append(f"Option {i+1} missing standard prefix '({prefix})'")

    # 3. Correct Answer Validation
    correct_answer = str(question["correct_answer"]).upper().replace("(", "").replace(")", "").strip()
    if correct_answer not in ["A", "B", "C", "D"]:
        errors.append(f"Invalid correct_answer format: {correct_answer}. Must be A, B, C, or D.")

    # 4. Content Quality Heuristics
    question_text = question["question"]
    explanation = question["explanation"]
    
    # Question length
    if len(question_text) < 50:
        errors.append("Question text is suspiciously short (< 50 chars).")
        
    # Explanation rigor
    if len(explanation) < 100:
        errors.append("Explanation is too brief (< 100 chars). UPSC rationales should be detailed.")
        
    # Check for "Correct" and "Incorrect" mentions in explanation (indicates thoroughness)
    if "correct" not in explanation.lower() and "right" not in explanation.lower():
        errors.append("Explanation does not explicitly justify the correct option.")
    if "incorrect" not in explanation.lower() and "wrong" not in explanation.lower() and "statement" not in explanation.lower():
        # Multi-statement questions might just say "Statement 1 is..."
        pass
    
    # 5. Trap Logic Check (Heuristic)
    # UPSC distractor options are often of similar length
    if len(options) == 4:
        lengths = [len(str(o)) for o in options]
        max_len = max(lengths)
        min_len = min(lengths)
        if max_len > min_len * 4 and max_len > 100: # One option is much longer than others
            errors.append("Option length imbalance: one option is significantly longer than others (potential 'long pole' giveaway).")

    return len(errors) == 0, errors

def validate_batch(questions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate a batch of questions.
    
    Returns:
        Tuple of (valid_questions, invalid_questions_with_errors)
    """
    valid = []
    invalid = []
    
    for q in questions:
        is_valid, errors = validate_mock_test_question(q)
        if is_valid:
            valid.append(q)
        else:
            q["validation_errors"] = errors
            invalid.append(q)
            
    return valid, invalid

def calculate_quality_score(question: Dict[str, Any]) -> float:
    """
    Calculate a numerical quality score (0.0 to 1.0) for a question.
    """
    score = 1.0
    
    # Penalize for short content
    if len(question.get("question", "")) < 100: score -= 0.1
    if len(question.get("explanation", "")) < 150: score -= 0.1
    
    # Penalize for lacking specific UPSC patterns
    patterns = ["consider the following", "which of the following", "assertion", "reason", "match", "how many"]
    found_pattern = any(p in question.get("question", "").lower() for p in patterns)
    if not found_pattern:
        score -= 0.2
        
    # Check for option prefix consistency
    options = question.get("options", [])
    if options and all(str(o).strip().lower().startswith(f"({chr(97+i)})") for i, o in enumerate(options)):
        score += 0.05
        
    return max(0.0, min(1.0, score))
