"""
UPSC Mock Test Prompt System - Refactored
Clean, hierarchical prompt structure for question generation
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# Path to the patterns configuration
# study-buddy/backend/app/utils/mock_test_prompting.py -> study-buddy/
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PATTERNS_PATH = BASE_DIR / "config" / "geography_prelims_pyq_patterns.json"

def load_pyq_patterns() -> Dict[str, Any]:
    """Load the enhanced UPSC Prelims patterns from JSON."""
    try:
        if PATTERNS_PATH.exists():
            with open(PATTERNS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading patterns: {e}")
    return {"patterns": []}

PYQ_PATTERNS_DATA = load_pyq_patterns()

def format_patterns_for_prompt() -> str:
    """Format the patterns JSON into a readable string for the prompt."""
    if not PYQ_PATTERNS_DATA.get("patterns"):
        return "No specific patterns available."
    
    formatted = "UPSC QUESTION PATTERN EXAMPLES & LOGIC:\n\n"
    for p in PYQ_PATTERNS_DATA["patterns"]:
        formatted += f"Pattern {p['id']}: {p['title']}\n"
        formatted += f"Logic: {p['explanation']}\n"
        if "examples" in p:
            for ex in p["examples"][:1]:  # Just one example per pattern for the framework
                formatted += f"Sample Trap: {ex.get('pattern_notes', 'N/A')}\n"
        formatted += "---\n"
    return formatted

# ===========================================
# UPSC MOCK TEST PROMPT SYSTEM (Refactored)
# ===========================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PATTERNS_PATH = BASE_DIR / "config" / "geography_prelims_pyq_patterns.json"

def load_pyq_patterns() -> Dict[str, Any]:
    """Load the enhanced UPSC Prelims patterns from JSON."""
    try:
        if PATTERNS_PATH.exists():
            with open(PATTERNS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading patterns: {e}")
    return {"patterns": []}

PYQ_PATTERNS_DATA = load_pyq_patterns()

def format_patterns_for_prompt() -> str:
    """Format the patterns JSON into a readable string for the prompt."""
    patterns = PYQ_PATTERNS_DATA.get("patterns", [])
    if not patterns:
        return ""
    
    formatted = "### Additional UPSC Question Patterns:\n"
    for p in patterns:
        formatted += f"- **{p.get('title', 'Pattern')}**: {p.get('explanation', '')}\n"
    return formatted

SYSTEM_PROMPT = """You are an expert UPSC Prelims Geography question designer with deep examiner-level understanding of the UPSC CSE exam pattern, especially for Geography sections.

Your role is to generate multiple-choice questions that reflect how UPSC examiners think, reason, and trap candidates — privileging application, conceptual linkage, spatial and map logic, and disciplined elimination reasoning.

Your questions must be rooted in static geographic concepts, with current contextual elements used only to test concept application, not to ask superficial news facts.

You must produce questions in authentic UPSC formats including multi-statement reasoning, assertion–reasoning, match-pairs, map/spatial logic, and integrated conceptual themes.

Craft distractors that are plausible, conceptually related, and require reasoning to eliminate. Avoid trivial or purely definitional options unless tightly linked with deeper understanding.

You should always assume UPSC-like language, precision, and structure in all questions and explanations.
"""

# ----------------------------------------------------------------------
# COGNITIVE FRAMEWORK – Universal generation rules for all difficulties
# ----------------------------------------------------------------------

COGNITIVE_FRAMEWORK = """COGNITIVE FRAMEWORK

PATTERN DEFINITIONS & QUESTION DESIGN RULES (GEOGRAPHY UP-SC CSE PRELIMS)

You must generate UPSC-level geography MCQs that reflect how questions are designed in actual UPSC Prelims papers — not simple recall items, but applied, analytical, spatial, and logically linked items.

The patterns below define *what each type tests*, *how linkages must work*, and *how distractors must be constructed*. Follow these strictly.

