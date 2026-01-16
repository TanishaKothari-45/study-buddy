import logging
from .core.ibc_core_rules import IBC_FORMAT_RULES
from .core.directive_decoder import DIRECTIVE_DECODER
from .core.visual_syntax_rules import (
    MERMAID_DIAGRAM_RULES,
    MAP_GENERATION_RULES,
    GEO_VISUAL_INTELLIGENCE_RULES,
    VISUAL_TIEBREAKER,
)
# Importing legacy rules from shared_mains_prompts until they are fully migrated
from .shared_mains_prompts import (
    BULLET_DISCIPLINE_RULES,
    WORD_COUNT_COMPRESSION_RULES,
    FACTUAL_ACCURACY_RULES,
    DIAGRAM_TOKEN_BUDGET,
    SCORING_RUBRIC,
)

# GS Overlays
from .gs_overlays.gs1_philosophy import GS1_PHILOSOPHY
from .gs_overlays.gs2_philosophy import GS2_PHILOSOPHY
from .gs_overlays.gs3_philosophy import GS3_PHILOSOPHY
from .gs_overlays.gs4_philosophy import GS4_PHILOSOPHY

# Subject Overlays
from .subject_overlays.administration import ADMINISTRATION_SUBJECT_OVERLAY
from .subject_overlays.agriculture import AGRICULTURE_OVERLAY
from .subject_overlays.case_studies import CASE_STUDIES_OVERLAY
from .subject_overlays.constitution import CONSTITUTION_SUBJECT_OVERLAY
from .subject_overlays.disaster import DISASTER_MANAGEMENT_OVERLAY
from .subject_overlays.economic_development import ECONOMIC_DEVELOPMENT_OVERLAY
from .subject_overlays.environment import ENVIRONMENT_SUBJECT_OVERLAY
from .subject_overlays.foundational_values import FOUNDATIONAL_VALUES_OVERLAY
from .subject_overlays.geography import GEOGRAPHY_SUBJECT_OVERLAY
from .subject_overlays.governance_ethics import GOVERNANCE_ETHICS_OVERLAY
from .subject_overlays.history import HISTORY_SUBJECT_OVERLAY
from .subject_overlays.internal_security import INTERNAL_SECURITY_OVERLAY
from .subject_overlays.international_relations import INTERNATIONAL_RELATIONS_SUBJECT_OVERLAY
from .subject_overlays.social import SOCIAL_SUBJECT_OVERLAY
from .subject_overlays.social_justice import SOCIAL_JUSTICE_SUBJECT_OVERLAY
from .subject_overlays.technology import TECHNOLOGY_OVERLAY
from .subject_overlays.thinkers import THINKERS_OVERLAY

logger = logging.getLogger(__name__)

GS_MAP = {
    "GS1": GS1_PHILOSOPHY,
    "GS2": GS2_PHILOSOPHY,
    "GS3": GS3_PHILOSOPHY,
    "GS4": GS4_PHILOSOPHY
}

