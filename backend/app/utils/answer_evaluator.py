# answer_evaluator.py
"""
Answer evaluator pipeline
- Edit student's answer in-place (preserve voice; add up to 3 facts from provided context only)
- Produce a final UPSC IBC-formatted mains answer using the edited answer + context
- Uses mains_prompt.assemble_mains_prompt when available
- Simple CLI included for testing

Usage:
    from answer_evaluator import evaluate_and_improve
    out = evaluate_and_improve(question, student_answer, static_context, current_bullets, word_count=350)
    print(out["edited_answer"])
    print(out["final_answer"])
"""

from typing import Optional, Dict, Any
import os
import logging
import sys

# OpenAI client
try:
    import openai
except Exception:
    openai = None

# Try to import the mains prompt assembler (your mains_prompt.py)
try:
    from mains_prompt import assemble_mains_prompt
except Exception:
    assemble_mains_prompt = None

# Logging
logger = logging.getLogger("answer_evaluator")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# -------------------------
# OpenAI wrapper
# -------------------------
def _ensure_openai_api():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment.")
    if openai is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    openai.api_key = api_key


def call_llm(system: str, user: str, model: str = "gpt-4o-mini",
             max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """
    Minimal chat wrapper. Returns assistant content string.
    """
    _ensure_openai_api()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            n=1
        )
        # Compatibility: older/newer responses
        choice = resp.choices[0]
        # Some SDKs use 'message' vs 'text'
        text = ""
        if hasattr(choice, "message") and isinstance(choice.message, dict):
            text = choice.message.get("content", "") or ""
        elif hasattr(choice, "message") and hasattr(choice.message, "content"):
            text = getattr(choice.message, "content", "") or ""
        else:
            text = choice.get("text", "") or choice.get("message", {}).get("content", "")
        return text.strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        raise


# -------------------------
# Prompts
# -------------------------
EDITOR_SYSTEM = """You are an expert UPSC Mains answer editor (Geography).
Edit and IMPROVE the student's answer — preserve their voice and original points.
Rules:
- Preserve student's voice; EDIT (rephrase, reorganize, tidy) rather than rewrite from scratch.
- Output must be in strict IBC format: Introduction (2-3 lines) → Body (sub-headings + bullets ≤ 18 words) → Conclusion (1 paragraph).
- Do NOT invent facts. You may add up to 3 missing, high-value facts/examples ONLY if they appear in STATIC CONTEXT or CURRENT BULLETS; annotate such additions as (source).
- If no supporting fact exists and you feel a fact is necessary, insert "[citation needed]" instead of inventing it.
- Insert at least one inline diagram suggestion where relevant: e.g., (Suggested Diagram: India map showing X).
- Keep length near TARGET_WORD_COUNT. If student's answer is much shorter, expand concisely using provided context; if longer, compress while preserving intent.
- Return only the edited/improved answer text (no JSON, no commentary).
"""

EDITOR_USER_TEMPLATE = """QUESTION:
{question}

STUDENT ANSWER:
---
{student_answer}
---

STATIC CONTEXT (use for substantiation; do not invent outside it):
{static_context}

CURRENT BULLETS (use if relevant):
{current_bullets}

TARGET_WORD_COUNT: approx {word_count} words.

Instructions: Edit the student's answer in place following the system rules. Preserve voice, add up to 3 facts from the STATIC/CURRENT contexts only (annotate sources), include at least one inline diagram suggestion, and output ONLY the improved answer text.
"""


FINAL_SYSTEM_FALLBACK = """You are a senior UPSC Mains answer writer (Geography). Produce a high-quality IBC-format answer.
Use the edited student answer as the base and the provided static/current contexts for substantiation.
Do NOT invent facts beyond the supplied contexts; mark any unverifiable claims as [citation needed].
Include at least one inline diagram suggestion.
Return only the final answer text (no metadata)."""

FINAL_USER_FALLBACK = """TASK:
Produce the final UPSC Mains IBC answer.

QUESTION:
{question}

EDITED STUDENT ANSWER (base for final):
{edited_answer}

STATIC CONTEXT:
{static_context}

CURRENT BULLETS:
{current_bullets}

Target words: ~{word_count}. Strict IBC format. Substantiate points using STATIC/CURRENT only. Output only the answer text.
"""


