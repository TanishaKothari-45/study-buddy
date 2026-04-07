"""
Chat Pipeline State — shared dataclasses passed between pipeline stages.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryAnalysis:
    original_question: str
    search_queries: list[str]       # 2-3 variants for multi-query retrieval
    subject: str | None             # e.g. "Geography", "History"
    major_domain: str | None        # e.g. "Physical Geography"
    sub_domain: str | None          # e.g. "Climatology"
    topics: list[str]               # key topics/concepts extracted


@dataclass
class RetrievedChunk:
    chunk_id: str
    filename: str
    content: str
    score: float
    metadata: dict[str, Any]


@dataclass
class Recommendation:
    type: str           # "deep_dive" | "related_concept" | "broader_topic" | "pyq_available" | "current_affairs"
    label: str          # Display text e.g. "Monsoon Mechanism — Deep Dive"
    topic: str          # micro_topic or sub_domain
    sub_domain: str
    major_domain: str
    query: str          # what to send as new chat question when clicked


@dataclass
class ChatPipelineState:
    question: str
    subject: str | None                         # user-selected subject from UI
    k: int = 7                                  # final chunks to use for generation
    analysis: QueryAnalysis | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