SUBJECT_MAP = {
    "administration": ADMINISTRATION_SUBJECT_OVERLAY,
    "agriculture": AGRICULTURE_OVERLAY,
    "case studies": CASE_STUDIES_OVERLAY,
    "constitution": CONSTITUTION_SUBJECT_OVERLAY,
    "disaster management": DISASTER_MANAGEMENT_OVERLAY,
    "disaster": DISASTER_MANAGEMENT_OVERLAY,  # Alias
    "economic development": ECONOMIC_DEVELOPMENT_OVERLAY,
    "environment": ENVIRONMENT_SUBJECT_OVERLAY,
    "ethics": GOVERNANCE_ETHICS_OVERLAY, # Note: separate file for foundational values? Using governance_ethics for generic ethics if needed, or maybe foundational? Let's assume Governance/Ethics covers general. Wait, user has 'ethics' mapped to 'ETHICS_SUBJECT_OVERLAY' previously which was missing? 
    # Ah, I see 'governance_ethics.py' is GOVERNANCE_ETHICS_OVERLAY. 
    # In my grep results: app/prompts/subject_overlays/governance_ethics.py:GOVERNANCE_ETHICS_OVERLAY
    # But wait, original code had: from .subject_overlays.ethics import ETHICS_SUBJECT_OVERLAY
    # My grep didn't show 'ethics.py'. Let me re-check the file list.
    # File list: governance_ethics.py, thinkers.py, foundational_values.py, case_studies.py. No 'ethics.py'.
    # Original code was importing from .subject_overlays.ethics but that file likely didn't exist or was renamed?
    # I will map "Ethics" to GOVERNANCE_ETHICS_OVERLAY for now, or check if I missed a file.
    
    "foundational values": FOUNDATIONAL_VALUES_OVERLAY,
    "geography": GEOGRAPHY_SUBJECT_OVERLAY,
    "governance": GOVERNANCE_ETHICS_OVERLAY,
    "governance & ethics": GOVERNANCE_ETHICS_OVERLAY,
    "history": HISTORY_SUBJECT_OVERLAY,
    "internal security": INTERNAL_SECURITY_OVERLAY,
    "international relations": INTERNATIONAL_RELATIONS_SUBJECT_OVERLAY,
    "ir": INTERNATIONAL_RELATIONS_SUBJECT_OVERLAY, # Alias
    "social": SOCIAL_SUBJECT_OVERLAY,
    "society": SOCIAL_SUBJECT_OVERLAY, # Alias
    "social issues": SOCIAL_SUBJECT_OVERLAY, # Alias match for frontend
    "social justice": SOCIAL_JUSTICE_SUBJECT_OVERLAY,
    "technology": TECHNOLOGY_OVERLAY,
    "science & technology": TECHNOLOGY_OVERLAY, # Alias
    "thinkers": THINKERS_OVERLAY
}



# Mapping from Syllabus JSON Primary Domains to Subject Overlays
DOMAIN_TO_SUBJECT_MAP = {
    # GS1
    "Indian_Heritage_and_Culture": "history",
    "Modern_Indian_History": "history",
    "Post_Independence_India": "history",
    "World_History": "history",
    "Indian_Society": "social",
    "Physical_Geography": "geography",
    "World_Geography": "geography",
    
    # GS2
    "Indian_Constitution": "constitution",
    "Federal_Structure": "constitution",
    "Separation_of_Powers": "constitution",
    "Parliament_and_State_Legislatures": "constitution",
    "Executive_and_Judiciary": "constitution",
    "Representation_of_People": "constitution",
    "Constitutional_Bodies": "constitution",
    "Statutory_and_Regulatory_Bodies": "administration",
    "Government_Policies": "administration",
    "Development_Processes": "administration",
    "Social_Justice": "social justice",
    "Governance": "administration",
    "International_Relations": "international relations",
    
    # GS3
    "Indian_Economy": "economic development",
    "Agriculture": "agriculture",
    "Food_Processing": "agriculture",
    "Land_Reforms": "agriculture",
    "Industrial_Policy": "economic development",
    "Infrastructure": "economic development",
    "Investment_Models": "economic development",
    "Science_and_Technology": "technology",
    "Environment_and_Ecology": "environment",
    "Disaster_Management": "disaster management",
    "Internal_Security": "internal security",
    
    # GS4
    "Ethics_and_Human_Interface": "foundational values",
    "Human_Values": "foundational values",
    "Attitude": "foundational values",
    "Aptitude_and_Foundational_Values": "foundational values",
    "Emotional_Intelligence": "foundational values",
    "Moral_Thinkers": "thinkers",
    "Public_Service_Ethics": "governance & ethics",
    "Probity_in_Governance": "governance & ethics",
    "Case_Studies": "case studies"
}

