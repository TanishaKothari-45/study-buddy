from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class MainsAnswerRequest(BaseModel):
    """Request structure for mains answer generation."""
    question: str = Field(..., description="The mains question to generate an answer for")
    word_count: int = Field(default=500, description="Target word count for the answer")

class MainsAnswerResponse(BaseModel):
    """Response structure for mains answer generation."""
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="The generated answer in markdown format")
    compressed_answer: Optional[str] = Field(default=None, description="Compressed version of the answer if applicable")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Source documents used for generation")
    word_count_actual: int = Field(..., description="Actual word count of the generated answer")
    word_count_compressed: Optional[int] = Field(default=None, description="Word count of the compressed answer")

class QueryRequest(BaseModel):
    """Request structure for general queries."""
    query: str = Field(..., description="The query string")
    mode: str = Field(default="concise", description="Query mode (concise or detailed)")
