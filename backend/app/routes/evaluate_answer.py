"""
Answer Evaluation endpoint for UPSC-style evaluation
"""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import logging
import time
import tempfile
from openai import OpenAI, RateLimitError

from ..core.config import settings
from ..utils.pdf_reader import extract_text_from_pdf
from ..utils.easyocr_processor import process_image_with_easyocr
from PIL import Image

logger = logging.getLogger(__name__)
router = APIRouter()

class EvaluateAnswerRequest(BaseModel):
    question: str
    answer_text: Optional[str] = None

class EvaluateAnswerResponse(BaseModel):
    question: str
    score: int
    max_score: int
    strengths: List[str]
    improvements: List[str]
    suggestions: List[str]
    model_answer_excerpt: Optional[str] = None

class OCRPreviewResponse(BaseModel):
    success: bool
    extracted_text: str
    original_text: str
    word_count: int
    confidence: str
    preprocessing_info: Dict[str, Any]
    error: Optional[str] = None

def extract_text_from_uploaded_file(file: UploadFile) -> str:
    """Extract text from uploaded PDF or text file"""
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.filename.split('.')[-1]}") as tmp_file:
            content = file.file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        # Extract text based on file type
        if file.filename.lower().endswith('.pdf'):
            pages_content = extract_text_from_pdf(tmp_file_path)
            text = "\n".join(page["text"] for page in pages_content if page.get("text"))
        else:  # Assume text file
            with open(tmp_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        # Clean up temporary file
        os.unlink(tmp_file_path)
        return text
        
    except Exception as e:
        logger.error(f"❌ Failed to extract text from uploaded file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract text from file: {str(e)}")

def evaluate_answer_with_gpt(question: str, answer: str, context: str, api_key: str, max_retries: int = 3) -> Dict[str, Any]:
    """Evaluate answer using GPT with UPSC evaluation criteria"""
    wait_time = 1.0
    
    for attempt in range(max_retries):
        try:
            client = OpenAI(api_key=api_key)
            
            system_prompt = """You are an expert UPSC Geography evaluator. Evaluate the student's answer based on UPSC Mains criteria:

**Evaluation Criteria (20 marks total):**
1. **Content Knowledge (8 marks)**: Accuracy, depth, and relevance of geographical concepts
2. **Structure & Presentation (4 marks)**: Introduction, body, conclusion, logical flow
3. **Analysis & Critical Thinking (4 marks)**: Analytical depth, cause-effect relationships
4. **Examples & Case Studies (2 marks)**: Relevant examples, current affairs integration
5. **Language & Expression (2 marks)**: Clarity, coherence, academic writing style

**Provide evaluation in this format:**
- Score: X/20
- Strengths: [List 3-4 specific strengths]
- Areas for Improvement: [List 3-4 specific areas]
- Specific Suggestions: [List 3-4 actionable suggestions]
- Model Answer Excerpt: [Provide a 2-3 sentence excerpt from a model answer]"""

            user_prompt = f"""Question: {question}

Student's Answer:
{answer}

Reference Context from Study Materials:
{context}

Evaluate this answer according to UPSC Mains standards and provide detailed feedback."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            completion = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=1500
            )
            
            evaluation_text = completion.choices[0].message.content
            
            # Parse the evaluation response
            lines = evaluation_text.split('\n')
            score = 0
            max_score = 20
            strengths = []
            improvements = []
            suggestions = []
            model_answer_excerpt = ""
            
            current_section = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if "Score:" in line or "score:" in line:
                    try:
                        score_part = line.split(":")[1].strip()
                        if "/" in score_part:
                            score = int(score_part.split("/")[0].strip())
                    except:
                        pass
                elif "Strengths:" in line.lower():
                    current_section = "strengths"
                elif "Areas for Improvement:" in line.lower() or "Improvement:" in line.lower():
                    current_section = "improvements"
                elif "Suggestions:" in line.lower():
                    current_section = "suggestions"
                elif "Model Answer Excerpt:" in line.lower():
                    current_section = "model"
                elif line.startswith("-") or line.startswith("•"):
                    content = line[1:].strip()
                    if current_section == "strengths":
                        strengths.append(content)
                    elif current_section == "improvements":
                        improvements.append(content)
                    elif current_section == "suggestions":
                        suggestions.append(content)
                elif current_section == "model":
                    model_answer_excerpt += line + " "
                elif current_section and not line.startswith(("Score", "Strengths", "Areas", "Suggestions", "Model")):
                    # Add to current section
                    if current_section == "strengths":
                        strengths.append(line)
                    elif current_section == "improvements":
                        improvements.append(line)
                    elif current_section == "suggestions":
                        suggestions.append(line)
                    elif current_section == "model":
                        model_answer_excerpt += line + " "
            
            # Ensure we have at least some content
            if not strengths:
                strengths = ["Good attempt at addressing the question"]
            if not improvements:
                improvements = ["Could benefit from more specific examples"]
            if not suggestions:
                suggestions = ["Try to include more current affairs and case studies"]
            
            return {
                "score": score,
                "max_score": max_score,
                "strengths": strengths[:5],  # Limit to 5 items
                "improvements": improvements[:5],
                "suggestions": suggestions[:5],
                "model_answer_excerpt": model_answer_excerpt.strip()
            }

        except RateLimitError as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                wait_time *= 2
            else:
                logger.warning("⚠️ Rate limit persists, using basic evaluation")
                return {
                    "score": 12,
                    "max_score": 20,
                    "strengths": ["Good attempt at addressing the question", "Shows understanding of basic concepts"],
                    "improvements": ["Could benefit from more specific examples", "Structure could be improved"],
                    "suggestions": ["Include more current affairs", "Add case studies", "Improve conclusion"],
                    "model_answer_excerpt": "A model answer would include a clear introduction, well-structured main body with sub-points, relevant examples, and a concise conclusion."
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to evaluate answer: {e}")
            return {
                "score": 10,
                "max_score": 20,
                "strengths": ["Attempted to answer the question"],
                "improvements": ["Technical evaluation unavailable"],
                "suggestions": ["Please try again later"],
                "model_answer_excerpt": "Evaluation service temporarily unavailable."
            }

@router.post("/preview-ocr/")
async def preview_ocr_extraction(
    answer_file: UploadFile = File(...)
):
    """
    Preview OCR extraction without evaluation - shows what text was extracted
    """
    try:
        # Save the file temporarily
        temp_path = f"/tmp/{answer_file.filename}"
        with open(temp_path, "wb") as f:
            content = await answer_file.read()
            f.write(content)
        
        full_text = ""
        preprocessing_info = {}
        
        # Check if it's a PDF and convert to images
        if answer_file.filename.lower().endswith('.pdf'):
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(temp_path)
                logger.info(f"📄 Converted PDF to {len(pages)} pages")
                
                # Process each page using EasyOCR
                for i, page in enumerate(pages):
                    logger.info(f"🔍 Processing page {i+1}/{len(pages)} with EasyOCR")
                    
                    # Process directly with EasyOCR
                    result = process_image_with_easyocr(page, f"page_{i+1}")
                    
                    if result.get("success"):
                        full_text += f"\n--- Page {i+1} ---\n" + result["text"]
                        # Collect confidence scores from all pages
                        if "confidence" not in preprocessing_info:
                            preprocessing_info = {
                                "image_size": result.get("image_size"),
                                "word_count": result.get("word_count", 0),
                                "confidence": result.get("confidence", 0),
                                "detections": result.get("detections", 0),
                                "confidences": []
                            }
                        preprocessing_info["confidences"].append(result.get("confidence", 0))
                        preprocessing_info["word_count"] += result.get("word_count", 0)
                        preprocessing_info["detections"] += result.get("detections", 0)
                    else:
                        full_text += f"\n--- Page {i+1} ---\n[OCR failed: {result.get('error', 'Unknown error')}]"
                        
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="pdf2image not installed. Install with: pip install pdf2image"
                )
        else:
            # Handle image files directly using EasyOCR
            image = Image.open(temp_path).convert("RGB")
            result = process_image_with_easyocr(image, answer_file.filename)
            
            if result.get("success"):
                full_text = result["text"]
                preprocessing_info = {
                    "image_size": result.get("image_size"),
                    "word_count": result.get("word_count", 0),
                    "confidence": result.get("confidence", 0),
                    "detections": result.get("detections", 0)
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"OCR extraction failed: {result.get('error', 'Unknown error')}"
                )
        
        # Clean up temp file
        os.unlink(temp_path)
        
        if not full_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the uploaded file. Please ensure the image/PDF is clear and readable."
            )
        
        # Calculate average confidence if we have confidences from multiple pages
        avg_confidence = 0
        if preprocessing_info.get("confidences"):
            avg_confidence = sum(preprocessing_info["confidences"]) / len(preprocessing_info["confidences"])
            preprocessing_info["avg_confidence"] = avg_confidence
        elif preprocessing_info.get("confidence"):
            avg_confidence = preprocessing_info["confidence"]
        
        # Determine confidence level
        if avg_confidence >= 0.7:
            confidence_level = "high"
        elif avg_confidence >= 0.5:
            confidence_level = "medium"
        else:
            confidence_level = "low"
        
        return OCRPreviewResponse(
            success=True,
            extracted_text=full_text,
            original_text=full_text,  # Same as extracted for now
            word_count=len(full_text.split()),
            confidence=confidence_level,
            preprocessing_info=preprocessing_info
        )
        
    except Exception as e:
        logger.error(f"❌ OCR preview failed: {e}")
        return OCRPreviewResponse(
            success=False,
            extracted_text="",
            original_text="",
            word_count=0,
            confidence="low",
            preprocessing_info={},
            error=str(e)
        )

@router.post("/upload-handwritten/")
async def upload_handwritten_answer(
    request: Request,
    question: str = Form(...),
    answer_file: UploadFile = File(...)
):
    """
    Upload and process handwritten answer using EasyOCR (CPU-friendly)
    """
    try:
        # Save the file temporarily
        temp_path = f"/tmp/{answer_file.filename}"
        with open(temp_path, "wb") as f:
            content = await answer_file.read()
            f.write(content)
        
        full_text = ""
        
        # Check if it's a PDF and convert to images
        if answer_file.filename.lower().endswith('.pdf'):
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(temp_path)
                logger.info(f"📄 Converted PDF to {len(pages)} pages")
                
                for i, page in enumerate(pages):
                    logger.info(f"🔍 Processing page {i+1}/{len(pages)} with EasyOCR")
                    result = process_image_with_easyocr(page, f"page_{i+1}")
                    if result.get("success"):
                        full_text += f"\n--- Page {i+1} ---\n" + result["text"]
                    else:
                        full_text += f"\n--- Page {i+1} ---\n[OCR failed: {result.get('error', 'Unknown error')}]"
                    
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="pdf2image not installed. Install with: pip install pdf2image"
                )
        else:
            # Handle image files directly
            image = Image.open(temp_path).convert("RGB")
            result = process_image_with_easyocr(image, answer_file.filename)
            if result.get("success"):
                full_text = result["text"]
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"OCR extraction failed: {result.get('error', 'Unknown error')}"
                )
        
        # Clean up temp file
        os.unlink(temp_path)
        
        if not full_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the uploaded file. Please ensure the image/PDF is clear and readable."
            )
        
        # Now evaluate the extracted text
        return await evaluate_extracted_answer(request, question, full_text)
        
    except Exception as e:
        logger.error(f"❌ Handwritten answer processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def evaluate_extracted_answer(request: Request, question: str, answer_text: str) -> EvaluateAnswerResponse:
    """Evaluate extracted answer text using the existing evaluation pipeline"""
    try:
        # Switch to the enriched collection
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.switch_to_collection("geography_docs_enriched")
        
        # Get relevant chunks for context
        chunks = chroma_handler.query_documents(question, k=8)
        context = "\n\n".join(chunk["content"] for chunk in chunks) if chunks else "No reference material available."

        # Evaluate answer using GPT if available
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            evaluation = evaluate_answer_with_gpt(question, answer_text, context, api_key)
        else:
            # Basic evaluation without GPT
            word_count = len(answer_text.split())
            evaluation = {
                "score": min(15, max(5, word_count // 20)),  # Basic scoring based on length
                "max_score": 20,
                "strengths": ["Answer provided", "Shows effort"],
                "improvements": ["OpenAI API not available for detailed evaluation"],
                "suggestions": ["Please ensure OpenAI API key is configured for detailed feedback"],
                "model_answer_excerpt": "Detailed evaluation requires OpenAI API access."
            }

        return EvaluateAnswerResponse(
            question=question,
            score=evaluation["score"],
            max_score=evaluation["max_score"],
            strengths=evaluation["strengths"],
            improvements=evaluation["improvements"],
            suggestions=evaluation["suggestions"],
            model_answer_excerpt=evaluation["model_answer_excerpt"]
        )

    except Exception as e:
        logger.error(f"❌ Answer evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def evaluate_answer(
    request: Request,
    question: str = Form(...),
    answer_text: Optional[str] = Form(None),
    answer_file: Optional[UploadFile] = File(None)
):
    """
    Evaluate a student's answer using UPSC Mains criteria.
    """
    try:
        # Extract answer text
        if answer_file:
            answer = extract_text_from_uploaded_file(answer_file)
        elif answer_text:
            answer = answer_text
        else:
            raise HTTPException(status_code=400, detail="Either answer_text or answer_file must be provided")
        
        if not answer.strip():
            raise HTTPException(status_code=400, detail="Answer cannot be empty")
        
        # Switch to the enriched collection
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.switch_to_collection("geography_docs_enriched")
        
        # Get relevant chunks for context
        chunks = chroma_handler.query_documents(question, k=8)
        context = "\n\n".join(chunk["content"] for chunk in chunks) if chunks else "No reference material available."

        # Evaluate answer using GPT if available
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            evaluation = evaluate_answer_with_gpt(question, answer, context, api_key)
        else:
            # Basic evaluation without GPT
            word_count = len(answer.split())
            evaluation = {
                "score": min(15, max(5, word_count // 20)),  # Basic scoring based on length
                "max_score": 20,
                "strengths": ["Answer provided", "Shows effort"],
                "improvements": ["OpenAI API not available for detailed evaluation"],
                "suggestions": ["Please ensure OpenAI API key is configured for detailed feedback"],
                "model_answer_excerpt": "Detailed evaluation requires OpenAI API access."
            }

        return EvaluateAnswerResponse(
            question=question,
            score=evaluation["score"],
            max_score=evaluation["max_score"],
            strengths=evaluation["strengths"],
            improvements=evaluation["improvements"],
            suggestions=evaluation["suggestions"],
            model_answer_excerpt=evaluation["model_answer_excerpt"]
        )

    except Exception as e:
        logger.error(f"❌ Answer evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