# -------------------------
# Core functions
# -------------------------
def edit_student_answer(question: str,
                        student_answer: str,
                        static_context: Optional[str] = None,
                        current_bullets: Optional[str] = None,
                        word_count: int = 350,
                        model: str = "gpt-4o-mini") -> str:
    """
    Edit/improve student's answer in place using the editor prompt.
    """
    static_context = static_context or "NONE"
    current_bullets = current_bullets or "NONE"
    user_msg = EDITOR_USER_TEMPLATE.format(
        question=question,
        student_answer=student_answer,
        static_context=static_context,
        current_bullets=current_bullets,
        word_count=word_count
    )
    logger.info("Calling LLM to edit student answer (deterministic)...")
    edited = call_llm(EDITOR_SYSTEM, user_msg, model=model, max_tokens=900, temperature=0.0)
    logger.info("Received edited answer.")
    return edited.strip()


def produce_final_mains_answer(question: str,
                               edited_answer: str,
                               static_context: Optional[str] = None,
                               current_bullets: Optional[str] = None,
                               word_count: int = 350,
                               model: str = "gpt-4o-mini") -> str:
    """
    Produce the final mains answer. Prefer using mains_prompt.assemble_mains_prompt if available.
    """
    static_context = static_context or ""
    current_bullets = current_bullets or ""

    if assemble_mains_prompt:
        # Build system + user using provided assembler
        try:
            assembled = assemble_mains_prompt(
                question=question,
                context=edited_answer + "\n\n" + static_context,
                current_bullets=current_bullets,
                word_count=word_count
            )
            system_prompt = assembled.get("system") or FINAL_SYSTEM_FALLBACK
            user_prompt = assembled.get("user") or FINAL_USER_FALLBACK.format(
                question=question,
                edited_answer=edited_answer,
                static_context=static_context,
                current_bullets=current_bullets,
                word_count=word_count
            )
            logger.info("Using mains_prompt.assemble_mains_prompt for final generation.")
            final = call_llm(system_prompt, user_prompt, model=model, max_tokens=1100, temperature=0.2)
            return final.strip()
        except Exception as e:
            logger.warning(f"assemble_mains_prompt failed: {e}; falling back to internal prompt.")
            # fall through to fallback
    # Fallback
    user_msg = FINAL_USER_FALLBACK.format(
        question=question,
        edited_answer=edited_answer,
        static_context=static_context,
        current_bullets=current_bullets,
        word_count=word_count
    )
    logger.info("Using fallback final prompt for LLM generation.")
    final = call_llm(FINAL_SYSTEM_FALLBACK, user_msg, model=model, max_tokens=1100, temperature=0.2)
    logger.info("Received final mains answer.")
    return final.strip()