---

1) CONCEPT DEFINITION / CORE GEOGRAPHIC CONCEPT MCQ

Purpose:
- Tests precise understanding of key geography concepts (physical processes, spatial principles, interactions).
- Not a trivial definition recall; distractors must be conceptually plausible and target common misunderstandings.

Expected Features:
- Stem asks for the *best description/definition* of a concept.
- Distractors reflect close concepts that candidates often confuse.
- Avoid completely irrelevant or obviously wrong options.

Example Traps to Use:
- Confusion between forces (e.g., Coriolis vs pressure gradient)
- Related but distinct terms (continental drift vs plate tectonics)

Static vs Current:
- Static concept at core. Current context may *illustrate* concept but not be tested as isolated knowledge.

Distractor Logic:
- Subtle differences (e.g., directionality, mechanism) that require reasoning.

---

2) MULTI-STATEMENT EVALUATION MCQs

Purpose:
- Tests cumulative understanding of a concept via several linked statements.
- Most common pattern in geography prelims, often with 3–4 statements.

Expected Features:
- Use “Consider the following statements…” followed by numbered items.
- Statements must be independent but conceptually related.
- Statements should test the application of static concepts.
- Options query which are correct, requiring the solver to reason through each.

Linkage Rules:
- All statements should stem from a **common conceptual theme** (e.g., monsoon mechanism, ocean current behavior).
- Some statements should be *plausible but subtly wrong* to enforce elimination reasoning.

Distractor Logic:
- Small factual/qualifier errors: direction, extent, conditions.
- Avoid trivial falsehoods; make every statement *appear plausible on first glance*.

Static vs Current:
- Static concepts govern correctness. Current context can be used to *frame or modify a statement*, but correctness must still derive from core geography logic.

---

3) MATCH-THE-PAIR / LIST MCQs

Purpose:
- Tests precise mapping of related items (rivers → basins, mountains → continents, climate types → characteristics).

Expected Features:
- Two columns with items requiring accurate one-to-one association.
- A mix of correct and incorrect pairings, where incorrect ones are *plausible but wrong*.

Linkage Rules:
- Each item pair must be verifiable through geography knowledge; traps should be near matches.

Distractor Logic:
- Similar names or regions (e.g., similar basin names, nearby mountain ranges) are good distractor sources.

Static vs Current:
- Largely static, factual spatial mapping.

---

4) ASSERTION–REASON TYPE

Purpose:
- Tests ability to evaluate *cause–effect or explanatory link* between two statements.

Expected Features:
- Two statements (Assertion and Reason).
- Options:
  (a) Both true, R explains A  
  (b) Both true, R does not explain A  
  (c) A true, R false  
  (d) A false, R true

Linkage Rules:
- Reason must link conceptually to assertion to be a correct explanation.
- Distractors test partial truth vs causal linkage.

Distractor Logic:
- R may be true but not explanatory.
- One or both statements may be subtly off.

Static vs Current:
- Primarily static logic; current context only to *validate or contextualize* a cause–effect.

---

5) FACT-BASED / DIRECT MCQs

Purpose:
- Tests accurate recall of geographic facts where high-level reasoning may not be required, but distractors must remain plausible.

Expected Features:
- One-question stems on geographic fact (rivers, latitudes, physiography).
- Distractors should be *close in parameters* (e.g., similar latitude or river location).

Distractor Logic:
- Near misses (latitude slightly off), similar but incorrect geographic features.

Static vs Current:
- Static.

---

6) MAP / LOCATION / SPATIAL REASONING

Purpose:
- Tests spatial understanding — relative positions, closest/furthest from a latitude/longitude, ordering.

Expected Features:
- Stem makes reference to spatial relationships, not just names.
- Distractors should be *geo-spatially adjacent or similar*.

Linkage Rules:
- Spatial reasoning must tie back to coordinate or proximity logic.

