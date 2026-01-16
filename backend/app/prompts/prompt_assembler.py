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
from .subject_overlays.economy import ECONOMY_SUBJECT_OVERLAY
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
    "economy": ECONOMY_SUBJECT_OVERLAY,
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
    subject_key = subject.lower() if subject else ""
    subject_overlay = SUBJECT_MAP.get(subject_key)
    if not subject_overlay:
        logger.warning(f"Subject '{subject}' not found in map. Defaulting to empty overlay.")
        subject_overlay = ""
    else:
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
