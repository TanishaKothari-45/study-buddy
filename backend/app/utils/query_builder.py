"""
Query Builder for Adaptive Retrieval
Builds semantically rich, difficulty-aware queries for Pinecone retrieval
"""
from typing import Optional


# Cross-domain relationships mapping (editable and expandable)
RELATED_DOMAINS = {
    "Climatology": ["Oceanography", "Agriculture", "Environmental Geography"],
    "Geomorphology": ["Hydrology", "Soils", "Settlement Geography"],
    "Human Geography": ["Economic Geography", "Cultural Geography", "Climatology"],
    "Indian Geography": ["Economic Geography", "Human Geography"],
    "World Geography": ["Physical Geography", "Environmental Geography"],
    "Economic Geography": ["Agriculture", "Population Geography"],
    "Biogeography": ["Ecology", "Environmental Geography"],
    "Physical Geography": ["Geomorphology", "Climatology", "Hydrology"],
    "Environmental Geography": ["Biogeography", "Climatology", "Ecology"],
    "Agriculture": ["Economic Geography", "Climatology", "Soils"],
    "Population Geography": ["Human Geography", "Economic Geography", "Settlement Geography"],
    "Cultural Geography": ["Human Geography", "Population Geography"],
    "Oceanography": ["Climatology", "Physical Geography", "Environmental Geography"],
    "Hydrology": ["Geomorphology", "Climatology", "Physical Geography"],
    "Soils": ["Geomorphology", "Agriculture", "Biogeography"],
    "Settlement Geography": ["Human Geography", "Economic Geography", "Population Geography"],
    "Ecology": ["Biogeography", "Environmental Geography", "Climatology"]
}


def build_query_text(
    major_domain: Optional[str] = None, 
    sub_domain: Optional[str] = None, 
    difficulty: str = "medium", # Arg kept for signature compatibility
    subject: str = "general"
) -> str:
    """
    Build a semantic, analytical query for Pinecone retrieval.
    Focuses on conceptual depth and interlinks regardless of difficulty.
    """
    subject = subject.lower()
    
    # 1️⃣ Subject-based tone modifiers (Simplified)
    if subject == "ncert":
        tone = "fundamental conceptual foundations"
    elif subject == "current_affairs":
        tone = "recent geographic developments and trends"
    else:
        # Simplified tone for general queries to avoid query dilution
        tone = "analytical conceptual synthesis and interdisciplinary links"
    
    # 2️⃣ Base core query construction
    if sub_domain:
        # Micro-level focus
        base_query = (
            f"Detailed {tone} of {sub_domain} in geography. "
            f"Focus on mechanisms, processes, and spatial distribution."
        )
    elif major_domain:
        # Broader domain focus
        base_query = (
            f"Key {tone} in {major_domain} geography. "
            f"Include major theories, processes, and sub-domain linkages."
        )
    else:
        # Fully general
        base_query = (
            f"Core geography concepts across physical, human, and environmental domains. "
            f"Focus on {tone}."
        )
    
    # Determine related domains for cross-linking
    cross_domains = []
    if major_domain:
        cross_domains = RELATED_DOMAINS.get(major_domain, [])[:2]
    
    if cross_domains:
        joined = ", ".join(cross_domains)
        domain_ref = major_domain or sub_domain or "geography"
        base_query += f" Also explore relationships with {joined}."
    
    return f"UPSC analytical context: {base_query}"


def build_current_affairs_query(
    conceptual_focus: str,
    difficulty: str = "medium"
) -> str:
    """
    Build a semantic query for current affairs retrieval with impact analysis.
    """
    return (
        f"Recent developments, government reports, policies, or events "
        f"related to {conceptual_focus} and its impact on society, economy, or environment. "
        f"Focus on real-world implications, recent data, and analytical perspectives."
    )

