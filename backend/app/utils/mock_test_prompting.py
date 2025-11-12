"""
UPSC Mock Test Prompt System - Refactored
Clean, hierarchical prompt structure for question generation
"""
from typing import Optional

# ===========================================
# UPSC MOCK TEST PROMPT SYSTEM (Refactored)
# ===========================================

SYSTEM_PROMPT = """You are a Senior UPSC Prelims Question Setter specializing in Geography.

Your mission: Generate **original, authentic UPSC-grade MCQs** that are indistinguishable in phrasing, tone, and reasoning balance from actual UPSC Prelims papers.

Think like an examiner:
- Identify the *core concept* behind each topic and test its application or interlinking.
- Derive statements from factual and analytical relationships, not mere recall.
- Construct plausible distractors that reflect real UPSC traps.
- Use the PYQ examples only to learn phrasing and structure — never copy content.

Each question must reflect *how a real UPSC examiner thinks while setting traps and testing depth of understanding.*
"""

# ----------------------------------------------------------------------
# COGNITIVE FRAMEWORK – Universal generation rules for all difficulties
# ----------------------------------------------------------------------

COGNITIVE_FRAMEWORK = """COGNITIVE FRAMEWORK (Apply to all difficulties)

1. Concept Focus
   - Base each question on ONE clear concept or mechanism per chunk group.

2. Context Variation
   - Vary spatial (India/global), temporal (historic/current), and domain (physical/human/environmental) perspectives.

3. Question Type Diversity
   - Include these formats across a test: Multi-statement, Assertion–Reason, Match-the-Pair, Concept Definition, and one Current-Affairs-Linked.

4. Option Engineering
   - Provide 3–4 plausible distractors.
   - Use authentic UPSC phrasing: "1 and 2 only", "All of the above", "Which of the following is/are NOT correct".

5. Explanation Discipline
   - Give concise explanations for why the correct option is right and why others are wrong, using the Vision IAS tone."""

# ----------------------------------------------------------------------
# DIFFICULTY GUIDE – concise cognitive modifiers
# ----------------------------------------------------------------------

DIFFICULTY_GUIDE = {
    "easy": """EASY MODE

• One factual NCERT/standard concept.
• Direct recall or definition-based question.
• Two options clearly wrong; no traps or "NOT correct".
• No current-affair linkage.
• Short one-line factual explanation.""",

    "medium": """MEDIUM MODE

• Blend two related subtopics (e.g., Monsoon + Agriculture).
• May include one "NOT correct" or Assertion–Reason question.
• Use elimination reasoning; moderate option confusion.
• Explanation: 2 concise lines covering concept and reasoning.""",

    "hard": """HARD MODE

• Interlink at least two domains (Physical + Human Geography, or Static + Current).
• Include at least one statement combining static and current info.
• Prefer "How many of the above" or Assertion–Reason format.
• Insert subtle factual traps ("only", "always", reversed cause–effect).
• Explanation must detail the reasoning path for elimination.
• Every question must reveal examiner intent — to test application, correlation, or elimination skill."""
}

# ----------------------------------------------------------------------
# PROMPT ASSEMBLER
# ----------------------------------------------------------------------

def assemble_upsc_prompt(
    topic: str,
    difficulty: str,
    num_questions: int,
    retrieved_static_text: str,
    retrieved_current_affairs: str = "",
    pyq_examples: str = ""
) -> str:
    """
    Build the hierarchical prompt for UPSC question generation.
    
    Args:
        topic: Topic/subject for the questions
        difficulty: "easy", "medium", or "hard"
        num_questions: Number of questions to generate
        retrieved_static_text: Static material context (NCERT, Vision notes)
        retrieved_current_affairs: Current affairs context (if any)
        pyq_examples: PYQ style examples for reference
        
    Returns:
        Complete prompt string ready for LLM
    """
    difficulty_text = DIFFICULTY_GUIDE.get(difficulty.lower(), DIFFICULTY_GUIDE["medium"])
    
    # Trim contexts for token safety
    # Target: 70% content, 30% style learning
    # Content: ~4200 chars (70% of 6000), Style: ~1800 chars (30% of 6000)
    # Note: retrieved_static_text now contains optimized mix of static + current affairs
    content_text_trimmed = retrieved_static_text[:4200] if retrieved_static_text else "No content material available."
    # Style learning examples (PYQ chunks + patterns + feedback) - 30% of prompt
    pyq_examples_trimmed = pyq_examples[:1800] if pyq_examples else "No style learning examples available."
    
    prompt = f"""SYSTEM:

{SYSTEM_PROMPT}

---

FRAMEWORK:

{COGNITIVE_FRAMEWORK}

---

DIFFICULTY MODE:

{difficulty_text}

---

CONTEXT SOURCES (Factual Knowledge - 70%):

Study Materials (NCERT, Vision Notes, Current Affairs):

{content_text_trimmed}

---

PYQ STYLE EXAMPLES (Style Learning - 30%):

{pyq_examples_trimmed}

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
   - Format: "Consider the following statements regarding [topic]:\n1. [First statement]\n2. [Second statement]\n3. [Third statement]\n\nWhich of the following is correct?"
   - DO NOT put statements in a separate field - they must be part of the question text.

2. For Assertion-Reason questions:
   - Format: "Assertion (A): [Assertion text]\nReason (R): [Reason text]\n\nWhich of the following is correct?"
   - Both Assertion and Reason MUST be in the question field.

3. For Match-the-Pair questions:
   - Format: "Match the following:\nList I\n1. [Item 1]\n2. [Item 2]\n3. [Item 3]\n\nList II\n(a) [Match 1]\n(b) [Match 2]\n(c) [Match 3]\n\nSelect the correct answer:"
   - All pairs and lists MUST be in the question field.

IMPORTANT: The "options" field must be a JSON array of strings, not a dictionary.
Example: "options": ["(a) Option 1", "(b) Option 2", "(c) Option 3", "(d) Option 4"]
NOT: "options": {{"A": "Option 1", "B": "Option 2"}}"""
    
    return prompt.strip()

