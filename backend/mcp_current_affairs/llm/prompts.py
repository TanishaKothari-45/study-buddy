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
- State the KEY FACT: WHO did WHAT, WHEN, WHERE, HOW MUCH
- Keep ALL numbers, percentages, amounts, dates, source names
- NO generic statements like "this highlights the need for..." or "this is important because..."
- If there's a study/report, name it
- End with the fact, not with implications

EXAMPLE:
❌ "Climate change is causing wildfires. Experts say urgent action is needed to protect public health."
✅ "Canada's 2023 wildfires released 647 million tonnes of CO2, equivalent to India's annual emissions, according to Copernicus Atmosphere Monitoring Service."

ARTICLE:
"""

# -------------------------------------------------
# EDITORIAL SUMMARY PROMPT (Analytical, argument-focused)
# -------------------------------------------------
EDITORIAL_SUMMARY_PROMPT = """
Summarize this editorial's argument in 80-120 words.

RULES:
- State the main thesis/argument first
- Include 2-3 key supporting points with specific examples
- Note any policy recommendations
- Keep cited data, names, case studies
- NO generic filler phrases

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
- State KEY FACT: WHO, WHAT, WHEN, WHERE, HOW MUCH
- Keep ALL numbers, percentages, dates, source names
- NO generic phrases like "this highlights..." or "experts say..."
- If study/report mentioned, name it
- End with fact, not implications

EDITORIAL SUMMARY RULES:
- State main thesis first
- Include 2-3 supporting points with examples
- Keep cited data and case studies
- Note policy recommendations if any

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
