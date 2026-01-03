from typing import List, Optional
from pydantic import BaseModel, Field

class MarginComment(BaseModel):
    """Margin comment anchored to specific text in the student's answer."""
    anchor_text: str = Field(
        description="Exact phrase or short excerpt from the student's answer"
    )
    comment: str = Field(
        description="Examiner-style remark explaining the issue or merit"
    )
    comment_type: str = Field(
        description="Type of comment: strength, weakness, omission, directive_misalignment, evidence_gap, structure_issue, visual_gap"
    )
    severity: str = Field(
        description="Severity level: low, medium, or high"
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        description="Optional: very brief guidance on how this could be improved or corrected"
    )

class CriticalGapAndRemedy(BaseModel):
    """Critical gap identified in the answer with its remedy."""
    gap: str = Field(
        description="Description of the fault or missing element"
    )
    remedy: str = Field(
        description="Concise, actionable instruction on how to fix it"
    )

class FeedbackDetails(BaseModel):
    """Structured feedback for student answer evaluation."""
    strengths: List[str] = Field(
        default_factory=list,
        description="Specific strengths of the student's answer"
    )
    critical_gaps_and_remedies: List[CriticalGapAndRemedy] = Field(
        default_factory=list,
        description="Critical gaps identified with actionable remedies"
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
    margin_comments: List[MarginComment] = Field(
        default_factory=list,
        description="Margin-style comments anchored to specific parts of the answer"
    )

class EvaluationResponse(BaseModel):
    """Structured response for answer evaluation."""
    paper_and_subject_identification: Optional[dict] = Field(
        default=None,
        description="Identified GS Paper, Subject Domain, Primary Domain, and Secondary Domain"
    )
    # Note: paper_and_subject_identification dict structure:
    # {
    #   "gs_paper": "GS1",
    #   "subject_domain": "Physical_Geography", # Exact JSON Key
    #   "primary_domain": "Geography",
    #   "secondary_domain": "Volcanism"
    # }
    improved_answer: str = Field(
        min_length=1,
        description="Improved answer in markdown format following IBC rules"
    )
    feedback: FeedbackDetails = Field(
        description="Detailed feedback on the student's answer"
    )
