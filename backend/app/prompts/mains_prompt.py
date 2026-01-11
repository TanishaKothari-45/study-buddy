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

Your job: produce high-quality, exam-ready UPSC Mains answers in strict IBC format with way forward section conditionally if relevant and adds value to the answer:
Introduction (2-3 lines) → Body (sub-headings + bullets + inline diagram suggestions) → (Conditional) Way Forward (2-3 bullets) → Conclusion (1 paragraph, forward-looking).

Follow directive interpretation rules (below) and the cognitive & structural checks strictly.
"""

DIRECTIVE_DECODER = """
Directive → expected examiner approach (mandatory alignment):

- Analyse = break the issue into components; examine each dimension logically; show interconnections.
- Examine = investigate causes, implications, and significance; avoid mere description.
- Critically examine = analyse strengths and weaknesses separately; assess implications.
- Discuss = present a balanced treatment covering multiple dimensions.
- Discuss critically = discuss + deeper reasoning, counter-arguments, and evaluation.
- Evaluate = assess positives and negatives; weigh evidence; arrive at a reasoned judgement.
- Critically evaluate = evaluate + explicit judgement, trade-offs, and limitations.
- Assess = judge validity or impact by weighing evidence; similar to evaluate but judgement-focused.
- To what extent = provide a graded, balanced judgement (fully / partly / marginally) with justification.
- Explain = clarify how or why something occurs.
- Describe = give a factual, detailed account without analysis.
- Elucidate = clarify with examples, data, or illustrations.
- Elaborate = expand the core idea by adding layers of reasoning.
- Substantiate = assert a claim and support it with evidence, reports, or data.
- Contrast / Compare = highlight key differences (and similarities if asked) between phenomena.
- Outline = present key points and structure concisely without detailed explanation.
- Show how = explain stages, processes, or causal progression logically.
- Give an account of = provide a descriptive narrative of what happens (not why).
- Identify = list key features or elements and indicate their relevance briefly.
- State = specify key facts or points concisely without elaboration.
- Summarise = present a brief, concise synthesis of main points only.
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
    Uses smart truncation to respect sentence boundaries and token limits.
    """
    
    # Import smart truncator
    try:
        from ..utils.smart_truncator import truncate_with_token_budget
        use_smart_truncation = True
    except ImportError:
        use_smart_truncation = False
        print("Warning: Could not import smart_truncator, using legacy truncation")

    # Smart truncation with token budget allocation
    if use_smart_truncation:
        context_trim, current_trim = truncate_with_token_budget(
            static_context=context,
            current_affairs=current_bullets,
            question=question,
            system_prompt_tokens=1500,  # Estimated system prompt size
            question_buffer_tokens=200,  # Buffer for question + formatting
            max_total_tokens=32000,     # Conservative limit for fast responses
            output_tokens=2000          # Reserve for model output
        )
    else:
        # Legacy fallback: simple character truncation
        context_trim = (context or "").strip()
        if len(context_trim) > 7200:
            context_trim = context_trim[:7200] + "\n\n[TRUNCATED CONTEXT]"

        current_trim = (current_bullets or "").strip()
        if len(current_trim) > 2400:
            current_trim = current_trim[:2400] + "\n\n[TRUNCATED CURRENT AFFAIRS]"

    # User-level guidance that will be fed as user message
    user_msg = f"""You are a Senior UPSC Mains answer-writer (Geography). Follow IBC strictly and include Mermaid diagrams.

Question: {question}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REFERENCE KNOWLEDGE BASE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**FOUNDATIONAL CONTEXT** (Core concepts, mechanisms, theory):
{context_trim or '[No retrieved context - use your geographical knowledge base]'}
**CURRENT AFFAIRS** (Recent data, examples):
{current_trim or '[No current affairs - use general contemporary examples if needed]'}

⚡ USAGE INSTRUCTIONS:
- Build your answer using FOUNDATIONAL CONTEXT + your general geographical knowledge
- Integrate CURRENT AFFAIRS as supporting evidence and contemporary examples
- Cite specific reports, indices, data points, and case studies from the context
- Maintain factual accuracy - If context is unclear, insufficient, or low-quality: use general knowledge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 ANSWER REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Constraints / Format:
- INTRO: 2–3 lines. Must include either a definition, a data point/report citation, or a recent context or current affair (if applicable).
- BODY: Use sub-headings and bullets. Each bullet <= 18 words.
- BULLET FORMAT (CRITICAL): Every bullet MUST start with a dash (-). Example:
  - **Main point one** with evidence (IPCC 2023) and example.
  - **Main point two** with evidence and example.
  Never write bullets without the dash prefix. Each bullet on its own line.
- TABLE FORMAT (When Applicable):
  - Tables replace bullets entirely for that sub-heading.
  - Max size: 4 rows × 3 columns.
  - Use for:
    - Positive vs negative impacts
    - Advantages vs limitations
    - Comparative geography
    - Category-wise or sector-wise impacts
    - Matrix (two-axis) evaluation
  - Do NOT repeat table content in bullets elsewhere.
  - Table cell content must be brief and point-like.
    - Avoid long sentences; no paragraph-style explanations inside cells.
    - Prefer compact phrases or bullet-style points per cell.

- DIAGRAM: Prefer including ONE Mermaid diagram when the question involves a clear process, mechanism, or causal chain. NEVER place diagram between a sub-heading and its bullets. Place it BEFORE the sub-heading or AFTER all bullets of a section.
- MAP: If the question contains keywords like "distribution", "where", "locate", "belts", "hotspots", "areas", "regional", or explicitly asks about countries/regions, include a map-json block per MAP_GENERATION_RULES (map-json before Body under 'Map/Diagram').
- **TOTAL VISUAL LIMIT**: You can include **at most TWO** visuals in total (spanning Tables, Mermaid diagrams, and Maps). Never include all three.
- WAY FORWARD (Conditional Section – Include Only When Applicable and Relevant): 
 - Include 2–3 bullets, each starting with a dash (-).
 - Each bullet must be actionable, future-oriented, and specific.
 - Keep bullets concise, concrete, and implementable.
- CONCLUSION: 1 para connecting to constitutional artciles, values, or SDG goals, or India’s governance ethos (equity, sustainability, decentralisation) or policy frameworks and where contextually relevant, appropriate technological or adaptive solutions.
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
