"""
mains_prompt.py
Prompt templates and assembler for UPSC Mains Geography answer generation.

Now uses shared prompts from app/prompts/shared_mains_prompts.py for consistency.
"""

from typing import Optional
import sys
from pathlib import Path

# Add app directory to path for imports
app_dir = Path(__file__).resolve().parent / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

# Import shared prompts
try:
    from app.prompts.shared_mains_prompts import get_mains_answer_system_prompt
    USE_SHARED_PROMPTS = True
except ImportError:
    # Fallback to legacy prompts if shared prompts not available
    USE_SHARED_PROMPTS = False
    print("Warning: Could not import shared prompts, using legacy prompts")

# Legacy prompts (fallback only)
SYSTEM_BASE = """You are an expert UPSC Geography teacher, evaluator and answer-writing coach.

Your job: produce high-quality, exam-ready UPSC Mains answers in strict IBC format:
Introduction (2-3 lines) → Body (sub-headings + bullets + inline diagram suggestions) → Conclusion (1 paragraph, forward-looking).

Follow directive interpretation rules (below) and the cognitive & structural checks strictly.
"""

DIRECTIVE_DECODER = """
Directive -> structure (mandatory):
- Comment = take a stance & justify (if 'critically' → both sides)
- Examine = causes / implications / way forward
- Critically examine = strengths + weaknesses separately, then implications
- Discuss = broad overview → positives / negatives / causes / consequences
- Discuss critically = same as discuss but more rigorous reasoning
- Evaluate = assess worthiness → positives / negatives → give verdict
- Critically evaluate = evaluate + explicit judgement and trade-offs
- Analyse = break the topic into sub-parts and examine each dimension
- Explain = clarify how/why something is
- Elucidate = make clear using examples/data
- Elaborate = expand the core idea by adding layers of reasoning
- Substantiate = assert then support with evidence/reports/data
- To what extent = give a balanced graded judgement (fully/partly/marginally)
"""

COGNITIVE_FRAMEWORK = """
COGNITIVE FRAMEWORK:
1) Concept Focus: Base each question/answer on ONE core concept or mechanism.
2) Context Variation: Vary spatial (India/global), temporal (current/historical), domain (physical/human/environmental) perspectives.
3) Body Organization: Use sub-headings (physical / economic / social / environmental / policy/ Governance / Vulnerability / Human angle.
4) Point Discipline:Each important point must be supported with a named index/report/data/example.
5) Global bodies and conferences: Mention at least one global body or conference related agreement before conclusion.
6) Human Angle: Mandatory human impacts even for physical geography.
7) Diagram discipline: At least ONE Mermaid diagram inside body (explicit).
"""

# Legacy system prompt (fallback)
LEGACY_SYSTEM_PROMPT = "\n\n".join([SYSTEM_BASE, DIRECTIVE_DECODER, COGNITIVE_FRAMEWORK]).strip()


def assemble_mains_prompt(
    question: str,
    context: Optional[str],
    current_bullets: Optional[str],
    word_count: int = 350
) -> dict:
    """
    Construct a system + user prompt pair for the LLM.
    Returns dict: {"system": str, "user": str}
    
    Now uses shared prompts with Mermaid diagram support.
    """

    # Trim / safety
    context_trim = (context or "").strip()
    if len(context_trim) > 4200:
        context_trim = context_trim[:4200] + "\n\n[TRUNCATED CONTEXT]"

    current_trim = (current_bullets or "").strip()
    if len(current_trim) > 1400:
        current_trim = current_trim[:1400] + "\n\n[TRUNCATED CURRENT AFFAIRS]"

    # User-level guidance that will be fed as user message
    user_msg = f"""You are a Senior UPSC Mains answer-writer (Geography). Follow IBC strictly and include Mermaid diagrams.

Question: {question}

Reference Context (from materials):
{context_trim or 'No static context provided.'}

Current Affairs (use if relevant; crisp bullets):
{current_trim or 'No current affairs bullets provided.'}

Constraints / Format:
- INTRO: 2–3 lines. Must include either a definition, a data point/report citation, or a recent context or current affair (if applicable).
- BODY: Use sub-headings and bullets. Each bullet <= 18 words.
- BULLET FORMAT (CRITICAL): Every bullet MUST start with a dash (-). Example:
  - **Main point one** with evidence (IPCC 2023) and example.
  - **Main point two** with evidence and example.
  Never write bullets without the dash prefix. Each bullet on its own line.
- DIAGRAM: Include at least ONE Mermaid diagram. NEVER place diagram between a sub-heading and its bullets. Place it BEFORE the sub-heading or AFTER all bullets of a section.
- MAP: If the question contains keywords like "distribution", "where", "locate", "belts", "hotspots", "areas", "regional", or explicitly asks about countries/regions, include a map-json block per MAP_GENERATION_RULES (map-json before Body under 'Map/Diagram').
- CONCLUSION: 1 para with global best practices or global bodies initiatives + SDG + India's government policies or local community initiatives + related Indian constitution articles.
- WORD COUNT: Target ~{word_count} words. Acceptable range: 80%-140% of target. Only compress bullet language if exceeding 140%.
- For directive words (Analyse, Evaluate, Critically examine, Discuss), follow the Directive Decoder rules in SYSTEM PROMPT.
- Tone: concise, exam-style, zero fluff.

Output: Provide the answer only (no metadata), using markdown list format (- for bullets, each on new line), sub-headings, and Mermaid diagrams.
"""
    
    # Use shared prompts if available, otherwise fallback to legacy
    if USE_SHARED_PROMPTS:
        system_prompt = get_mains_answer_system_prompt()
    else:
        system_prompt = LEGACY_SYSTEM_PROMPT
    
    return {"system": system_prompt, "user": user_msg}
