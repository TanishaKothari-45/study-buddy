"""
Answer Evaluation Module
Evaluates UPSC handwritten answers using reconstructed text (not OCR blocks)
Handles: Evaluation only (question and answer already provided)
"""
import logging
import json
import os
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# System prompt for reconstruction + evaluation (all 3 tasks in ONE call)
RECONSTRUCT_AND_EVALUATE_SYSTEM_PROMPT = """You are an expert UPSC Mains evaluator AND faithful transcriber. You will receive OCR blocks from a handwritten UPSC answer.

INPUT: You will receive OCR blocks (each block has text + bounding box). The UPSC question itself is ALSO inside these blocks – identify it.

TASK 1 — IDENTIFY QUESTION
• detect which block(s) contain the question
• extract that question text

TASK 2 — RECONSTRUCT STUDENT ANSWER
• reconstruct only the student's written answer (not your own answer)
• use ONLY OCR text
• you MAY fill small missing fragments ONLY if DIRECTLY implied by partial line continuation (no external facts)
• if comparison / flowchart / table is visually implied → insert placeholder:
  [diagram: <short descriptor>]
• if something is unclear → mark as "[unclear]"

TASK 3 — EVALUATE THE ANSWER

Your job is NOT to judge structure, NOT to check IBC format mechanically.

Your job is to evaluate the answer based on:
– how well the student addressed ALL major parts of the question
– topic coverage completeness (especially when question asks multi-part)
– depth of explanation
– relevance + conceptual correctness
– use of examples and evidence
– clarity of argument
– linkages + insight (inter-topic / human dimensions / geography intersections)

SCORE:
Give ONE score out of 20. 
(20 = near topper level, 15–17 = solid, 10–14 = average, <10 weak)

OUTPUT FORMAT (MANDATORY EXACT):

### QUESTION
<identified question text>

### RECONSTRUCTED ANSWER
<clean reconstructed answer>

### SCORE (out of 20)
x/20

### WHAT WAS DONE WELL
• 3–6 bullets of strengths in THIS answer (not generic)

### WHAT WAS MISSING / CAN BE IMPROVED
• MUST be concrete: mention 3–6 SPECIFIC content gaps that this answer SHOULD have included but did not
• reference exact missing items in THIS topic (e.g. “no mention of El Niño anomaly”, “no India wildfire example”, “water security part did not mention groundwater recharge reduction”)
• NO generic remarks like “improve clarity” or “expand examples” — must say exactly WHAT example / line / concept is missing

### HIGH RETURN IMPROVEMENTS
Each improvement bullet MUST state WHAT to insert AND WHERE in the answer to insert it.
Format like:
• After the drought line: insert [diagram: drought→fuel dryness→ignition→crop loss]
• After global wildfire stats: add India example (e.g. Uttarakhand 2024)
• In the last 2 lines before conclusion: insert 1 SDG linkage (SDG-2 + SDG-6)
• After listing food implications: add 1 explicit water implication (groundwater recharge reduction)

RULES:
• Do not rewrite the answer.
• Do not generate ideal answer.
• Do not hallucinate facts.
• Improvements MUST be based on missing parts in THIS answer only.


"""