def reconstruct_with_question_identification(
    ocr_data: Dict[str, Any],
    llm_client=None,
    model: str = "gpt-4o-mini"
) -> Dict[str, str]:
    """
    Reconstruct student answer from OCR data and identify the question.
    
    Args:
        ocr_data: Dictionary with OCR data (blocks, full_text, width, height)
        llm_client: OpenAI client instance (optional, will create if not provided)
        model: LLM model to use
    
    Returns:
        Dict with 'question' and 'reconstructed_answer'
    """
    import json
    from openai import OpenAI
    
    if llm_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment.")
        llm_client = OpenAI(api_key=api_key)
    
    blocks = ocr_data.get("blocks", [])
    full_text = ocr_data.get("full_text", "")
    
    if not blocks and not full_text:
        logger.warning("⚠️ No blocks or full_text provided for reconstruction")
        return {"question": "", "reconstructed_answer": ""}
    
    # Format OCR data as JSON for LLM
    ocr_json = json.dumps(ocr_data, ensure_ascii=False, indent=2)
    
    system_prompt = """You are a faithful transcriber for UPSC handwritten answers. Your task:
1. Identify the QUESTION from the OCR text (look for question markers, numbered items, or explicit question text)
2. Reconstruct the STUDENT'S ANSWER from the OCR blocks and full text

RULES:
- Use only the provided OCR text. Do not add new knowledge.
- Do not correct factual content.
- You may fix only spacing/case for readability.
- If multiple blocks imply comparison or side-by-side columns, convert them to a comparative list.
- If a diagram/flowchart/table is visually implied, insert: [diagram: short descriptor]
- If text is unclear, use "[unclear]" exactly.
- Output must be clean readable text with paragraphs/bullets.

Do NOT evaluate. Do NOT explain. Only identify question and reconstruct answer.

Output format (JSON):
{
  "question": "the identified question text",
  "reconstructed_answer": "the reconstructed student answer"
}"""
    
    user_message = f"""Identify the question and reconstruct the student's handwritten answer from this OCR data:

{ocr_json}

Remember:
- Identify the question first (look for question markers, numbers, or explicit question text)
- Reconstruct only the student's answer (not the question)
- Use only provided OCR text
- Fix only spacing/case for readability
- Handle comparisons/columns logically
- Insert placeholders for diagrams/tables/flowcharts
- Use "[unclear]" for unclear text
- Do NOT evaluate, explain, or summarize

Return JSON with "question" and "reconstructed_answer" fields."""
    
    try:
        logger.info("🤖 Sending OCR data to LLM for question identification and answer reconstruction...")
        
        completion = llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0,  # Maximum accuracy
            max_tokens=2500,
            response_format={"type": "json_object"}  # Force JSON response
        )
        
        response_text = completion.choices[0].message.content
        
        # Parse JSON response
        try:
            result = json.loads(response_text)
            question = result.get("question", "").strip()
            reconstructed_answer = result.get("reconstructed_answer", "").strip()
            
            if not reconstructed_answer and full_text:
                # Fallback: use full_text if reconstruction is empty
                reconstructed_answer = full_text
                logger.warning("⚠️ Empty reconstruction, using full_text as fallback")
            
            logger.info(f"✅ Question identified: {question[:100]}...")
            logger.info(f"✅ Answer reconstructed: {len(reconstructed_answer)} chars")
            
            return {
                "question": question,
                "reconstructed_answer": reconstructed_answer
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract question and answer from text
            logger.warning("⚠️ Failed to parse JSON response, attempting text extraction...")
            lines = response_text.split("\n")
            question = ""
            answer = ""
            in_answer = False
            
            for line in lines:
                if "question" in line.lower() and ":" in line:
                    question = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif "answer" in line.lower() and ":" in line:
                    answer = line.split(":", 1)[1].strip().strip('"').strip("'")
                    in_answer = True
                elif in_answer:
                    answer += "\n" + line.strip()
            
            if not answer and full_text:
                answer = full_text
            
            return {
                "question": question or "",
                "reconstructed_answer": answer or response_text
            }
            
    except Exception as e:
        logger.error(f"❌ LLM reconstruction failed: {e}", exc_info=True)
        # Fallback: return full_text as answer
        return {
            "question": "",
            "reconstructed_answer": full_text or "\n".join([b.get("text", "") for b in blocks])
        }


def evaluate_and_improve(question: str,
                         student_answer: str,
                         static_context: Optional[str] = None,
                         current_bullets: Optional[str] = None,
                         word_count: int = 350,
                         edit_model: str = "gpt-4o-mini",
                         final_model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """
    Full pipeline: edit -> final answer.
    Returns dict with 'edited_answer' and 'final_answer'.
    """
    logger.info("Starting evaluate_and_improve pipeline...")
    try:
        edited = edit_student_answer(
            question=question,
            student_answer=student_answer,
            static_context=static_context,
            current_bullets=current_bullets,
            word_count=word_count,
            model=edit_model
        )
    except Exception as e:
        logger.error(f"Editing failed: {e}", exc_info=True)
        edited = student_answer  # fallback, preserve original

    try:
        final = produce_final_mains_answer(
            question=question,
            edited_answer=edited,
            static_context=static_context,
            current_bullets=current_bullets,
            word_count=word_count,
            model=final_model
        )
    except Exception as e:
        logger.error(f"Final generation failed: {e}", exc_info=True)
        final = edited  # fallback

    logger.info("Completed pipeline.")
    return {"edited_answer": edited, "final_answer": final}


# -------------------------
# CLI for quick testing
# -------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate and improve student answer (CLI)")
    parser.add_argument("--question", "-q", type=str, help="Question text", default=None)
    parser.add_argument("--student", "-s", type=str, help="Student answer text", default=None)
    parser.add_argument("--static", type=str, help="Path to static context file (optional)", default=None)
    parser.add_argument("--current", type=str, help="Path to current bullets file (optional)", default=None)
    parser.add_argument("--words", type=int, help="Target word count", default=350)
    args = parser.parse_args()

    q = args.question or "Explain the geographical factors influencing the location of large-scale digital infrastructure in India. Analyse how such investments are transforming the spatial pattern of economic activity."
    sa = args.student or "Student answer: Digital infrastructure prefers cities because of power, connectivity, and talent. It leads to jobs close to cities and increases inequality in rural areas."

    static_txt = ""
    current_txt = ""
    if args.static and os.path.exists(args.static):
        with open(args.static, "r", encoding="utf-8") as f:
            static_txt = f.read()
    if args.current and os.path.exists(args.current):
        with open(args.current, "r", encoding="utf-8") as f:
            current_txt = f.read()

    out = evaluate_and_improve(
        question=q,
        student_answer=sa,
        static_context=static_txt,
        current_bullets=current_txt,
        word_count=args.words
    )

    print("\n\n===== EDITED ANSWER =====\n")
    print(out["edited_answer"])
    print("\n\n===== FINAL MAINS ANSWER =====\n")
    print(out["final_answer"])