def resolve_subject_overlay(subject_input: str) -> str:
    """
    Resolves the subject overlay content from a subject input string.
    Handles both direct subject names (e.g., 'history') and Syllabus Domains (e.g., 'Modern_Indian_History').
    """
    if not subject_input:
        return ""
        
    s_clean = subject_input.strip()
    
    # 1. Check if it's a Syllabus Domain Key directly
    if s_clean in DOMAIN_TO_SUBJECT_MAP:
        mapped_subject = DOMAIN_TO_SUBJECT_MAP[s_clean]
        logger.debug(f"Mapped Domain '{s_clean}' -> Subject '{mapped_subject}'")
        return SUBJECT_MAP.get(mapped_subject, "")
        
    # 2. Check if it matches a Subject Map key directly (case-insensitive)
    s_lower = s_clean.lower()
    if s_lower in SUBJECT_MAP:
        return SUBJECT_MAP[s_lower]
        
    # 3. Fallback: Check if it's a Syllabus Domain but case didn't match (unlikely if direct from JSON, but safe)
    # or partial matching could go here if needed.
    
    logger.warning(f"Subject/Domain '{subject_input}' not found in any map. Defaulting to empty overlay.")
    return ""


def assemble_mains_prompt(gs_paper: str, subject: str) -> str:
    """
    Dynamically assumes the Mains Answer System Prompt based on GS Paper and Subject.
    
    Args:
        gs_paper: "GS1", "GS2", "GS3", "GS4"
        subject: "Geography", "History", "Polity", etc. (case-insensitive)
    
    Returns:
        Complete system prompt string.
    """
    logger.info(f"Assembling Mains Prompt for GS Paper: {gs_paper}, Subject: {subject}")

    # 1. Fetch GS Overlay
    gs_overlay = GS_MAP.get(gs_paper.upper())
    if not gs_overlay:
        logger.warning(f"GS Paper '{gs_paper}' not found in map. Defaulting to empty overlay.")
        gs_overlay = ""
    else:
        logger.debug(f"Loaded GS Overlay for {gs_paper}")

    # 2. Fetch Subject Overlay
    subject_overlay = resolve_subject_overlay(subject)
    if subject_overlay:
        logger.debug(f"Loaded Subject Overlay for {subject}")
        
    # 3. Assemble Prompt
    # We follow the structure of the original prompt but inject specific overlays
    
    system_prompt = f"""You are an expert UPSC Mains answer writer specializing in {subject if subject else 'General Studies'}.

{IBC_FORMAT_RULES}

**DIRECTIVE HANDLING (MANDATORY)**:
Identify the directive word(s) in the question and structure the answer according to the DIRECTIVE_DECODER below.
The directive determines:
- Depth of analysis
- Balance of arguments
- Need for evaluation or judgement
- Inclusion or exclusion of way forward

{DIRECTIVE_DECODER}

# ============================================================
# CONTEXTUAL OVERLAYS (GS PAPER & SUBJECT)
# ============================================================

{gs_overlay}

{subject_overlay}

# ============================================================
# CORE RULES & SYNTAX
# ============================================================

{BULLET_DISCIPLINE_RULES}

{MERMAID_DIAGRAM_RULES}

{GEO_VISUAL_INTELLIGENCE_RULES}

{VISUAL_TIEBREAKER}

{MAP_GENERATION_RULES}

{DIAGRAM_TOKEN_BUDGET}

{SCORING_RUBRIC}

{WORD_COUNT_COMPRESSION_RULES}

{FACTUAL_ACCURACY_RULES}


**CRITICAL**: 
- Follow ALL rules strictly.
- Diagrams: For word count ≥ 200, include exactly ONE Mermaid diagram. For word count ≤ 150, include only if necessary.
- MAP RULE (mandatory when triggered): If the question matches MAP_TRIGGER_RULES (distribution, locate, belts, hotspots, spatial patterns), the model MUST include a map-json block following MAP_GENERATION_RULES. This is not optional for those questions.
- Maintain IBC structure.
- Write bullets as natural English sentences with strategic source citations where credibility matters.
- Keep diagrams simple and compact (stick to token budget).
"""
    

    logger.info("Prompt assembly completed successfully.")
    return system_prompt

