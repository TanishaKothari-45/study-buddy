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
    difficulty: str = "medium"
) -> str:
    """
    Build an adaptive, cross-domain, difficulty-conditioned query text.
    
    Handles:
      1. Domain and sub-domain precision
      2. Cross-domain connections for hard questions
      3. Semantic difficulty tone injection
    
    The goal: embed conceptual intent + cross-domain awareness directly into the query.
    This helps the embedding model understand what type of content we're looking for.
    
    Args:
        major_domain: Major geography domain (e.g., "Physical Geography", "Climatology")
        sub_domain: Sub-domain within major domain (e.g., "Climatology")
        difficulty: Difficulty level ("easy", "medium", "hard")
    
    Returns:
        Semantically rich query string optimized for vector search
    """
    difficulty = difficulty.lower()
    
    # 1️⃣ Difficulty-based tone modifiers
    tone_phrases = {
        "easy": "basic factual understanding and NCERT-level definitions",
        "medium": "conceptual and applied understanding with moderate interlinks",
        "hard": "analytical and interdisciplinary synthesis across related geography domains"
    }
    tone = tone_phrases.get(difficulty, "conceptual understanding")
    
    # 2️⃣ Determine cross-domain relationships for hard questions
    cross_domains = []
    if difficulty == "hard":
        if major_domain:
            # Get related domains for the major domain
            cross_domains = RELATED_DOMAINS.get(major_domain, [])[:2]  # top 2 related
        elif sub_domain:
            # If sub_domain provided, infer its parent and related siblings
            # First check if sub_domain itself is a key
            if sub_domain in RELATED_DOMAINS:
                cross_domains = RELATED_DOMAINS.get(sub_domain, [])[:2]
            else:
                # Search for sub_domain in related lists to find parent domain
                for domain, related in RELATED_DOMAINS.items():
                    if sub_domain in related:
                        cross_domains = [domain] + [r for r in related if r != sub_domain][:1]
                        break
                if not cross_domains:
                    cross_domains = []
    
    # 3️⃣ Base core query construction
    if sub_domain:
        # Micro-level focus + internal sub-links
        # Best for precise, focused retrieval
        base_query = (
            f"Detailed {tone} of {sub_domain} in geography, "
            f"including interlinks with related subtopics and mechanisms within "
            f"the {major_domain or 'same'} domain."
        )
    elif major_domain:
        # Broader domain + cross-domain bridge
        # Good for domain-wide coverage with connections
        base_query = (
            f"Important {tone} topics under {major_domain} geography "
            f"and their interconnections with its subdomains."
        )
    else:
        # Fully general — multi-domain thematic blending
        # Fallback for broad, diverse retrieval
        base_query = (
            f"Important geography topics across physical, human, and environmental domains, "
            f"focusing on {tone}."
        )
    
    # 4️⃣ Add cross-domain awareness if applicable (for hard questions)
    if cross_domains:
        joined = ", ".join(cross_domains)
        domain_ref = major_domain or sub_domain or "geography"
        base_query += (
            f" Also explore analytical relationships between {domain_ref} "
            f"and domains like {joined}."
        )
    
    # 5️⃣ Difficulty-conditioning prefix (inject reasoning style into embedding)
    query_text = f"UPSC {difficulty.upper()} question context: {base_query}"
    
    return query_text


def build_current_affairs_query(
    conceptual_focus: str,
    difficulty: str = "medium"
) -> str:
    """
    Build a semantic query for current affairs retrieval.
    
    Focuses on recent developments, policies, and real-world implications
    related to a specific concept.
    
    Args:
        conceptual_focus: The concept/topic to find current affairs for
        difficulty: Difficulty level (affects query depth)
    
    Returns:
        Query string optimized for current affairs retrieval
    """
    difficulty = difficulty.lower()
    
    # Adjust query depth based on difficulty
    if difficulty == "hard":
        return (
            f"Recent developments, government reports, policies, or events "
            f"related to {conceptual_focus} and its impact on society, economy, or environment. "
            f"Focus on real-world implications, recent data, policy changes, or analytical perspectives "
            f"linked to this concept. Include cross-domain connections and long-term implications."
        )
    else:  # medium
        return (
            f"Recent developments, government reports, policies, or events "
            f"related to {conceptual_focus} and its impact on society, economy, or environment. "
            f"Focus on real-world implications or recent data linked to this concept."
        )