Distractor Logic:
- Nearby but incorrect positional alternatives.

Static vs Current:
- Static spatial relationships.

---

7) CONCEPT + CURRENT CONTEXT (APPLIED GEOGRAPHY)

Purpose:
- Tests *static geography principles* in the light of *recent contextual observations or trends*.
- Current context should serve as a testing *lens* for geography concepts, not trivia.
- Current context should be applied part of the static concept.

Expected Features:
- One or more statements include a current context premise.
- Correctness still hinges on *core geography concept application*.

Linkage Rules:
- Use current context to *modify or illustrate* static concepts (e.g., anomalous rainfall patterns, sea surface temperature trends).
- Current info must *alter or test* conceptual interpretation.

Distractor Logic:
- Current context can introduce confusion if misinterpreted; use that as trap logic, but still tie back to static truth.

---

GENERAL RULES FOR LINKAGE & DISTRACTOR DESIGN

1. Reasoning and Elimination:
- Questions should be structured so candidates apply elimination reasoning, not pure recall.  
- In multi-statement and assertion–reasoning items, logical evaluation of each option is required.

2. Static + Current Integration:
- *Static geography knowledge forms the core truth*.  
- *Current affairs can be used to test or extend this truth but should not stand alone.*  
- Avoid superficial news questions that do not *deepen the conceptual test*.

3. Plausible Distractors — Hallmarks of UPSC:
- Distractors should exploit:
  • Common misconceptions
  • Qualifier traps (“only”, “always”, “never”)
  • Spatial or causal confusion
  • Near-true factual variants

4. Language and Tone:
- Use formal, precise, concise language, similar to UPSC question papers.  
- Avoid unnecessary verbosity.

5. Pattern Diversity in a Single Mock:
- A balanced mock should include:
  • At least two multi-statement questions
  • One assertion–reason
  • One match-the-pair (if possible)
  • One applied concept link with current context
  • A mix of fact- and spatial-based items

6. Explanation Requirement:
- Provide concise justification for each correct answer and brief reasons why other options are incorrect.
- Explanations must reflect *UPSC-like reasoning*, not generic clarification.

---
"""

# Integrate patterns into the framework
COGNITIVE_FRAMEWORK += "\n" + format_patterns_for_prompt()

# ----------------------------------------------------------------------
# PROMPT ASSEMBLER
# ----------------------------------------------------------------------

def assemble_upsc_prompt(
    topic: str,
    num_questions: int,
    retrieved_static_text: str,
    retrieved_current_affairs: str = "",
    pyq_chunks: List[Dict] = None,
    search_queries: List[Dict] = None
) -> str:
    """
    Build the hierarchical prompt for UPSC question generation.
    
    Args:
        topic: Topic/subject for the questions
        num_questions: Number of questions to generate
        retrieved_static_text: Static material context (NCERT, Vision notes)
        retrieved_current_affairs: Current affairs context (if any)
        pyq_chunks: List of PYQ chunks for style learning
        search_queries: Optional list of Google Search queries (q, recency)
        
    Returns:
        Complete prompt string ready for LLM
    """
    # Difficulty-based modifiers are now handled via subject-based queries and the framework itself
    
    # Pass full contexts without trimming (enforced by bucket selection logic)
    content_text = retrieved_static_text if retrieved_static_text else "No content material available."
    
    # Format search queries if provided
    research_instruction = ""
    if search_queries:
        research_instruction = """### STEP 1: CONDUCT LIVE RESEARCH (CRITICAL FOR CURRENT AFFAIRS)

You MUST use your Google Search tool to research the following queries. These queries target the LATEST (2024-2026) developments, policies, and data that will make your questions contemporary and UPSC-relevant.

**SEARCH QUERIES TO EXECUTE:**
"""
        for i, sq in enumerate(search_queries):
            research_instruction += f"{i+1}. {sq['q']}\n"
        
        research_instruction += """
