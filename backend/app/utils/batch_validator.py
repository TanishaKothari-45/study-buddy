"""
Batch Validation and Quality Checks for Mock Test Questions
"""
import logging
import math
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Any

logger = logging.getLogger(__name__)


def validate_batch(questions: List[Dict[str, Any]]) -> Tuple[List[Dict], List[str]]:
    """
    Validate a batch of questions for schema and quality with enhanced UPSC rigor
    
    Args:
        questions: List of question dictionaries from LLM
    
    Returns:
        Tuple of (valid_questions, error_messages)
    """
    valid = []
    errors = []
    
    for i, q in enumerate(questions):
        question_num = i + 1
        
        # 1. Schema validation - required fields
        required_fields = ["question", "options", "correct_answer", "explanation"]
        missing_fields = [f for f in required_fields if f not in q]
        if missing_fields:
            errors.append(f"Q{question_num}: Missing fields {missing_fields}")
            continue
        
        # 2. Options validation - must have exactly 4
        options = q.get("options", [])
        if not isinstance(options, list) or len(options) != 4:
            errors.append(f"Q{question_num}: Options must be a list of exactly 4 items")
            continue
        
        # Prefix enforcement (a, b, c, d)
        prefixes_valid = True
        for j, opt in enumerate(options):
            prefix = chr(97 + j)
            if not str(opt).strip().lower().startswith(f"({prefix})"):
                # Append the prefix if missing for better UX
                options[j] = f"({prefix}) {str(opt).strip()}"
                prefixes_valid = False
        
        if not prefixes_valid:
            logger.debug(f"Q{question_num}: Normalized option prefixes")
            
        if len(set(options)) != 4:
            errors.append(f"Q{question_num}: Duplicate options found")
            continue
        
        # 3. Correct answer validation
        correct_answer = str(q.get("correct_answer", "")).strip().upper().replace("(", "").replace(")", "")
        if correct_answer not in ["A", "B", "C", "D"]:
            errors.append(f"Q{question_num}: Invalid correct_answer '{correct_answer}', must be A/B/C/D")
            continue
        q["correct_answer"] = correct_answer
        
        # 4. Length and Rigor Heuristics
        question_text = str(q.get("question", "")).strip()
        explanation = str(q.get("explanation", "")).strip()
        
        if len(question_text) < 50:
            errors.append(f"Q{question_num}: Question too short (< 50 chars)")
            continue

        # All validations passed
        valid.append(q)
    
    # Log validation results
    if errors:
        logger.warning(f"⚠️ Validation: {len(valid)}/{len(questions)} passed ({len(errors)} errors)")
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


def partition_with_diversity(
    chunks: List[Dict],
    batch_size: int = 10,
    max_per_subdomain: int = 3,
) -> List[Dict]:
    """
    Build a single batch by round-robin across sub-domains, capping each at
    *max_per_subdomain* so no single sub-domain dominates the generation context.
    Chunks that are consumed are popped from *subdomain_buckets* in-place so the
    caller can feed the remainder into subsequent batches.
    """
    subdomain_buckets: Dict[str, List[Dict]] = defaultdict(list)
    for chunk in chunks:
        sd = chunk.get("metadata", {}).get("sub_domain", "Unknown")
        subdomain_buckets[sd].append(chunk)

    batch: List[Dict] = []
    subdomain_counts: Dict[str, int] = defaultdict(int)

    while len(batch) < batch_size:
        added = False
        for sd in list(subdomain_buckets.keys()):
            sd_chunks = subdomain_buckets[sd]
            if subdomain_counts[sd] < max_per_subdomain and sd_chunks:
                batch.append(sd_chunks.pop(0))
                subdomain_counts[sd] += 1
                added = True
                if len(batch) >= batch_size:
                    break
        if not added:
            break

    return batch


def partition_all_batches(
    all_chunks: List[Dict],
    num_batches: int,
    batch_size: int = 10,
    max_per_subdomain: int = 3,
) -> List[List[Dict]]:
    """
    Partition *all_chunks* into *num_batches* lists, each with sub-domain
    diversity enforced.  Remaining chunks after all capped rounds are
    distributed evenly so nothing is wasted.
    """
    pool = list(all_chunks)
    batches: List[List[Dict]] = []

    for _ in range(num_batches):
        batch = partition_with_diversity(pool, batch_size, max_per_subdomain)
        used_ids = {id(c) for c in batch}
        pool = [c for c in pool if id(c) not in used_ids]
        batches.append(batch)

    if pool:
        for i, chunk in enumerate(pool):
            batches[i % num_batches].append(chunk)

    sd_summary = {}
    for idx, b in enumerate(batches):
        dist = defaultdict(int)
        for c in b:
            dist[c.get("metadata", {}).get("sub_domain", "Unknown")] += 1
        sd_summary[idx] = dict(dist)
    logger.info(f"📊 Batch diversity distribution: {sd_summary}")

    return batches


def subdomain_entropy_score(questions: List[Dict[str, Any]]) -> float:
    """
    Normalized Shannon entropy (0-1) over sub-domain labels in a question set.
    1.0 = perfectly uniform distribution; 0.0 = all questions from one sub-domain.
    """
    subdomains = [
        q.get("source", {}).get("sub_domain", "Unknown") for q in questions
    ]
    counts = Counter(subdomains)
    n = len(subdomains)
    if n == 0:
        return 0.0

    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
    return entropy / max_entropy if max_entropy > 0 else 0.0


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
