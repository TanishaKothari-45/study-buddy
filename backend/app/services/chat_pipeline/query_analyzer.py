"""
Stage 0: Query Analysis

Uses Gemini to extract subject/domain/topics from the user question
and generate 2-3 search query variants for better retrieval recall.
"""
import json
import logging
from .state import QueryAnalysis

logger = logging.getLogger(__name__)

_SUBJECTS = ["Geography", "History", "Economy", "Polity", "Science & Tech", "Environment & Ecology"]

_ANALYSIS_PROMPT = """You are a UPSC study assistant. Analyze the student's question and return a JSON object.

Question: {question}

Return ONLY valid JSON with this structure:
{{
  "subject": "<one of: Geography, History, Economy, Polity, Science & Tech, Environment & Ecology, or null>",
  "major_domain": "<broad domain within subject, e.g. Physical Geography, Ancient Indian History, or null>",
  "sub_domain": "<specific sub-domain, e.g. Climatology, Vedic Period, or null>",
  "topics": ["<key topic 1>", "<key topic 2>"],
  "search_queries": [
    "<original question rephrased for retrieval>",
    "<a related angle or broader concept>",
    "<a third variant if distinctly useful, otherwise repeat variant 2>"
  ]
}}

Rules:
- search_queries must have exactly 3 items, each under 15 words
- topics must have 2-4 items
- If unsure about subject/domain, set to null
- Do NOT include explanation or markdown — pure JSON only"""


async def analyze_query(
    question: str,
    gemini_client,
    user_subject: str | None = None,
) -> QueryAnalysis:
    """
    Run LLM query analysis. If user_subject is set, use it as ground truth.
    Falls back gracefully to a minimal analysis on any error.
    """
    try:
        prompt = _ANALYSIS_PROMPT.format(question=question)
        raw = await gemini_client.generate_response(
            user_prompt=prompt,
            temperature=0.1,
        )

        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        data = json.loads(text)

        subject = user_subject or data.get("subject")
        # Validate subject
        if subject and subject not in _SUBJECTS:
            subject = user_subject  # fall back to user selection only

        search_queries = data.get("search_queries", [question])
        if not search_queries:
            search_queries = [question]
        # Ensure at most 3, at least 1
        search_queries = [q for q in search_queries if q][:3] or [question]

        analysis = QueryAnalysis(
            original_question=question,
            search_queries=search_queries,
            subject=subject,
            major_domain=data.get("major_domain"),
            sub_domain=data.get("sub_domain"),
            topics=data.get("topics", []),
        )
        logger.info(
            f"🔍 Query analysis: subject={analysis.subject}, "
            f"domain={analysis.major_domain}/{analysis.sub_domain}, "
            f"queries={len(analysis.search_queries)}"
        )
        return analysis

    except Exception as e:
        logger.warning(f"⚠️ Query analysis failed ({e}), using fallback")
        return QueryAnalysis(
            original_question=question,
            search_queries=[question],
            subject=user_subject,
            major_domain=None,
            sub_domain=None,
            topics=[],
        )
