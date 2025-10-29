import re
import logging
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)

GEOGRAPHY_TOPICS = {
    "Physical Geography": [
        "Geomorphology", "Climatology", "Oceanography",
        "Biogeography", "Natural Disasters"
    ],
    "Human Geography": [
        "Human Geography", "Economic Geography",
        "Cultural Geography", "Models and Theories"
    ],
    "Indian Geography": [
        "Physiography", "Drainage System", "Climate",
        "Natural Resources", "Agriculture", "Soils"
    ],
    "World Geography": [
        "Continents and Countries", "Major Physical Features",
        "Environmental Challenges"
    ],
    "Map-Based Questions": [
        "Mapping", "Political and Physical Features"
    ]
}

# --- simple rule-based detection --- #
def detect_topic(text: str) -> Dict[str, str]:
    text_lower = text.lower()
    for domain, subtopics in GEOGRAPHY_TOPICS.items():
        for sub in subtopics:
            if re.search(rf"\b{sub.lower().split()[0]}\b", text_lower):
                return {"major_domain": domain, "sub_domain": sub}
    return {"major_domain": None, "sub_domain": None}


def enrich_metadata(chunk_text: str, filename: str, chapter: str, section: str, llm_client: OpenAI) -> Dict[str, Any]:
    """Hybrid enrichment — rules first, then LLM fallback."""
    rule_meta = detect_topic(chunk_text)

    if rule_meta["major_domain"]:
        logger.debug(f"✅ Rule-based match: {rule_meta}")
        summary = " ".join(chunk_text.split()[:40]) + "..."
        difficulty = "Basic" if len(chunk_text.split()) < 120 else "Moderate"
        return {
            "subject": "Geography",
            "major_domain": rule_meta["major_domain"],
            "sub_domain": rule_meta["sub_domain"],
            "difficulty": difficulty,
            "summary": summary,
            "chapter": chapter,
            "section": section,
            "filename": filename,
        }

    # LLM fallback for uncertain chunks
    prompt = f"""
    You are a UPSC Geography classifier.
    Classify the text into:
    1. Major Domain: (choose from Physical Geography, Human Geography, Indian Geography, World Geography, Map-Based Questions)
    2. Sub Domain: Pick the most fitting topic.
    3. Difficulty: Basic / Moderate / Advanced
    4. 1-line Summary

    Text:
    {chunk_text[:1000]}
    """

    try:
        resp = llm_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=150
        )
        content = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"⚠️ LLM enrichment failed: {e}")
        return {
            "subject": "Geography",
            "major_domain": "Unclassified",
            "sub_domain": "Unknown",
            "difficulty": "Unknown",
            "summary": chunk_text[:100],
            "chapter": chapter,
            "section": section,
            "filename": filename
        }

    meta = {
        "subject": "Geography",
        "chapter": chapter,
        "section": section,
        "filename": filename
    }
    for line in content.splitlines():
        if ":" in line:
            k, v = [x.strip() for x in line.split(":", 1)]
            if "major" in k.lower():
                meta["major_domain"] = v
            elif "sub" in k.lower():
                meta["sub_domain"] = v
            elif "difficulty" in k.lower():
                meta["difficulty"] = v
            elif "summary" in k.lower():
                meta["summary"] = v

    return meta
