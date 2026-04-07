"""
Stage 2: Response Generation

Builds an improved UPSC-aware prompt and streams the LLM response.
"""
import logging
from typing import AsyncIterator
from .state import QueryAnalysis, RetrievedChunk

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a study buddy helping a UPSC aspirant understand topics — like a smart friend who knows the syllabus well.
Your job is to make things click, not to recite a textbook.
Explain with intuition first, then detail. Use everyday analogies where they help. Be conversational but accurate."""

_ANSWER_PROMPT = """You are a UPSC study assistant{subject_label}.

STUDY MATERIAL CONTEXT:
{context_text}

INSTRUCTIONS:
- Lead with the core idea or intuition — don't start with a definition dump
- Explain like you're talking to a smart friend, not writing a textbook entry
- Use analogies, "think of it as...", "the key thing here is..." where it helps things click
- Short paragraphs. Break it up. Use ## headings only when the topic genuinely has distinct parts
- Do NOT cite sources inline — sources are shown separately below
- Accurate and exam-relevant, but readable and natural — not dry or formal
- At the end, one brief line: "**UPSC angle:** ..." — which paper, prelims or mains, what angle examiners usually ask from

VISUAL RULES — include exactly ONE visual per answer, chosen by what adds most clarity:

**Map** (use for spatial/geographic topics):
- Monsoon branches and their coverage areas → map
- River basins, mountain ranges, distribution patterns → map
- Any topic where "where" or "which region" matters → map
- Format: output a ```map-json block. Schema:
```map-json
{{
  "type": "map",
  "mapType": "choropleth | markers | rivers | combined",
  "region": "india | world",
  "title": "Brief title",
  "choropleth": {{"values": {{"State/Region": value}}, "unit": "unit"}},
  "markers": [{{"name": "Location", "coordinates": [lon, lat], "type": "city|resource", "label": "label"}}],
  "arrows": [{{"from": [lon, lat], "to": [lon, lat], "label": "direction/flow"}}],
  "paths": [{{"label": "Feature name", "coordinates": [[lon, lat], [lon, lat]], "stroke": "#8B4513", "strokeWidth": 3}}],
  "rivers": true,
  "legendTitle": "Legend",
  "style": {{"colorScheme": "Blues | YlOrRd | YlGn | Greens"}}
}}
```
- `choropleth`: state-wise data (rainfall, crop production)
- `markers`: point locations (cities, ports, minerals)
- `combined`: multiple layers (arrows for monsoon branches + choropleth for rainfall)
- `arrows`: directional flows (monsoon tracks, trade winds, ocean currents)
- Coordinate order: [longitude, latitude] — Delhi [77.2, 28.6], Mumbai [72.8, 19.1]

**Mermaid diagram** (use for processes/mechanisms/hierarchies):
- Causal chains, feedback loops, step-by-step processes → flowchart
- Hierarchies, classification trees → mindmap or graph TD
- ALWAYS wrap ALL node labels in double quotes: `A["Label (with parens)"] --> B["Next step"]`
- Never bare unquoted labels with parentheses, apostrophes, or special characters
- For subgraphs: `subgraph "Title (parens ok here)"` not `subgraph Title (parens)`

**When to pick which:**
- Spatial coverage / distribution → Map
- Process / mechanism / cause-effect → Mermaid
- Comparison of few items → Table (markdown)
- Simple factual answer → no visual needed

Question: {question}"""


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """
    Build context string from retrieved chunks with smart truncation.

    Total budget: ~28k tokens (leaves room for prompt + output within Gemini limits).
    Top chunks get more budget; lower-ranked chunks get less.
    """
    from ...utils.smart_truncator import smart_truncate_context, estimate_tokens

    if not chunks:
        return "No relevant context found in study materials."

    selected = chunks[:7]
    n = len(selected)

    # Weighted budget: top chunks get more, lower ones get less.
    # 10k total — enough for focused chat; mains uses 28k.
    # Top 2 chunks get ~3k tokens each (a full NCERT section), rest get less.
    base_weights = [4.0, 4.0, 3.5, 3.0, 2.5, 2.0, 2.0][:n]
    total_weight = sum(base_weights)
    total_budget = 10000  # tokens

    parts = []
    for chunk, weight in zip(selected, base_weights):
        chunk_budget = int((weight / total_weight) * total_budget)
        truncated = smart_truncate_context(
            text=chunk.content,
            max_tokens=chunk_budget,
            strategy="head",        # keep foundational content first
            preserve_structure=True,
        )
        if truncated:
            parts.append(truncated)

    return "\n\n---\n\n".join(parts)


async def generate_response_text(
    question: str,
    analysis: QueryAnalysis,
    chunks: list[RetrievedChunk],
    gemini_client,
    temperature: float = 0.3,
) -> str:
    """Returns the full response text (before streaming simulation)."""
    subject_label = f" specializing in {analysis.subject}" if analysis.subject else ""
    context_text = _build_context(chunks)

    prompt = _ANSWER_PROMPT.format(
        subject_label=subject_label,
        context_text=context_text,
        question=question,
    )

    logger.info(f"💬 Generating response (context: {len(context_text)} chars)")

    return await gemini_client.generate_response(
        user_prompt=prompt,
        temperature=temperature,
        system_prompt=_SYSTEM_PROMPT,
    )


async def stream_text(text: str) -> AsyncIterator[str]:
    """Simulate streaming by yielding 40-char chunks with small delays."""
    import asyncio
    chunk_size = 40
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        if chunk:
            yield chunk
            await asyncio.sleep(0.015)
