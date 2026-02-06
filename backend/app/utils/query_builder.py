"""
Query Builder for Adaptive Retrieval
Builds semantically rich, difficulty-aware queries for Pinecone retrieval
"""
from typing import Optional


# Cross-domain relationships mapping for Geography
GEOGRAPHY_RELATED_DOMAINS = {
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

# Cross-domain relationships mapping for History
HISTORY_RELATED_DOMAINS = {
    "Ancient Indian History": ["Indian Heritage and Culture", "Medieval Indian History"],
    "Medieval Indian History": ["Ancient Indian History", "Modern Indian History", "Indian Heritage and Culture"],
    "Modern Indian History": ["Medieval Indian History", "Post-Independence History", "World History"],
    "Post-Independence History": ["Modern Indian History", "World History"],
    "World History": ["Modern Indian History", "Post-Independence History"],
    "Indian Heritage and Culture": ["Ancient Indian History", "Medieval Indian History"]
}

# Combined for backward compatibility
RELATED_DOMAINS = {**GEOGRAPHY_RELATED_DOMAINS, **HISTORY_RELATED_DOMAINS}


# Cross-domain relationships mapping for Economy
ECONOMY_RELATED_DOMAINS = {
    "Basic Economic Concepts": ["Macroeconomics & Policy", "Indian Economy & Development"],
    "Macroeconomics & Policy": ["Basic Economic Concepts", "Banking & Finance", "Taxation & Public Finance"],
    "Indian Economy & Development": ["Basic Economic Concepts", "Contemporary Economic Issues", "External Sector & Global Economy"],
    "Banking & Finance": ["Macroeconomics & Policy", "Indian Economy & Development"],
    "Taxation & Public Finance": ["Macroeconomics & Policy", "Indian Economy & Development"],
    "External Sector & Global Economy": ["Macroeconomics & Policy", "Indian Economy & Development"],
    "Contemporary Economic Issues": ["Macroeconomics & Policy", "Indian Economy & Development"]
}

# Cross-domain relationships mapping for Science & Tech
SCIENCE_TECH_RELATED_DOMAINS = {
    "Fundamental Science Concepts": ["Applied Science & Research", "Biotechnology & Health Tech"],
    "Space & Defence Technology": ["Fundamental Science Concepts", "Information & Communication Tech"],
    "Information & Communication Tech": ["Emerging Technologies", "Space & Defence Technology"],
    "Biotechnology & Health Tech": ["Fundamental Science Concepts", "Applied Science & Research"],
    "Emerging Technologies": ["Information & Communication Tech", "Applied Science & Research"],
    "Applied Science & Research": ["Fundamental Science Concepts", "Emerging Technologies"]
}

# Cross-domain relationships mapping for Environment & Ecology
ENVIRONMENT_ECOLOGY_RELATED_DOMAINS = {
    "Ecology & Ecosystems": ["Biodiversity & Conservation", "Natural Resource Management"],
    "Biodiversity & Conservation": ["Ecology & Ecosystems", "Environment & Ecology"],
    "Pollution & Environmental Issues": ["Climate Change & Global Frameworks", "Environmental Laws & Policies"],
    "Climate Change & Global Frameworks": ["Pollution & Environmental Issues", "Contemporary Environmental Issues"],
    "Environmental Laws & Policies": ["Pollution & Environmental Issues", "Natural Resource Management"],
    "Natural Resource Management": ["Ecology & Ecosystems", "Environmental Laws & Policies"],
    "Contemporary Environmental Issues": ["Climate Change & Global Frameworks", "Biodiversity & Conservation"]
}

# Cross-domain relationships mapping for Polity
POLITY_RELATED_DOMAINS = {
    "Constitutional Framework": ["Judiciary & Legal Institutions", "Union Government"],
    "Union Government": ["State & Local Governance", "Constitutional Framework"],
    "State & Local Governance": ["Union Government", "Governance & Public Policy"],
    "Judiciary & Legal Institutions": ["Constitutional Framework", "Governance & Public Policy"],
    "Electoral Processes & Reforms": ["Constitutional Framework", "Union Government"],
    "Governance & Public Policy": ["Union Government", "Contemporary Governance Issues"],
    "Contemporary Governance Issues": ["Governance & Public Policy", "Constitutional Framework"]
}

# Combined for backward compatibility
RELATED_DOMAINS = {
    **GEOGRAPHY_RELATED_DOMAINS, 
    **HISTORY_RELATED_DOMAINS,
    **ECONOMY_RELATED_DOMAINS,
    **SCIENCE_TECH_RELATED_DOMAINS,
    **ENVIRONMENT_ECOLOGY_RELATED_DOMAINS,
    **POLITY_RELATED_DOMAINS
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
    Supports both Geography and History subjects.
    """
    subject_lower = subject.lower() if subject else "general"
    
    # Detect if this is a History query based on domain names
    history_domains = ["ancient", "medieval", "modern", "post-independence", "world history", "heritage", "culture"]
    is_history = subject_lower == "history" or any(h in (major_domain or "").lower() for h in history_domains)
    
    # 1️⃣ Subject-based tone modifiers
    if subject_lower == "ncert" or subject_lower == "concept":
        tone = "fundamental conceptual foundations"
    elif subject_lower == "current_affairs":
        tone = "recent developments and trends"
    elif is_history:
        tone = "historical analysis, causes, consequences, and significance"
    else:
        # Default for Geography and general
        tone = "analytical conceptual synthesis and interdisciplinary links"
    
    # 2️⃣ Base core query construction
    if is_history:
        # History-specific queries
        if sub_domain:
            base_query = (
                f"Detailed {tone} of {sub_domain}. "
                f"Focus on events, movements, personalities, and socio-economic impact."
            )
        elif major_domain:
            base_query = (
                f"Key {tone} in {major_domain}. "
                f"Include major events, reforms, movements, and their significance."
            )
        else:
            base_query = (
                f"Core Indian and World History concepts across ancient, medieval, and modern periods. "
                f"Focus on {tone}."
            )
    else:
        # Geography queries (original behavior)
        if sub_domain:
            base_query = (
                f"Detailed {tone} of {sub_domain} in geography. "
                f"Focus on mechanisms, processes, and spatial distribution."
            )
        elif major_domain:
            base_query = (
                f"Key {tone} in {major_domain} geography. "
                f"Include major theories, processes, and sub-domain linkages."
            )
        else:
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