# System prompt for evaluation (reconstructed answer only - no OCR blocks) - DEPRECATED
EVALUATION_SYSTEM_PROMPT = """You are an expert UPSC Mains evaluator in mentor-mode. You will receive a reconstructed handwritten UPSC answer.

INPUT: You will receive:
- The question (if provided, otherwise identify it from the answer)
- The reconstructed student's answer (already transcribed from OCR)

TASK 1 — IDENTIFY QUESTION (if not provided)
• If question is not provided, identify it from the reconstructed answer
• Look for question markers, directive words (discuss, analyze, examine, etc.)
• Extract the complete question text

TASK 2 — EVALUATE THE ANSWER

Your job is NOT to judge structure, NOT to check IBC format mechanically.

Your job is to evaluate the answer based on:
– how well the student addressed ALL major parts of the question
– topic coverage completeness (especially when question asks multi-part)
– depth of explanation
– relevance + conceptual correctness
– use of examples and evidence
– clarity of argument
– linkages + insight (inter-topic / human dimensions / geography intersections)

SCORE:
Give ONE score out of 20. 
(20 = near topper level, 15–17 = solid, 10–14 = average, <10 weak)

OUTPUT FORMAT (MANDATORY EXACT):

### QUESTION
<identified question text>

### RECONSTRUCTED ANSWER
<clean reconstructed answer>

### SCORE (out of 20)
x/20

### WHAT WAS DONE WELL
• 3–6 bullets of strengths in THIS answer (not generic)

### WHAT WAS MISSING / CAN BE IMPROVED
• MUST be concrete: mention 3–6 SPECIFIC content gaps that this answer SHOULD have included but did not
• reference exact missing items in THIS topic (e.g. “no mention of El Niño anomaly”, “no India wildfire example”, “water security part did not mention groundwater recharge reduction”)
• NO generic remarks like “improve clarity” or “expand examples” — must say exactly WHAT example / line / concept is missing

### HIGH RETURN IMPROVEMENTS
Each improvement bullet MUST state WHAT to insert AND WHERE in the answer to insert it.
Format like:
• After the drought line: insert [diagram: drought→fuel dryness→ignition→crop loss]
• After global wildfire stats: add India example (e.g. Uttarakhand 2024)
• In the last 2 lines before conclusion: insert 1 SDG linkage (SDG-2 + SDG-6)
• After listing food implications: add 1 explicit water implication (groundwater recharge reduction)

RULES:
• Do not rewrite the answer.
• Do not generate ideal answer.
• Do not hallucinate facts.
• Improvements MUST be based on missing parts in THIS answer only.

"""

# System prompt for reconstruction only (Task 1 & 2, no evaluation)
RECONSTRUCTION_ONLY_SYSTEM_PROMPT = """You are a faithful transcriber. Your task is to identify the question and reconstruct the student's handwritten answer.

INPUT you receive will be OCR blocks (each block has text + bounding box). The UPSC question itself is ALSO inside these blocks – identify it.

TASK 1 — IDENTIFY QUESTION

• detect which block(s) contain the question

• extract that question text

TASK 2 — RECONSTRUCT STUDENT ANSWER

• reconstruct only the student's written answer (not your own answer)

• use ONLY OCR text

• you MAY fill small missing fragments ONLY if DIRECTLY implied by partial line continuation (no external facts)

• if comparison / flowchart / table is visually implied → insert placeholder:
  [diagram: <short descriptor>]

• if something is unclear → mark as "[unclear]"

Do NOT evaluate. Do NOT score. Only identify question and reconstruct answer.

OUTPUT FORMAT (MANDATORY):

### QUESTION

<detected question text>

### RECONSTRUCTED ANSWER

<clean reconstructed answer>"""


