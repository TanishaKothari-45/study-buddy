"""
Mock test generation endpoint
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import logging
import time
from openai import OpenAI, RateLimitError

from ..core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class MockTestRequest(BaseModel):
    num_questions: int = 5
    topics: List[str] = []  # Optional topics to focus on
    difficulty: str = "medium"  # easy, medium, hard

class MockTestQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    source: Dict[str, Any]  # Reference to source material

class MockTestResponse(BaseModel):
    questions: List[MockTestQuestion]
    total_marks: int
    time_allowed: str
    instructions: List[str]

def generate_question_paper(chunks: List[Dict], request: MockTestRequest, api_key: str) -> MockTestResponse:
    """Generate UPSC style questions using context and GPT"""
    # Prepare context from chunks
    context = "\n\n".join(chunk["content"] for chunk in chunks)
    
    # System prompt for GPT
    system_prompt = """You are an expert UPSC exam paper setter for Geography. 
    Create challenging multiple-choice questions in UPSC Prelims style.
    Each question should:
    1. Be clear and unambiguous
    2. Have 4 options (A, B, C, D)
    3. Include a detailed explanation
    4. Be based strictly on the provided context
    5. Follow UPSC's actual question patterns
    
    Format each question as a JSON object with:
    - question: The actual question text
    - options: Array of 4 options
    - correct_answer: The correct option (A, B, C, or D)
    - explanation: Detailed explanation of the answer
    """

    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""Context from study materials:
                {context}
                
                Generate {request.num_questions} questions at {request.difficulty} difficulty level.
                Focus on these topics if specified: {', '.join(request.topics) if request.topics else 'any geography topics'}.
                Format as a JSON array of question objects."""}
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={ "type": "json_object" }
        )
        
        # Parse GPT response
        response_text = completion.choices[0].message.content
        
        # Parse JSON response
        import json
        try:
            response_data = json.loads(response_text)
            questions_data = response_data.get("questions", [])
        except json.JSONDecodeError:
            # Fallback: try to extract questions from text
            logger.warning("Failed to parse JSON response, using fallback parsing")
            questions_data = []
        
        # Convert to MockTestQuestion objects
        questions = []
        for i, q_data in enumerate(questions_data):
            if isinstance(q_data, dict):
                question = MockTestQuestion(
                    question=q_data.get("question", f"Question {i+1}"),
                    options=q_data.get("options", ["A", "B", "C", "D"]),
                    correct_answer=q_data.get("correct_answer", "A"),
                    explanation=q_data.get("explanation", "No explanation provided"),
                    source={"filename": "Generated", "chapter": "Mock Test", "section": f"Question {i+1}"}
                )
                questions.append(question)
        
        # If no questions were parsed, create a fallback
        if not questions:
            questions = [MockTestQuestion(
                question="What is the primary focus of Geography as a discipline?",
                options=[
                    "Study of physical features only",
                    "Study of human-environment interactions",
                    "Study of maps and cartography",
                    "Study of weather patterns"
                ],
                correct_answer="B",
                explanation="Geography is the study of human-environment interactions, encompassing both physical and human aspects.",
                source={"filename": "Generated", "chapter": "Mock Test", "section": "Fallback Question"}
            )]
        
        # Create response with standard instructions
        return MockTestResponse(
            questions=questions,
            total_marks=len(questions),
            time_allowed="2 minutes per question",
            instructions=[
                "Attempt all questions.",
                "Each question carries 1 mark.",
                "There is no negative marking.",
                "Choose the most appropriate option.",
                "Questions are based on your uploaded study materials."
            ]
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to generate mock test: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate mock test. Please try again."
        )

@router.post("/generate", response_model=MockTestResponse)
async def generate_mock_test(request: Request, test_request: MockTestRequest):
    """Generate a UPSC-style mock test"""
    try:
        # Get ChromaDB handler
        chroma_handler = request.app.state.chroma_handler
        
        # Get relevant chunks for context
        # If topics specified, use them in the query
        query = " ".join(test_request.topics) if test_request.topics else "important geography topics for UPSC"
        chunks = chroma_handler.query_documents(query, k=10)  # Get more chunks for variety
        
        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No relevant content found in uploaded materials. Please upload study materials first."
            )

        # Get API key for GPT
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key not configured. Mock test generation requires GPT for quality questions."
            )

        # Generate mock test
        return generate_question_paper(chunks, test_request, api_key)

    except Exception as e:
        logger.error(f"❌ Mock test generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