**AFTER SEARCHING**, synthesize your findings into factual 'Current Affair Bullets' (30-40 words each). This act as CURRENT AFFAIRS context for your questions.

### STEP 2: INTEGRATE CURRENT AFFAIRS WITH STATIC CONTENT

**IMPORTANT**: You MUST create questions that integrate BOTH for UPSC style questions:
1. **Static Knowledge** - Geography concepts, processes, theories 
2. **Current Affairs** (from your search results) - Recent events, policies, data, government initiatives that are applied to the static content

**INTEGRATION EXAMPLES:**
- "In light of India's recent National Monsoon Mission findings (2024)..." + static monsoon concept
- "The 2025 IPCC report highlighted..." + static climate change geography
- "Considering the recent Himalayan glacial lake outburst..." + static glacier dynamics

At least 40% of your questions MUST link current affairs with static concepts. This is CRITICAL for UPSC-style question quality.

"""
    
    # Format PYQ chunks for style learning
    pyq_examples_text = ""
    if pyq_chunks:
        for i, chunk in enumerate(pyq_chunks):
            content = chunk.get("content", "").strip()
            if content:
                pyq_examples_text += f"Example {i+1}:\n{content}\n---\n"
    
    if not pyq_examples_text:
        pyq_examples_text = "No style learning examples available."
    
    prompt = f"""SYSTEM:

{SYSTEM_PROMPT}

---

FRAMEWORK:

{COGNITIVE_FRAMEWORK}


{research_instruction}

CONTEXT SOURCES (Factual Knowledge - 70%):

{content_text}

---

PYQ STYLE EXAMPLES (Style Learning):

{pyq_examples_text}

---

TASK:

Generate {num_questions} UPSC-style MCQs on the topic: {topic}.

Each question must follow this structure:

{{
  "questions": [
    {{
      "question": "...",
      "options": ["(a)...", "(b)...", "(c)...", "(d)..."],
      "correct_answer": "A" | "B" | "C" | "D",
      "explanation": "...",
      "source": {{"topic": "...", "sub_domain": "..."}}
    }},
    ...
  ]
}}

Ensure:

• 4–5 distinct question types across the test.
• 1–2 questions combine static + current info (if current affairs available).
• Avoid keyword or fact repetition.
• Tone and conciseness must match authentic UPSC.
• Each explanation justifies correct and incorrect options.

CRITICAL FORMATTING RULES:

1. For Multi-Statement questions ("Consider the following statements"):
   - The "question" field MUST include ALL statements WITHIN it.
   - Format: "Consider the following statements regarding [topic]:\\n1. [First statement]\\n2. [Second statement]\\n3. [Third statement]\\n\\nWhich of the following is correct?"
   - DO NOT put statements in a separate field - they must be part of the question text.

2. For Assertion-Reason questions:
   - Format: "Assertion (A): [Assertion text]\\nReason (R): [Reason text]\\n\\nWhich of the following is correct?"
   - Both Assertion and Reason MUST be in the question field.

3. For Match-the-Pair questions:
   - Format: "Match the following:\\nList I\\n1. [Item 1]\\n2. [Item 2]\\n3. [Item 3]\\n\\nList II\\n(a) [Match 1]\\n(b) [Match 2]\\n(c) [Match 3]\\n\\nSelect the correct answer:"
   - All pairs and lists MUST be in the question field.

IMPORTANT: The "options" field must be a JSON array of strings, not a dictionary.
Example: "options": ["(a) Option 1", "(b) Option 2", "(c) Option 3", "(d) Option 4"]
NOT: "options": {{"A": "Option 1", "B": "Option 2"}}

**CRITICAL JSON OUTPUT REQUIREMENT:**
You MUST return ONLY valid JSON with NO markdown formatting, NO code blocks, NO explanatory text.
Start your response with {{ and end with }}.
Do NOT wrap the JSON in ```json or any other markers."""
    
    return prompt.strip()
