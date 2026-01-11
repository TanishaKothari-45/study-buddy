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
Extract 3-5 keywords from this UPSC question, RANKED BY IMPORTANCE for news search.

RANKING RULES (most important first):
1. Core subject + specific entity (COMBINED): "tribal agriculture", "coastal flooding", "forest fires", "migration patterns"
2. Geographic specificity: state/region names (Odisha, Kerala, Northeast, Himalayas) OR demographic groups if not in #1
3. Related concepts/qualifiers: impacts, causes, policies, climate change
4. Generic context terms: India, development, geography (lowest priority)

KEYWORD CONSTRUCTION:
- Combine subject + entity/phenomenon in first keyword when both are important
- Keep geographic names as separate keywords for precise filtering
- Avoid redundant words (don't repeat "India" if already in context)

Return ONLY a JSON array with most important keywords FIRST.

Examples:
- "Impact of drought on tribal agriculture in Odisha" 
  → ["tribal agriculture", "drought impact", "Odisha", "rural livelihoods"]
  (combines tribal+agriculture, then qualifier+impact, then region)

- "Why are forest fires increasing in India?" 
  → ["forest fires", "wildfire increase", "climate change"]
  (core subject first, skip "India" as generic)

- "Climate change effects on coastal women in Kerala"
  → ["coastal women", "climate change impacts", "Kerala", "vulnerability"]
  (combines coastal+women, then change+impacts, then region)

- "Formation of fjords in Scandinavian areas"
  → ["fjords formation", "Scandinavia", "glacial landscapes"]
  (combines fjords+formation, then region)

- "Migration patterns of scheduled tribes in Northeast India"
  → ["tribal migration", "Northeast India", "displacement patterns", "indigenous communities"]
  (combines tribal+migration, then region, then related concepts)

- "Drought impact on agriculture in Odisha"
  → ["drought agriculture", "Odisha", "crop failure", "rural distress"]
  (combines drought+agriculture as single phenomenon)

Query:
"""
