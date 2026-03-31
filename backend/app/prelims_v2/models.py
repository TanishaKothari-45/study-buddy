"""
Shared Pydantic models for the v2 prelims pipeline.
"""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SubConceptItem(BaseModel):
    """Structured sub-concept reference — topic name + relationship aspect."""
    topic:          str    # sub_concept topic text (verbatim from concept pool)
    aspect:         str    # impact | mechanism | process | comparison | application
    source_concept: str = ""  # "" = own concept; concept name = borrowed from that concept

# backward-compat alias
SubConcept = SubConceptItem


class QuestionSkeleton(BaseModel):
    """Blueprint unit produced by Stage 0."""
    skeleton_id: str                              # e.g. "sk_001"
    question_type: str                            # multi_statement | assertion_reason | match_pair | fact | spatial
    concept: str                                  # e.g. "Monsoon"
    sub_concepts: List[SubConceptItem] = []           # interlinked {topic, aspect} pairs for targeted retrieval
    difficulty: str = "medium"                   # easy | medium | hard
    ca_flag: bool = False                         # requires current-affairs search?
    ca_event: str = ""                            # e.g. "2024 below-normal SW monsoon IMD June forecast"
    trap_strategy: str = ""                       # trap_id from registry e.g. "GEO_T04"
    trap_name: str = ""                           # human-readable trap name
    sub_domain: str = ""                          # sub_domain hint for Pinecone query


class TrapRule(BaseModel):
    """Distractor & trap rules attached to a skeleton by Stage 2."""
    trap_id: str
    trap_name: str
    description: str
    how_to_generate: str
    distractor_strategy: str
    generation_rules: Dict[str, Any] = Field(default_factory=dict)
    real_pyq_example: str = ""


class DifficultyBundle(BaseModel):
    """Skeleton + injected difficulty/trap rules — input for Stage 3."""
    skeleton: QuestionSkeleton
    trap_rule: Optional[TrapRule] = None
    # Prose block that is appended to the generation prompt
    difficulty_instruction: str = ""


class V2GeneratedQuestion(BaseModel):
    """Output from Stage 3 — single question with quality metadata."""
    skeleton_id: str
    question: str
    options: List[str]                        # ["A) ...", "B) ...", "C) ...", "D) ..."]
    correct_answer: str                       # "A" | "B" | "C" | "D"
    explanation: str
    # Quality flags set by Stage 4
    trap_verified: bool = False
    ca_in_stem: bool = False                  # CA event appears in question stem (not explanation only)
    quality_score: float = 0.0
    # Source metadata
    sub_domain: str = ""
    difficulty: str = ""
    question_type: str = ""


class V2JobRequest(BaseModel):
    """API request body for /mock-test/v2/generate-async."""
    num_questions: int = 20
    topics: List[str] = []
    subject: str = "Geography"


# Valid question type slugs — enforced by Gemini response_schema
QuestionTypeLiteral = Literal[
    "multi_statement",
    "match_pair",
    "assertion_reason",
    "direct_fact",
    "spatial",
    "chronology",
    "data_based",
]


class BlueprintQuestion(BaseModel):
    """
    Single question skeleton in the blueprint.
    This is the structured output returned by the Gemini Flash blueprint call.
    """
    id: str                                              # "Q1", "Q2", ...
    type: QuestionTypeLiteral                             # MUST be one of the valid slugs
    concept: str                                         # from concept_pool provided in the prompt
    sub_concepts: List[SubConcept] = Field(min_length=2) # 2-3 {topic, aspect} from the pool
    trap_id: str                                         # from trap registry (e.g. "GEO_T04")
    difficulty: Literal["easy", "medium", "hard"]
    ca_linked: bool                                      # true if current affairs angle required


class BlueprintOutput(BaseModel):
    """Full blueprint returned by Stage 0 — wrapper for Gemini response_schema."""
    questions: List[BlueprintQuestion]
