"""
Feedback endpoint for user ratings on generated questions
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from ..utils.memory_manager import record_feedback, get_high_quality_examples

logger = logging.getLogger(__name__)
router = APIRouter()


class FeedbackRequest(BaseModel):
    question_text: str = Field(..., description="The question text")
    topic: str = Field(..., description="Topic/subject area")
    difficulty: str = Field(..., description="Difficulty level (easy/medium/hard)")
    quality: str = Field(..., description="Quality rating: 'high', 'medium', or 'low'")
    reason: Optional[str] = Field(None, description="Optional reason/comment for the rating")


class FeedbackResponse(BaseModel):
    success: bool
    message: str


@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(feedback_request: FeedbackRequest):
    """
    Submit user feedback/rating for a generated question.
    
    This feedback is used to:
    1. Improve question generation through few-shot learning
    2. Track question quality over time
    3. Build a database of high-quality question examples
    
    Flow:
    - User rates a question quality ('high', 'medium', 'low')
    - Feedback is stored in memory DB
    - High-quality questions are used as few-shot examples in future generations
    """
    try:
        # Validate quality value
        if feedback_request.quality.lower() not in ['high', 'medium', 'low']:
            raise HTTPException(
                status_code=400,
                detail="Quality must be 'high', 'medium', or 'low'"
            )
        
        logger.info(f"📝 [FEEDBACK] Received feedback: quality={feedback_request.quality}, topic={feedback_request.topic}")
        
        # Store feedback in database
        record_feedback(
            question_text=feedback_request.question_text,
            topic=feedback_request.topic,
            difficulty=feedback_request.difficulty,
            quality=feedback_request.quality.lower(),
            reason=feedback_request.reason
        )
        
        logger.info(f"✅ [FEEDBACK] Stored feedback successfully")
        return FeedbackResponse(
            success=True,
            message=f"Feedback stored successfully. Quality: {feedback_request.quality}"
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [FEEDBACK] Feedback submission failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit feedback: {str(e)}"
        )


@router.get("/stats")
async def get_feedback_stats():
    """
    Get statistics about feedback database.
    """
    try:
        # Get high-quality examples
        high_quality = get_high_quality_examples(limit=100)
        
        return {
            "total_high_quality": len(high_quality),
            "message": "Feedback statistics retrieved successfully"
        }
    except Exception as e:
        logger.error(f"❌ Failed to get feedback stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get feedback statistics: {str(e)}"
        )

