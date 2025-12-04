# llm/prompts.py
"""
Prompts for LLM-based summarization.
Designed for UPSC exam preparation context.
"""

# -------------------------------------------------
# ARTICLE SUMMARY PROMPT (Fact-focused, no fluff)
# -------------------------------------------------
ARTICLE_ONE_LINER_PROMPT = """
Summarize this news for UPSC preparation in 30-50 words.

RULES:
- START DIRECTLY with the fact/event. NO "India has experienced..." or "This article reports..."
- Format: "Factors contributing to rise include X, Y, Z, as per [Source]."
- Keep ALL numbers, percentages, amounts, dates.
- NO extra wording. Be telegraphic but grammatically correct.

EXAMPLE:
❌ "India has seen a surge in fires. Data shows 50% increase."
✅ "50% increase in forest fires recorded due to dry spell and shifting agriculture, as per FSI data."

ARTICLE:
"""

# -------------------------------------------------
# EDITORIAL SUMMARY PROMPT (Analytical, argument-focused)
# -------------------------------------------------
EDITORIAL_SUMMARY_PROMPT = """
Summarize this editorial's argument in 80-120 words.

RULES:
- START DIRECTLY with the argument. NO "The editorial argues..." or "The author suggests..."
- Format: "Rapid urbanization in Asia poses flood risks due to X. Regions experiencing Y. Urgent need for Z."
- Use bullet points if helpful for suggestions.
- Keep cited data, names, case studies.
- NO filler phrases.

EDITORIAL:
"""

# -------------------------------------------------
# BATCH SUMMARIZATION PROMPT
# -------------------------------------------------
BATCH_SUMMARY_PROMPT = """
Summarize news for UPSC exam preparation.

INPUT: Multiple article leads + one editorial extract (or null).

OUTPUT: JSON with this exact structure:
{
  "article_summaries": ["30-50 word summary of article 1...", ...],
  "editorial_summary": "80-120 word summary of editorial..." or null
}

ARTICLE SUMMARY RULES:
- START DIRECTLY with fact/event. NO "The article states..."
- "Factors include X, Y, Z, as per [Source]."
- Keep ALL numbers, percentages, dates.
- NO extra wording.

EDITORIAL SUMMARY RULES:
- START DIRECTLY with argument. NO "The editorial argues..."
- "Rapid urbanization poses risks due to X. Urgent need for Y."
- Keep cited data and case studies.
- NO filler phrases.

RETURN ONLY VALID JSON.
"""

# -------------------------------------------------
# KEYWORD EXTRACTION PROMPT
# -------------------------------------------------
KEYWORD_EXTRACTION_PROMPT = """
Extract core topic keywords from this UPSC-style query.
Return ONLY a JSON array of 3-5 keywords (as strings).
Keywords should be suitable for news search queries.

Examples:
- "Why are forest fires increasing?" → ["forest fires", "wildfires", "climate change"]
- "India-China border tensions" → ["India China", "border dispute", "LAC"]

Query:
"""
