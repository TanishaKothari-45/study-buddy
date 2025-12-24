"""
training_data.py

Endpoint for collecting training examples to improve feedback quality.

Flow:
  1) Upload answer (PDF/image) -> Gemini extracts text (OCR)
  2) User provides ideal feedback
  3) Store as training example in JSON file
  4) Use examples as few-shot prompts for better feedback generation

Usage:
  POST /training-data/extract-answer
  - file: PDF or image file (required)
  
  POST /training-data/submit
  - question: Question text
  - answer_text: OCR extracted answer text
  - ideal_feedback: User-provided feedback
"""

import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()

def clean_gemini_error(error_msg: str) -> str:
    """
    Clean Gemini API error messages for user-friendly display.
    Provides actionable guidance to help users resolve the issue.
    """
    # For quota errors (429)
    if '429' in error_msg and 'quota' in error_msg.lower():
        return "Failed to extract text: You have exceeded your Gemini API quota. Please check your usage at https://aistudio.google.com/app/apikey and upgrade your plan if needed, or try again after some time."
    
    if '429' in error_msg and 'rate limit' in error_msg.lower():
        return "Failed to extract text: Too many requests to Gemini API. Please wait a few minutes and try again."
    
    # For auth errors
    lower_msg = error_msg.lower()
    if 'api_key_invalid' in error_msg or 'api key not valid' in lower_msg or 'invalid api key' in lower_msg:
        return "Failed to extract text: Invalid Gemini API key. Please check your API key configuration. You can get a new key from https://aistudio.google.com/app/apikey"
    
    # For timeout errors
    if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
        return "Failed to extract text: Request timed out. The AI service is taking longer than expected. Please try again, or try with a smaller file."
    
    # For network/connection errors
    if 'connection' in error_msg.lower() or 'network' in error_msg.lower():
        return "Failed to extract text: Network connection error. Please check your internet connection and try again."
    
    # For empty response
    if 'empty response' in error_msg.lower():
        return "Failed to extract text: Received empty response from AI service. This is usually temporary - please try again in a moment."
    
    # For service unavailable
    if 'service unavailable' in error_msg.lower() or '503' in error_msg:
        return "Failed to extract text: AI service is temporarily unavailable. Please try again in a few minutes."
    
    # For server errors
    if '500' in error_msg or 'internal server error' in error_msg.lower():
        return "Failed to extract text: Server error occurred. We're working to fix this. Please try again or contact support if the issue persists."
    
    # Generic fallback with first sentence
    first_line = error_msg.split('\n')[0]
    first_sentence = first_line.split('.')[0]
    
    # Limit to reasonable length
    if len(first_sentence) > 120:
        first_sentence = first_sentence[:117] + '...'
    
    # Always prefix with "Failed to extract text:"
    if first_sentence and not first_sentence.startswith('Failed to extract text'):
        return f"Failed to extract text: {first_sentence}. Please try again or contact support if the issue persists."
    
    return "Failed to extract text: An unexpected error occurred. Please try again or contact support if the issue persists."

# Import Gemini client
try:
    from ..gemini_core.gemini_client import GeminiClient
    from ..gemini_core import settings_gemini_key
    GEMINI_API_KEY = settings_gemini_key.GEMINI_API_KEY
except ImportError as e:
    GeminiClient = None
    GEMINI_API_KEY = None
    logger.warning(f"Could not import Gemini client: {e}")

# Training data storage path
TRAINING_DATA_FILE = Path(__file__).parent.parent.parent / "data" / "training_examples.json"

def load_training_data():
    """Load existing training data"""
    if TRAINING_DATA_FILE.exists():
        with open(TRAINING_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"training_examples": []}

def save_training_data(data):
    """Save training data to file"""
    TRAINING_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@router.post("/extract-answer")
