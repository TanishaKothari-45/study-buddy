from typing import List
from pydantic import BaseModel, Field

class FeedbackDetails(BaseModel):
    """Structured feedback for student answer evaluation."""
    strengths: List[str] = Field(
        default_factory=list,
        description="Specific strengths of the student's answer"
    )
    missing_elements: List[str] = Field(
        default_factory=list,
        description="Key points missing from the student's answer"
    )
    improvements_needed: List[str] = Field(
        default_factory=list,
        description="Actionable suggestions for improvement"
    )
    structure_feedback: str = Field(
        default="",
        description="Comment on IBC format adherence and structure"
    )
    evidence_feedback: str = Field(
        default="",
        description="Comment on use of reports/data/indices/examples"
    )
    overall_assessment: str = Field(
        default="",
        description="Brief overall assessment and encouragement"
    )

class EvaluationResponse(BaseModel):
    """Structured response for answer evaluation."""
    improved_answer: str = Field(
        min_length=1,
        description="Improved answer in markdown format following IBC rules"
    )
    feedback: FeedbackDetails = Field(
        description="Detailed feedback on the student's answer"
    )
