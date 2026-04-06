# ============================================================
# BLUEPRINT GS & SUBJECT OVERLAY SUMMARIES
# ============================================================
# Condensed 2-3 line summaries for blueprint (Stage 0) use only.
# Full overlays (with evidence rules, tone, detailed guidance) go to generator.
# Purpose: help blueprint choose appropriate subheadings, decide way_forward,
# and pick visuals — without bloating the blueprint prompt.
# ============================================================

GS_BLUEPRINT_SUMMARIES = {
    "GS1": (
        "GS1: Rewards spatial, temporal, and socio-cultural reasoning. "
        "Subheadings should capture cause → process → impact structure. "
        "Maps strongly preferred for geography; diagrams for processes. "
        "Way forward: embed in conclusion as forward-looking synthesis, not separate section (unless explicitly asked)."
    ),
    "GS2": (
        "GS2: Rewards constitutional grounding, institutional analysis, and governance logic. "
        "Subheadings should cover design, performance, gaps, and reform dimensions. "
        "Way forward is expected in most answers — frame as procedural/institutional reform. "
        "Tables useful for scheme comparisons; maps rare (only IR/spatial governance)."
    ),
    "GS3": (
        "GS3: Rewards data-driven economic/scientific analysis and technology-environment interlinkages. "
        "Subheadings should cover current status, challenges, opportunities, and policy response. "
        "Way forward is expected — should be evidence-based, feasible. "
        "Flowcharts for processes; tables for comparative policy/scheme analysis; maps for distribution."
    ),
    "GS4": (
        "GS4: Rewards ethical reasoning, stakeholder analysis, and value-based arguments. "
        "Subheadings should address ethical dimensions, competing values, and dilemmas. "
        "Way forward: optional — only if explicitly asked or question demands reform. "
        "Visuals rare: tables only for framework comparisons; no maps; no flowcharts unless institutional."
    ),
}

SUBJECT_BLUEPRINT_SUMMARIES = {
    "geography": (
        "Geography: Emphasise spatial patterns, physical processes, and human-environment linkages. "
        "Maps are high-priority. Diagrams for mechanism/process questions."
    ),
    "history": (
        "History: Cover chronological evolution, causes, consequences, and historiographical perspectives. "
        "Timelines useful; maps for battles/trade routes/territorial changes."
    ),
    "social": (
        "Society: Address structural causes, demographic data, constitutional safeguards, and reform pathways. "
        "Mindmaps for multi-factor analysis; tables for comparative evaluation."
    ),
    "constitution": (
        "Constitution/Polity: Ground every subheading in Articles, judicial interpretations, or committee reports. "
        "Diagrams for institutional flows; tables for comparative constitutional mechanisms."
    ),
    "administration": (
        "Governance/Administration: Focus on institutional design, accountability mechanisms, and service delivery gaps. "
        "Flowcharts for policy processes; tables for scheme comparisons."
    ),
    "international relations": (
        "IR: Analyse strategic interests, multilateral frameworks, and India's foreign policy positions. "
        "Maps for geopolitical/regional questions; tables for bilateral/multilateral comparisons."
    ),
    "environment": (
        "Environment: Link ecological science, policy frameworks (national and global), and sustainability challenges. "
        "Maps for biodiversity/disaster spatial distribution; flowcharts for ecological processes."
    ),
    "economic development": (
        "Economy: Use data, indices, and policy analysis. Cover growth, distribution, structural challenges, and reforms. "
        "Tables for sector comparisons; flowcharts for economic mechanisms."
    ),
    "agriculture": (
        "Agriculture: Address productivity, supply chains, farmer welfare, and technology adoption. "
        "Maps for crop distribution; tables for scheme comparisons."
    ),
    "internal security": (
        "Internal Security: Analyse threat dimensions, institutional response, and capacity gaps. "
        "Maps only for insurgency/border/coastal spatial questions; avoid for cyber/institutional."
    ),
    "technology": (
        "Science & Technology: Cover innovation, application to governance/economy, ethical concerns, and India's position. "
        "Flowcharts for technology pipelines; tables for comparative policy analysis."
    ),
    "disaster management": (
        "Disaster Management: Cover risk factors, institutional framework (NDMA/SDMA/NDRF), response, and mitigation. "
        "Maps for disaster-prone spatial distribution; flowcharts for response chain."
    ),
    "foundational values": (
        "Ethics/Values: Address value conflicts, philosophical grounding, and real-world application. "
        "Tables for framework comparisons only; no maps or flowcharts."
    ),
    "social justice": (
        "Social Justice: Frame through constitutional rights, marginalised communities, scheme gaps, and reform. "
        "Tables for policy comparisons; mindmaps for multi-stakeholder impact."
    ),
}


def get_blueprint_gs_hint(gs_paper: str) -> str:
    """Return concise GS paper summary for blueprint user prompt."""
    key = (gs_paper or "").upper().strip().replace(" ", "").replace("-", "")
    return GS_BLUEPRINT_SUMMARIES.get(key, "")


def get_blueprint_subject_hint(subject: str) -> str:
    """Return concise subject summary for blueprint user prompt."""
    if not subject:
        return ""
    s = subject.strip().lower()
    # Direct lookup
    if s in SUBJECT_BLUEPRINT_SUMMARIES:
        return SUBJECT_BLUEPRINT_SUMMARIES[s]
    # Partial match
    for key, val in SUBJECT_BLUEPRINT_SUMMARIES.items():
        if key in s or s in key:
            return val
    return ""