def evaluate_reconstructed_answer(
    question: Optional[str],
    reconstructed_answer: str,
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Evaluate a reconstructed answer (question optional - will be identified if not provided, no OCR blocks)
    
    Args:
        question: The question (optional - will be identified from answer if not provided)
        reconstructed_answer: The reconstructed answer (already transcribed from OCR)
        llm_client: OpenAI client instance
        model: LLM model to use
        max_retries: Maximum retry attempts
    
    Returns:
        Dictionary with evaluation results:
            {
                "question": identified_question,
                "reconstructed_answer": reconstructed_answer,
                "evaluation": {
                    "score": x,
                    "max_score": 20,
                    "what_was_done_well": ["...", "..."],
                    "what_was_missing": ["...", "..."],
                    "high_return_improvements": ["...", "..."]
                },
                "raw_response": "..."  # Exact LLM response
            }
    """
    if not reconstructed_answer:
        logger.warning("⚠️ Reconstructed answer missing")
        return {
            "question": question or "",
            "reconstructed_answer": "",
            "error": "Reconstructed answer missing"
        }
    
    logger.info(f"   📤 Sending reconstructed answer to LLM for evaluation:")
    if question:
        logger.info(f"      • Question provided: {question[:100]}...")
    else:
        logger.info(f"      • Question not provided - will be identified from answer")
    logger.info(f"      • Answer length: {len(reconstructed_answer)} chars")
    
    # Build user message - include question if provided, otherwise ask LLM to identify it
    if question:
        user_message = f"""Question:
{question}

Reconstructed Student Answer:
{reconstructed_answer}

Evaluate this answer based on UPSC Mains criteria. Return ONLY the evaluation in the exact format specified."""
    else:
        user_message = f"""Reconstructed Student Answer:
{reconstructed_answer}

First, identify the question from the answer (look for question markers, directive words like "discuss", "analyze", "examine", etc.).
Then evaluate this answer based on UPSC Mains criteria. Return ONLY the evaluation in the exact format specified (including the identified question)."""
    
    for attempt in range(max_retries):
        try:
            logger.info(f"   🤖 Sending to LLM for evaluation (attempt {attempt + 1}/{max_retries})...")
            
            completion = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,  # Maximum accuracy
                top_p=0,  # Deterministic output
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            
            if response_text:
                logger.info(f"   ✅ LLM evaluation complete - output length: {len(response_text)} chars")
                
                # Parse the response
                parsed_result = parse_evaluation_response_simple(response_text)
                # Extract identified question from response if not provided
                identified_question = parsed_result.get("question", question or "")
                parsed_result["question"] = identified_question
                parsed_result["reconstructed_answer"] = reconstructed_answer
                parsed_result["raw_response"] = response_text  # Include exact response
                return parsed_result
            else:
                raise ValueError("Empty response from LLM")
                
        except Exception as e:
            logger.error(f"   ❌ LLM evaluation failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"   ⏳ Retrying...")
                continue
            else:
                logger.error(f"   ❌ All evaluation attempts failed")
                return {
                    "question": question or "",
                    "reconstructed_answer": reconstructed_answer,
                    "error": str(e),
                    "raw_response": ""
                }
    
    return {
        "question": question or "",
        "reconstructed_answer": reconstructed_answer,
        "error": "All attempts failed",
        "raw_response": ""
    }


def parse_evaluation_response_simple(response_text: str) -> Dict[str, Any]:
    """
    Parse simple evaluation response (question, score, what was done well, what was missing, improvements)
    
    Args:
        response_text: Raw LLM response
    
    Returns:
        Parsed evaluation dictionary
    """
    import re
    
    result = {
        "question": "",
        "evaluation": {
            "score": 0,
            "max_score": 20,
            "what_was_done_well": [],
            "what_was_missing": [],
            "high_return_improvements": []
        }
    }
    
    try:
        # Extract question (if identified in response)
        question_match = re.search(r'### QUESTION\s*\n(.*?)(?=### SCORE|$)', response_text, re.DOTALL)
        if question_match:
            result["question"] = question_match.group(1).strip()
        
        # Extract score
        score_match = re.search(r'### SCORE.*?\n(\d+)/20', response_text, re.IGNORECASE | re.DOTALL)
        if score_match:
            result["evaluation"]["score"] = int(score_match.group(1))
        
        # Extract "WHAT WAS DONE WELL"
        done_well_match = re.search(r'### WHAT WAS DONE WELL\s*\n(.*?)(?=### WHAT WAS MISSING|### HIGH RETURN|$)', response_text, re.IGNORECASE | re.DOTALL)
        if done_well_match:
            done_well_text = done_well_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', done_well_text, re.MULTILINE)
            result["evaluation"]["what_was_done_well"] = [b.strip() for b in bullets if b.strip()]
        
        # Extract "WHAT WAS MISSING / CAN BE IMPROVED"
        missing_match = re.search(r'### WHAT WAS MISSING.*?\n(.*?)(?=### HIGH RETURN|$)', response_text, re.IGNORECASE | re.DOTALL)
        if missing_match:
            missing_text = missing_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', missing_text, re.MULTILINE)
            result["evaluation"]["what_was_missing"] = [b.strip() for b in bullets if b.strip()]
        
        # Extract "HIGH RETURN IMPROVEMENTS"
        improvements_match = re.search(r'### HIGH RETURN IMPROVEMENTS\s*\n(.*?)$', response_text, re.IGNORECASE | re.DOTALL)
        if improvements_match:
            improvements_text = improvements_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', improvements_text, re.MULTILINE)
            result["evaluation"]["high_return_improvements"] = [b.strip() for b in bullets if b.strip()]
        
    except Exception as e:
        logger.error(f"   ⚠️ Failed to parse evaluation response: {e}")
        result["raw_response"] = response_text
    
    return result


def parse_reconstruct_and_evaluate_response(response_text: str) -> Dict[str, Any]:
    """
    Parse LLM response that contains both reconstruction and evaluation (all 3 tasks in one call)
    
    Args:
        response_text: Raw LLM response
    
    Returns:
        Parsed dictionary with question, reconstructed_answer, and evaluation
    """
    import re
    
    result = {
        "question": "",
        "reconstructed_answer": "",
        "evaluation": {
            "score": 0,
            "max_score": 20,
            "what_was_done_well": [],
            "what_was_missing": [],
            "high_return_improvements": []
        }
    }
    
    try:
        # Extract question
        question_match = re.search(r'### QUESTION\s*\n(.*?)(?=### RECONSTRUCTED ANSWER|$)', response_text, re.DOTALL)
        if question_match:
            result["question"] = question_match.group(1).strip()
        
        # Extract reconstructed answer
        answer_match = re.search(r'### RECONSTRUCTED ANSWER\s*\n(.*?)(?=### SCORE|$)', response_text, re.DOTALL)
        if answer_match:
            result["reconstructed_answer"] = answer_match.group(1).strip()
        
        # Extract score
        score_match = re.search(r'### SCORE.*?\n(\d+)/20', response_text, re.IGNORECASE | re.DOTALL)
        if score_match:
            result["evaluation"]["score"] = int(score_match.group(1))
        
        # Extract "WHAT WAS DONE WELL"
        done_well_match = re.search(r'### WHAT WAS DONE WELL\s*\n(.*?)(?=### WHAT WAS MISSING|### HIGH RETURN|$)', response_text, re.IGNORECASE | re.DOTALL)
        if done_well_match:
            done_well_text = done_well_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', done_well_text, re.MULTILINE)
            result["evaluation"]["what_was_done_well"] = [b.strip() for b in bullets if b.strip()]
        
        # Extract "WHAT WAS MISSING / CAN BE IMPROVED"
        missing_match = re.search(r'### WHAT WAS MISSING.*?\n(.*?)(?=### HIGH RETURN|$)', response_text, re.IGNORECASE | re.DOTALL)
        if missing_match:
            missing_text = missing_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', missing_text, re.MULTILINE)
            result["evaluation"]["what_was_missing"] = [b.strip() for b in bullets if b.strip()]
        
        # Extract "HIGH RETURN IMPROVEMENTS"
        improvements_match = re.search(r'### HIGH RETURN IMPROVEMENTS\s*\n(.*?)$', response_text, re.IGNORECASE | re.DOTALL)
        if improvements_match:
            improvements_text = improvements_match.group(1)
            # Extract bullet points
            bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', improvements_text, re.MULTILINE)
            result["evaluation"]["high_return_improvements"] = [b.strip() for b in bullets if b.strip()]
        
    except Exception as e:
        logger.error(f"   ⚠️ Failed to parse reconstruction + evaluation response: {e}")
        logger.debug(f"   Response text: {response_text[:500]}...")
        result["raw_response"] = response_text
    
    return result


def reconstruct_and_evaluate_from_ocr_blocks(
    ocr_data: Dict[str, Any],
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Reconstruct AND evaluate in ONE LLM call from OCR blocks (all 3 tasks: identify question, reconstruct, evaluate)
    
    This is the preferred method for evaluation - does everything in one call.
    
    Args:
        ocr_data: Dictionary with OCR data:
            {
                "blocks": [
                    {"text": "...", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "conf": 0.93},
                    ...
                ],
                "full_text": "...raw text...",
                "width": W,
                "height": H
            }
        llm_client: OpenAI client instance
        model: LLM model to use
        max_retries: Maximum retry attempts
    
    Returns:
        Dictionary with evaluation results:
            {
                "question": "...",
                "reconstructed_answer": "...",
                "evaluation": {
                    "score": x,
                    "max_score": 20,
                    "what_was_done_well": ["...", "..."],
                    "what_was_missing": ["...", "..."],
                    "high_return_improvements": ["...", "..."]
                },
                "raw_response": "..."  # Exact LLM response
            }
    """
    blocks = ocr_data.get("blocks", [])
    full_text = ocr_data.get("full_text", "")
    width = ocr_data.get("width", 0)
    height = ocr_data.get("height", 0)
    
    if not blocks and not full_text:
        logger.warning("⚠️ No blocks or full_text provided")
        return {
            "question": "",
            "reconstructed_answer": "",
            "error": "No OCR data provided"
        }
    
    # Format OCR data as JSON for LLM
    ocr_json = json.dumps(ocr_data, ensure_ascii=False, indent=2)
    
    logger.info(f"   📤 Sending OCR blocks to LLM for reconstruction + evaluation (ONE call):")
    logger.info(f"      • Blocks: {len(blocks)}")
    logger.info(f"      • Full text length: {len(full_text)} chars")
    logger.info(f"      • Image dimensions: {width}x{height} pixels")
    
    user_message = f"""Process the following OCR blocks to:
1. Identify the question
2. Reconstruct the student's answer
3. Evaluate the answer

OCR Data:
{ocr_json}

Remember:
- Identify which blocks contain the question
- Reconstruct ONLY the student's answer (not your own)
- Use only OCR text
- Evaluate strictly based on UPSC Mains criteria
- Follow the output format exactly"""
    
    for attempt in range(max_retries):
        try:
            logger.info(f"   🤖 Sending OCR blocks to LLM for reconstruction + evaluation (attempt {attempt + 1}/{max_retries})...")
            
            completion = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": RECONSTRUCT_AND_EVALUATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,  # Maximum accuracy
                top_p=0,  # Deterministic output
                max_tokens=3000  # More tokens for reconstruction + evaluation
            )
            
            response_text = completion.choices[0].message.content
            
            if response_text:
                logger.info(f"   ✅ LLM reconstruction + evaluation complete - output length: {len(response_text)} chars")
                
                # Parse the response
                parsed_result = parse_reconstruct_and_evaluate_response(response_text)
                parsed_result["raw_response"] = response_text  # Include exact response
                return parsed_result
            else:
                raise ValueError("Empty response from LLM")
                
        except Exception as e:
            logger.error(f"   ❌ LLM reconstruction + evaluation failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"   ⏳ Retrying...")
                continue
            else:
                logger.error(f"   ❌ All attempts failed")
                return {
                    "question": "",
                    "reconstructed_answer": full_text if full_text else "\n".join([b["text"] for b in blocks]),
                    "error": str(e),
                    "raw_response": ""
                }
    
    return {
        "question": "",
        "reconstructed_answer": "",
        "error": "All attempts failed",
        "raw_response": ""
    }


def evaluate_from_ocr_blocks(
    ocr_data: Dict[str, Any],
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    DEPRECATED: Alias for reconstruct_and_evaluate_from_ocr_blocks
    Kept for backward compatibility.
    """
    return reconstruct_and_evaluate_from_ocr_blocks(ocr_data, llm_client, model, max_retries)


def reconstruct_with_question_identification(
    ocr_data: Dict[str, Any],
    llm_client: OpenAI,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Reconstruct answer and identify question from OCR blocks (Task 1 & 2 only, no evaluation)
    
    Args:
        ocr_data: Dictionary with OCR data
        llm_client: OpenAI client instance
        model: LLM model to use
        max_retries: Maximum retry attempts
    
    Returns:
        Dictionary with:
            {
                "question": "...",
                "reconstructed_answer": "..."
            }
    """
    blocks = ocr_data.get("blocks", [])
    full_text = ocr_data.get("full_text", "")
    width = ocr_data.get("width", 0)
    height = ocr_data.get("height", 0)
    
    if not blocks and not full_text:
        logger.warning("⚠️ No blocks or full_text provided for reconstruction")
        return {
            "question": "",
            "reconstructed_answer": ""
        }
    
    # Format OCR data as JSON for LLM
    ocr_json = json.dumps(ocr_data, ensure_ascii=False, indent=2)
    
    logger.info(f"   📤 Sending OCR data to LLM for reconstruction (with question identification):")
    logger.info(f"      • Blocks: {len(blocks)}")
    logger.info(f"      • Full text length: {len(full_text)} chars")
    
    user_message = f"""Process the following OCR blocks to:
1. Identify the question
2. Reconstruct the student's answer

OCR Data:
{ocr_json}

Remember:
- Identify which blocks contain the question
- Reconstruct ONLY the student's answer (not your own)
- Use only OCR text
- Follow the output format exactly"""
    
    for attempt in range(max_retries):
        try:
            logger.info(f"   🤖 Sending OCR data to LLM (attempt {attempt + 1}/{max_retries})...")
            
            completion = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": RECONSTRUCTION_ONLY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,  # Maximum accuracy
                top_p=0,  # Deterministic output
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            
            if response_text:
                logger.info(f"   ✅ LLM reconstruction complete - output length: {len(response_text)} chars")
                
                # Parse the response
                parsed_result = parse_reconstruction_response(response_text)
                return parsed_result
            else:
                raise ValueError("Empty response from LLM")
                
        except Exception as e:
            logger.error(f"   ❌ LLM reconstruction failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"   ⏳ Retrying...")
                continue
            else:
                logger.error(f"   ❌ All reconstruction attempts failed")
                # Fallback: use full_text
                return {
                    "question": "",
                    "reconstructed_answer": full_text if full_text else "\n".join([b["text"] for b in blocks])
                }
    
    return {
        "question": "",
        "reconstructed_answer": ""
    }


def parse_evaluation_response(response_text: str) -> Dict[str, Any]:
    """
    Parse LLM evaluation response into structured format (DEPRECATED - old format)
    
    Args:
        response_text: Raw LLM response
    
    Returns:
        Parsed evaluation dictionary
    """
    import re
    
    result = {
        "question": "",
        "reconstructed_answer": "",
        "evaluation": {
            "intro": {"score": 0, "max": 3, "justification": ""},
            "directive": {"score": 0, "max": 1, "justification": ""},
            "ibc": {"score": 0, "max": 2, "justification": ""},
            "multidimensionality": {"score": 0, "max": 6, "justification": ""},
            "examples": {"score": 0, "max": 3, "justification": ""},  # Assuming x/3 (32 seems like typo)
            "diagram": {"score": 0, "max": 2, "justification": ""},  # Assuming x/2 (10 seems inconsistent)
            "conclusion": {"score": 0, "max": 3, "justification": ""},
            "overall_score": 0,
            "max_score": 20
        },
        "improvements": []
    }
    
    try:
        # Extract question
        question_match = re.search(r'### QUESTION\s*\n(.*?)(?=### RECONSTRUCTED ANSWER|### EVALUATION|$)', response_text, re.DOTALL)
        if question_match:
            result["question"] = question_match.group(1).strip()
        
        # Extract reconstructed answer
        answer_match = re.search(r'### RECONSTRUCTED ANSWER\s*\n(.*?)(?=### EVALUATION|$)', response_text, re.DOTALL)
        if answer_match:
            result["reconstructed_answer"] = answer_match.group(1).strip()
        
        # Extract evaluation scores
        eval_section = re.search(r'### EVALUATION\s*\n(.*?)(?=### IMPROVEMENTS|$)', response_text, re.DOTALL)
        if eval_section:
            eval_text = eval_section.group(1)
            
            # Parse each score (updated to match new scoring system)
            patterns = {
                "intro": r'Intro:\s*(\d+(?:\.\d+)?)/3\s*–\s*(.*?)(?=\n|$)',
                "directive": r'Directive:\s*(\d+(?:\.\d+)?)/1\s*–\s*(.*?)(?=\n|$)',
                "ibc": r'IBC:\s*(\d+(?:\.\d+)?)/2\s*–\s*(.*?)(?=\n|$)',
                "multidimensionality": r'Multidimensionality:\s*(\d+(?:\.\d+)?)/6\s*–\s*(.*?)(?=\n|$)',
                "examples": r'Examples.*?:\s*(\d+(?:\.\d+)?)/(?:3|32)\s*–\s*(.*?)(?=\n|$)',  # Handle both 3 and 32 (typo)
                "diagram": r'Inline Diagram:\s*(\d+(?:\.\d+)?)/(?:2|10)\s*–\s*(.*?)(?=\n|$)',  # Handle both 2 and 10
                "conclusion": r'Conclusion:\s*(\d+(?:\.\d+)?)/3\s*–\s*(.*?)(?=\n|$)',
            }
            
            max_scores = {
                "intro": 3,
                "directive": 1,
                "ibc": 2,
                "multidimensionality": 6,
                "examples": 3,  # Default to 3, but will extract actual max from pattern
                "diagram": 2,  # Default to 2, but will extract actual max from pattern
                "conclusion": 3
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, eval_text, re.IGNORECASE | re.DOTALL)
                if match:
                    score = float(match.group(1))
                    justification = match.group(2).strip()
                    # Extract max score from the match if possible, otherwise use default
                    max_score = max_scores.get(key, 3)
                    # Try to extract the actual max from the matched text
                    max_match = re.search(r'/(\d+)', match.group(0))
                    if max_match:
                        max_score = int(max_match.group(1))
                        # Fix obvious typos
                        if key == "examples" and max_score == 32:
                            max_score = 3
                        elif key == "diagram" and max_score == 10:
                            max_score = 2
                    
                    result["evaluation"][key] = {
                        "score": score,
                        "max": max_score,
                        "justification": justification
                    }
            
            # Extract overall score (out of 20)
            overall_match = re.search(r'Overall Score:\s*(\d+(?:\.\d+)?)/20', eval_text, re.IGNORECASE)
            if overall_match:
                result["evaluation"]["overall_score"] = float(overall_match.group(1))
        
        # Extract improvements
        improvements_match = re.search(r'### IMPROVEMENTS\s*\n(.*?)$', response_text, re.DOTALL)
        if improvements_match:
            improvements_text = improvements_match.group(1)
            # Extract bullet points
            improvements = re.findall(r'[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n\n|$)', improvements_text, re.MULTILINE)
            result["improvements"] = [imp.strip() for imp in improvements if imp.strip()]
        
    except Exception as e:
        logger.error(f"   ⚠️ Failed to parse evaluation response: {e}")
        logger.debug(f"   Response text: {response_text[:500]}...")
        # Return raw response if parsing fails
        result["raw_response"] = response_text
    
    return result


def parse_reconstruction_response(response_text: str) -> Dict[str, Any]:
    """
    Parse LLM reconstruction response (question + answer only)
    
    Args:
        response_text: Raw LLM response
    
    Returns:
        Dictionary with question and reconstructed_answer
    """
    import re
    
    result = {
        "question": "",
        "reconstructed_answer": ""
    }
    
    try:
        # Extract question
        question_match = re.search(r'### QUESTION\s*\n(.*?)(?=### RECONSTRUCTED ANSWER|$)', response_text, re.DOTALL)
        if question_match:
            result["question"] = question_match.group(1).strip()
        
        # Extract reconstructed answer
        answer_match = re.search(r'### RECONSTRUCTED ANSWER\s*\n(.*?)$', response_text, re.DOTALL)
        if answer_match:
            result["reconstructed_answer"] = answer_match.group(1).strip()
        
    except Exception as e:
        logger.error(f"   ⚠️ Failed to parse reconstruction response: {e}")
        result["raw_response"] = response_text
    
    return result
