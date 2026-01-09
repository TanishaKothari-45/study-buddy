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
from .subject_overlays.geography import GEOGRAPHY_SUBJECT_OVERLAY
from .subject_overlays.modern_history import HISTORY_SUBJECT_OVERLAY
from .subject_overlays.polity import POLITY_SUBJECT_OVERLAY
from .subject_overlays.ethics import ETHICS_SUBJECT_OVERLAY
from .subject_overlays.economy import ECONOMY_SUBJECT_OVERLAY
from .subject_overlays.environment import ENVIRONMENT_SUBJECT_OVERLAY

logger = logging.getLogger(__name__)

GS_MAP = {
    "GS1": GS1_PHILOSOPHY,
    "GS2": GS2_PHILOSOPHY,
    "GS3": GS3_PHILOSOPHY,
    "GS4": GS4_PHILOSOPHY
}

SUBJECT_MAP = {
    "geography": GEOGRAPHY_SUBJECT_OVERLAY,
    "history": HISTORY_SUBJECT_OVERLAY,
    "polity": POLITY_SUBJECT_OVERLAY,
    "ethics": ETHICS_SUBJECT_OVERLAY,
    "economy": ECONOMY_SUBJECT_OVERLAY,
    "environment": ENVIRONMENT_SUBJECT_OVERLAY
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