def assemble_improved_answer_prompt(gs_paper: str, subject: str) -> str:
    """
    Dynamically assumes the Improved Answer System Prompt based on GS Paper and Subject.
    
    Args:
        gs_paper: "GS1", "GS2", "GS3", "GS4"
        subject: "Geography", "History", "Polity", etc. (case-insensitive)
    """
    logger.info(f"Assembling Improved Answer Prompt for GS Paper: {gs_paper}, Subject: {subject}")

    # 1. Fetch GS Overlay
    gs_overlay = GS_MAP.get(gs_paper.upper())
    if not gs_overlay:
        gs_overlay = ""

    # 2. Fetch Subject Overlay
    subject_overlay = resolve_subject_overlay(subject)
        
    # 3. Assemble Prompt
    # Base structure matches get_improved_answer_system_prompt but with overlays injected
    
    system_prompt = f"""You are an expert UPSC Mains answer writer and mentor specializing in {subject if subject else 'General Studies'}.

You are given:
1. The original student answer
2. Examiner evaluation feedback, including:
   - Examiner Expectation Blueprint
   - Critical gaps and remedies
   - Directive alignment assessment

Your task is to generate an IMPROVED VERSION of the answer.

========================
CONTEXTUAL OVERLAYS (GS PAPER & SUBJECT)
========================

{gs_overlay}

{subject_overlay}

========================
CORE REWRITE PRINCIPLES
========================
**RULE 0 — PRIORITY HIERARCHY (MANDATORY)**:
When improving the answer, follow this strict priority order:
1. Examiner Expectation Blueprint (what the examiner expects)
2. Directive compliance (depth, balance, judgement)
3. Interpret the directive and depth of answer in line with the GS paper’s thematic philosophy (conceptual, governance-oriented, solution-driven, or ethical).
4. Student’s original ideas, structure, examples, data and phrasing.
5. Strengthen arguments with evidence (reports, examples, data, schemes) where relevant and appropriate to the subject and question.
6. IBC formatting norms

**RULE 1 - PRESERVE STUDENT'S VOICE (MOST IMPORTANT)**:
Build strictly on the student’s original ideas, structure, and examples.
EDIT (rephrase, reorganize, refine, add selectively, remove redundancy) rather than rewrite from scratch.
Introduce new points ONLY where:
- the blueprint explicitly demands them, or
- evaluation identified a concrete gap.

**RULE 2 - DIRECTIVE-FIRST RECONSTRUCTION**:
Structure the improved answer strictly according to the directive identified.
Depth, balance, and judgement must match the directive exactly.

**RULE 3 - TARGETED IMPROVEMENT ONLY**:
- Address gaps explicitly identified in the evaluation feedback.
- Improve structure, logical flow and coherence.
- Fulfil unmet key demands in the Examiner Expectation Blueprint.
- Strengthen weak evidence with examples, data, or reports.
- Add or replace visuals ONLY if evaluation said so or seems necessary.

Do NOT over-enrich beyond UPSC expectations unless it is necessary to satisfy a blueprint demand.

========================
FORMAT & STRUCTURE RULES
========================

{IBC_FORMAT_RULES}
{DIRECTIVE_DECODER}
{BULLET_DISCIPLINE_RULES}
{MERMAID_DIAGRAM_RULES}
{GEO_VISUAL_INTELLIGENCE_RULES}
{MAP_GENERATION_RULES}
{WORD_COUNT_COMPRESSION_RULES}
{FACTUAL_ACCURACY_RULES}

========================
OUTPUT FORMAT
========================

The output must be the **Improved Answer** in markdown format. 
Do not include metadata JSON or preamble. Start directly with the answer title or first section.
"""

    return system_prompt