async def extract_answer_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    question: Optional[str] = Form(default=None)
):
    """
    Extract answer text from uploaded files using Gemini OCR.
    Supports multiple files for multi-page answers.
    
    Args:
        files: List of PDF or image files containing the handwritten answer
        question: Optional question text
    
    Returns:
        - question: Identified or provided question
        - answer_text: Extracted answer text (OCR) from all files combined
        - success: True if successful
        - files_processed: Number of files processed
    """
    if not GeminiClient or not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="Gemini client not available. Please check GEMINI_API_KEY configuration."
        )
    
    # Create temp directory for files
    temp_dir = tempfile.mkdtemp()
    temp_file_paths = []
    
    try:
        logger.info("=" * 70)
        logger.info("🔁 Starting extract-answer endpoint...")
        logger.info(f"   • Files: {len(files)} file(s)")
        logger.info(f"   • Question: {question[:100] if question else 'None (will identify)'}...")
        logger.info("=" * 70)
        
        # Initialize Gemini client
        gemini_client = GeminiClient(
            api_key=GEMINI_API_KEY,
            model_name="gemini-2.5-pro"
        )
        
        # Process each file and extract text
        all_answer_texts = []
        identified_question = question
        
        for idx, file in enumerate(files, 1):
            logger.info(f"📄 Processing file {idx}/{len(files)}: {file.filename}")
            
            # Read file content
            file_content = await file.read()
            
            # Save uploaded file temporarily
            file_ext = Path(file.filename).suffix.lower() if file.filename else '.pdf'
            temp_file_path = os.path.join(temp_dir, f"answer_{idx}{file_ext}")
            temp_file_paths.append(temp_file_path)
            
            with open(temp_file_path, "wb") as buffer:
                buffer.write(file_content)
            
            logger.info(f"✅ File {idx} saved to: {temp_file_path}")
            
            # Determine if it's PDF or image
            is_pdf = file_ext == '.pdf'
            is_image = file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
            
            if not (is_pdf or is_image):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {file_ext}. Please upload PDF or image file."
                )
            
            # Extract text from file - combine question and answer extraction in single API call
            if idx == 1 and not identified_question:
                # First file and no question provided - extract both question and answer in one call
                logger.info("📝 Extracting question and answer from first file (single API call)...")
                try:
                    combined_prompt = f"""Read the handwritten document and extract:

1. QUESTION: Identify the question being answered. Look for:
   - Question written at the top of the page
   - Topic/subject being discussed
   - Any numbered question (Q1, Q2, etc.)
   If you can't find an explicit question, infer it from the answer content.

2. ANSWER: Extract the complete answer text exactly as written, preserving structure and content.

Return your response in this exact format:
QUESTION: [the question text here]
ANSWER: [the answer text here]

This is page {idx} of {len(files)}."""
                    
                    if is_pdf:
                        combined_response = await gemini_client.generate_response(
                            user_prompt=combined_prompt,
                            pdf_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    else:
                        combined_response = await gemini_client.generate_response(
                            user_prompt=combined_prompt,
                            image_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    
                    # Parse the response to extract question and answer
                    response_text = combined_response.strip()
                    question_match = None
                    answer_match = None
                    
                    # Try to extract QUESTION and ANSWER sections
                    if "QUESTION:" in response_text and "ANSWER:" in response_text:
                        parts = response_text.split("ANSWER:", 1)
                        if len(parts) == 2:
                            question_part = parts[0].replace("QUESTION:", "").strip()
                            answer_part = parts[1].strip()
                            identified_question = question_part
                            answer_match = answer_part
                    elif "QUESTION:" in response_text:
                        # Only question found, extract it
                        question_part = response_text.split("QUESTION:", 1)[1].split("ANSWER:", 1)[0].strip()
                        identified_question = question_part
                        # Try to get answer from remaining text
                        if "ANSWER:" in response_text:
                            answer_match = response_text.split("ANSWER:", 1)[1].strip()
                    else:
                        # Fallback: treat entire response as answer, question not found
                        answer_match = response_text
                        identified_question = "Question not identified"
                    
                    if answer_match:
                        all_answer_texts.append(answer_match)
                        logger.info(f"✅ Extracted question: {identified_question[:100] if identified_question != 'Question not identified' else 'Not found'}...")
                        logger.info(f"✅ Extracted {len(answer_match)} chars from file {idx}")
                    else:
                        raise ValueError("Failed to extract answer from response")
                        
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ Combined extraction failed for file {idx}: {error_msg}")
                    # Clean error message for user display
                    clean_msg = clean_gemini_error(error_msg)
                    # Re-raise with cleaned message
                    raise HTTPException(status_code=500, detail=clean_msg)
                    
            elif idx == 1 and identified_question:
                # Question provided - only extract answer from first file
                logger.info(f"✅ Question already provided: {identified_question[:100]}...")
                logger.info(f"📝 Extracting answer text from file {idx}...")
                
                answer_prompt = f"""Read the handwritten answer and extract the complete text.

This is page {idx} of {len(files)} in the answer.

Return ONLY the answer text exactly as written, preserving the structure and content. Do not add any commentary or improvements."""
                
                try:
                    if is_pdf:
                        answer_text = await gemini_client.generate_response(
                            user_prompt=answer_prompt,
                            pdf_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    else:
                        answer_text = await gemini_client.generate_response(
                            user_prompt=answer_prompt,
                            image_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    
                    all_answer_texts.append(answer_text)
                    logger.info(f"✅ Extracted {len(answer_text)} chars from file {idx}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ Extraction failed for file {idx}: {error_msg}")
                    # Clean error message for user display
                    clean_msg = clean_gemini_error(error_msg)
                    # Re-raise with cleaned message
                    raise HTTPException(status_code=500, detail=clean_msg)
            else:
                # Subsequent files - only extract answer
                logger.info(f"📝 Extracting answer text from file {idx}...")
                
                answer_prompt = f"""Read the handwritten answer and extract the complete text.

This is page {idx} of {len(files)} in the answer.

Return ONLY the answer text exactly as written, preserving the structure and content. Do not add any commentary or improvements."""
                
                try:
                    if is_pdf:
                        answer_text = await gemini_client.generate_response(
                            user_prompt=answer_prompt,
                            pdf_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    else:
                        answer_text = await gemini_client.generate_response(
                            user_prompt=answer_prompt,
                            image_path=temp_file_path,
                            temperature=0.0,
                            max_retries=2
                        )
                    
                    all_answer_texts.append(answer_text)
                    logger.info(f"✅ Extracted {len(answer_text)} chars from file {idx}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ Extraction failed for file {idx}: {error_msg}")
                    # Clean error message for user display
                    clean_msg = clean_gemini_error(error_msg)
                    # Re-raise with cleaned message
                    raise HTTPException(status_code=500, detail=clean_msg)
        
        # Combine all answer texts
        combined_answer = "\n\n".join(all_answer_texts)
        
        logger.info(f"✅ Combined answer text: {len(combined_answer)} chars from {len(files)} file(s)")
        logger.info("=" * 70)
        logger.info("✅ Extraction complete!")
        logger.info("=" * 70)
        
        return {
            "question": identified_question,
            "answer_text": combined_answer,
            "files_processed": len(files),
            "success": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Extraction failed: {error_msg}", exc_info=True)
        # Clean error message for user display
        clean_msg = clean_gemini_error(error_msg)
        raise HTTPException(status_code=500, detail=clean_msg)
    
    finally:
        # Clean up temp files
        for temp_file_path in temp_file_paths:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
        # Clean up temp directory
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass


@router.post("/submit")
async def submit_training_example(
    question: str = Form(...),
    answer_text: str = Form(...),
    ideal_feedback: str = Form(...)
):
    """
    Submit a training example for few-shot learning.
    
    Args:
        question: The question text
        answer_text: The student's answer (OCR extracted)
        ideal_feedback: The ideal feedback provided by the user
    
    Returns:
        - success: True if successful
        - example_id: ID of the stored example
        - total_examples: Total number of training examples
    """
    try:
        logger.info("=" * 70)
        logger.info("💾 Storing training example...")
        logger.info(f"   • Question: {question[:50]}...")
        logger.info(f"   • Answer length: {len(answer_text)} chars")
        logger.info(f"   • Feedback length: {len(ideal_feedback)} chars")
        logger.info("=" * 70)
        
        # Load existing data
        training_data = load_training_data()
        
        # Create new example
        example_id = f"example_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        new_example = {
            "id": example_id,
            "question": question,
            "student_answer": answer_text,
            "ideal_feedback": ideal_feedback,
            "metadata": {
                "word_count": len(answer_text.split()),
                "created_at": datetime.now().isoformat(),
                "tags": []
            }
        }
        
        # Add to training examples
        training_data["training_examples"].append(new_example)
        
        # Save to file
        save_training_data(training_data)
        
        logger.info(f"✅ Training example stored: {example_id}")
        logger.info(f"   • Total examples: {len(training_data['training_examples'])}")
        logger.info("=" * 70)
        
        return {
            "success": True,
            "example_id": example_id,
            "total_examples": len(training_data["training_examples"])
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to store training example: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to store training example: {str(e)}")


@router.get("/examples")
async def get_training_examples():
    """
    Get all training examples.
    
    Returns:
        - training_examples: List of all training examples
        - total: Total number of examples
    """
    try:
        training_data = load_training_data()
        return {
            "training_examples": training_data["training_examples"],
            "total": len(training_data["training_examples"])
        }
    except Exception as e:
        logger.error(f"❌ Failed to load training examples: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load training examples: {str(e)}")
