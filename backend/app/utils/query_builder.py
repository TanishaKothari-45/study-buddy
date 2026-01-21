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
    
    # 1️⃣ Subject-based tone modifiers
    if subject == "ncert":
        tone = "fundamental NCERT-level conceptual foundations and standard definitions"
    elif subject == "current_affairs":
        tone = "recent developments, policy overlaps, and contemporary geographical trends"
    else:
        tone = "advanced analytical and conceptual synthesis including interdisciplinary links"
    
    # 2️⃣ Base core query construction
    if sub_domain:
        # Micro-level focus + internal sub-links
        base_query = (
            f"Detailed {tone} of {sub_domain} in geography, "
            f"including interlinks with related subtopics and mechanisms within "
            f"the {major_domain or 'same'} domain."
        )
    elif major_domain:
        # Broader domain + cross-domain bridge
        base_query = (
            f"Important {tone} topics under {major_domain} geography "
            f"and their interconnections with its subdomains."
        )
    else:
        # Fully general — multi-domain thematic blending
        base_query = (
            f"Important geography topics across physical, human, and environmental domains, "
            f"focusing on {tone}."
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

