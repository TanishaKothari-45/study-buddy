import re
import json
import logging
import time
from typing import Dict, Any, List, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# UPSC Geography taxonomy
GEOGRAPHY_DOMAINS = {
    "Physical Geography": [
        "Geomorphology",
        "Climatology",
        "Oceanography",
        "Biogeography",
        "Natural Disasters"
    ],
    "Human Geography": [
        "Economic Geography",
        "Cultural Geography",
        "Models and Theories",
        "Population Geography",
        "Settlements",
        "Migration"
    ],
    "Indian Geography": [
        "Indian Physiography",
        "Indian Drainage System",
        "Indian Climate",
        "Indian Soils",
        "Indian Agriculture",
        "Indian Natural Resources",
        "Indian Industries",
        "Transport and Communication",
        "Regional Planning"
    ],
    "World Geography": [
        "Continents and Countries",
        "Major Physical Features",
        "Environmental Challenges",
        "Political and Physical Features",
        "Mapping and Cartography"
    ]
}

# UPSC History taxonomy (Simplified from user input)
HISTORY_DOMAINS = {
    "Indian Heritage and Culture": [
        "Art Forms",
        "Architecture",
        "Literature & Language Traditions",
        "Religious & Philosophical Streams",
        "Performing & Folk Traditions"
    ],
    "Ancient Indian History": [
        "Prehistoric Cultures",
        "Indus Valley Civilization",
        "Vedic Period",
        "Mahajanapadas & Second Urbanisation",
        "Major Empires (Mauryas, Guptas)",
        "Religion, Philosophy & Society",
        "Economy & Trade",
        "Science & Technology / Education"
    ],
    "Medieval Indian History": [
        "Early Medieval Polities",
        "Delhi Sultanate",
        "Mughal Empire",
        "Regional Kingdoms",
        "Socio-Cultural Movements (Bhakti & Sufi)",
        "Architecture & Art",
        "Economic and Agrarian Trends"
    ],
    "Modern Indian History": [
        "European Penetration & Colonial Expansion",
        "Administrative & Economic Policies",
        "Social & Religious Reform Movements",
        "Revolt of 1857",
        "Freedom Movement (1885-1947)",
        "Partition & Independence"
    ],
    "Post-Independence History": [
        "Consolidation & Reorganization of States",
        "Domestic Political Developments",
        "Economic & Social Transformations",
        "Foreign Policy & International Relations",
        "Challenges of nation-building"
    ],
    "World History": [
        "Industrial Revolution",
        "French Revolution & Napoleonic Era",
        "Nationalism in Europe",
        "Colonialism & Imperialism",
        "World Wars I & II",
        "Russian Revolution & Communist Ideology",
        "Inter-War Period & Great Depression",
        "Cold War & Decolonisation",
        "Post-Cold War World"
    ]
}

SUBJECT_DOMAINS = {
    "Geography": GEOGRAPHY_DOMAINS,
    "History": HISTORY_DOMAINS
}

# Legacy GEOGRAPHY_TOPICS for backward compatibility
GEOGRAPHY_TOPICS = GEOGRAPHY_DOMAINS.copy()
GEOGRAPHY_TOPICS["Map-Based Questions"] = [
    "Mapping", "Political and Physical Features"
]

def get_system_prompt(subject: str = "Unclassified", provided_major_domain: str = "Unclassified") -> str:
    """Generate system prompt for specified subject."""
    domains = SUBJECT_DOMAINS.get(subject, GEOGRAPHY_DOMAINS)
    
    # Instructions for prioritizing the provided major domain
    priority_instruction = ""
    if provided_major_domain != "Unclassified":
        priority_instruction = f"CRITICAL: The user has specified '{provided_major_domain}' as the major domain for THIS batch of chunks. Unless a chunk is flagrantly unrelated, use '{provided_major_domain}' specifically."

    return f"""
You are a UPSC {subject} domain expert.

Classify each provided passage according to the following hierarchy:

• major_domain  → one of: {list(domains.keys())}

• sub_domain    → choose only from the valid sub-domains under that major domain:

{json.dumps(domains, indent=2)}

• micro_topic   → the main concept or phenomenon described (free-form, 1-4 words)

• sub_topics    → optional list of smaller ideas/examples if multiple appear (array of strings)

{priority_instruction}

Guidelines:
- Use exact names from the lists for major_domain and sub_domain.
- Infer micro_topic and sub_topics contextually from the passage.
- Keep micro_topic concise (1–4 words).
- If unsure about micro_topic, use "General Concepts".
- Return pure JSON array — one object per passage, no explanations.

Example output format:
[
  {{"major_domain": "{list(domains.keys())[0]}", "sub_domain": "{domains[list(domains.keys())[0]][0]}", "micro_topic": "Example Concept", "sub_topics": ["Specific 1", "Specific 2"]}}
]
"""

# Configuration
CLASSIFICATION_BATCH_SIZE = 20
MAX_RETRIES = 1

# --- source type detection --- #
def detect_source_type(filename: str) -> Dict[str, str]:
    """
    Determine source_type and source_subtype from filename.
    
    Returns dict: {"source_type": str, "source_subtype": str or None}
    
    Priority: PYQ > NCERT > Current Affairs > Concept (topic)
    
    Uses word-boundary matching to avoid false positives (e.g., "ca" in "Practical").
    """
    if not filename:
        return {"source_type": "concept", "source_subtype": "topic"}
    
    filename_lower = filename.lower()
    
    # PYQ patterns - check first
    pyq_patterns = [
        "geography-pyq topic wise", "geography_questions_in_upsc_prelims",
        "pyq", "prelims", "previous year"
    ]
    
    # NCERT patterns - check before current affairs (more specific)
    ncert_patterns = ["ncert"]
    
    # Current Affairs patterns - use word boundaries to avoid false matches
    # e.g., "ca" should match "ca" or "current_affairs" but not "Practical"
    import re
    
    # Check PYQ first
    # Check PYQ first
    for pattern in pyq_patterns:
        if pattern in filename_lower:
            # Determine subtype
            if "mains" in filename_lower:
                subtype = "mains"
            elif "prelims" in filename_lower:
                subtype = "prelims"
            else:
                # Default to prelims if generic (or you can use "prelims" as safe default for legacy files)
                subtype = "prelims"
            return {"source_type": "pyq", "source_subtype": subtype}
    
    # Check NCERT second (before current affairs to avoid false positives)
    for pattern in ncert_patterns:
        if pattern in filename_lower:
            return {"source_type": "concept", "source_subtype": "ncert"}
    
    # Check Current Affairs - handle underscores, hyphens, and spaces
    # Normalize filename: replace underscores and hyphens with spaces for matching
    normalized = re.sub(r'[_\-\s]+', ' ', filename_lower)
    
    # Check for "current affair" or "current affairs" (handles all separators)
    if re.search(r'\bcurrent\s+affair', normalized):
        return {"source_type": "current_affairs", "source_subtype": None}
    
    # Check for "vision monthly" or "vision magazine" or "monthly magazine"
    if re.search(r'\bvision\s+(monthly|magazine)', normalized) or \
       re.search(r'\bmonthly\s+magazine', normalized):
        return {"source_type": "current_affairs", "source_subtype": None}
    
    # Check single words with word boundaries (avoid substring matches)
    # Only check if they appear together or in context
    current_words = ["current", "affair", "vision", "monthly", "magazine"]
    # If we find "current" AND "affair" (in any order), it's current affairs
    if re.search(r'\bcurrent\b', normalized) and re.search(r'\baffair\b', normalized):
        return {"source_type": "current_affairs", "source_subtype": None}
    
    # If we find "vision" AND ("monthly" OR "magazine"), it's current affairs
    if re.search(r'\bvision\b', normalized) and \
       (re.search(r'\bmonthly\b', normalized) or re.search(r'\bmagazine\b', normalized)):
        return {"source_type": "current_affairs", "source_subtype": None}
    
    # Default fallback
    return {"source_type": "concept", "source_subtype": "topic"}

# --- simple rule-based detection (fallback) --- #
def detect_topic(text: str, subject: str = "Geography") -> Dict[str, str]:
    """Rule-based fallback for domain detection"""
    text_lower = text.lower()
    domains = SUBJECT_DOMAINS.get(subject, GEOGRAPHY_DOMAINS)
    
    for domain, subtopics in domains.items():
        for sub in subtopics:
            # Match first word of sub-topic as simplified rule
            match_word = sub.lower().split()[0]
            if len(match_word) > 3 and re.search(rf"\b{match_word}\b", text_lower):
                return {"major_domain": domain, "sub_domain": sub}
    return {"major_domain": None, "sub_domain": None}


def safe_json_parse(text: str) -> List[Dict[str, Any]]:
    """Attempt to parse model output into JSON list safely."""
    text = text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    
    # Fallback: try to extract multiple JSON objects manually
    objects = []
    for block in text.split("\n"):
        block = block.strip()
        if not block.startswith("{"):
            continue
        try:
            obj = json.loads(block)
            objects.append(obj)
        except Exception:
            continue
    
    return objects


from .langsmith_tracer import trace_llm

@trace_llm("metadata_enrichment_batch")
def enrich_batch(batch: List[Dict[str, Any]], client: OpenAI, subject: str = "Unclassified", provided_major_domain: str = "Unclassified") -> List[Dict[str, Any]]:
    """Send a batch of chunks to GPT and return enriched classifications."""
    # Prepare combined input
    combined = "\n\n".join([
        f"CHUNK {i+1}:\n{chunk['content'][:1800]}"
        for i, chunk in enumerate(batch)
    ])
    
    messages = [
        {"role": "system", "content": get_system_prompt(subject, provided_major_domain)},
        {"role": "user", "content": combined}
    ]
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.2,
                max_tokens=500  # Enough for batch of 5 classifications
            )
            output = response.choices[0].message.content
            parsed = safe_json_parse(output)
            
            if not parsed or len(parsed) == 0:
                raise ValueError("Empty or unparsable JSON")
            
            # Ensure we have enough results for the batch
            if len(parsed) < len(batch):
                logger.warning(f"⚠️ Got {len(parsed)} results for {len(batch)} chunks, padding with defaults")
                while len(parsed) < len(batch):
                    parsed.append({})
            
            return parsed[:len(batch)]  # Return only as many as we need
            
        except Exception as e:
            logger.warning(f"⚠️ Retry {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    
    logger.error("❌ Giving up on batch after retries, using fallback")
    # Return empty dicts for fallback
    return [{} for _ in batch]


def classify_chunks_batch(chunks: List[Dict[str, Any]], client: OpenAI, subject: str = "Unclassified", provided_major_domain: str = "Unclassified", source_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Classify all chunks in batches and merge results into metadata.
    
    Args:
        chunks: List of dicts with 'content' and 'metadata' keys
        client: OpenAI client instance
        subject: The subject domain (History, Geography, etc.)
        provided_major_domain: User-selected major domain hint
        source_type: User-selected source type (ncert, concept, current_affairs). If None, auto-detect from filename.
    
    Returns:
        List of enriched chunks with major_domain, sub_domain, micro_topic, sub_topics added
    """
    enriched = []
    domains = SUBJECT_DOMAINS.get(subject, GEOGRAPHY_DOMAINS)
    
    for i in range(0, len(chunks), CLASSIFICATION_BATCH_SIZE):
        batch = chunks[i:i + CLASSIFICATION_BATCH_SIZE]
        batch_num = (i // CLASSIFICATION_BATCH_SIZE) + 1
        total_batches = (len(chunks) + CLASSIFICATION_BATCH_SIZE - 1) // CLASSIFICATION_BATCH_SIZE
        
        logger.info(f"   Processing classification batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        
        results = enrich_batch(batch, client, subject=subject, provided_major_domain=provided_major_domain)
        
        for j, chunk in enumerate(batch):
            classification = results[j] if j < len(results) else {}
            meta = chunk["metadata"].copy()
            
            # Use provided source_type if available, otherwise detect from filename
            filename = meta.get("filename", "")
            logger.info(f"   📌 source_type parameter received: '{source_type}' (type: {type(source_type).__name__})")
            if source_type:
                # User provided source_type directly - use as-is
                source_info = {"source_type": source_type, "source_subtype": source_type}
                logger.info(f"   ✅ Using user-provided source_type: {source_info}")
            else:
                # Auto-detect from filename (legacy behavior)
                source_info = detect_source_type(filename)
                logger.info(f"   ⚠️ Auto-detected from filename '{filename}': {source_info}")
            meta.update(source_info)
            
            # Extract classification fields
            # Use provided domain as override if it's set and valid
            major_domain = classification.get("major_domain")
            if provided_major_domain != "Unclassified":
                major_domain = provided_major_domain
                
            sub_domain = classification.get("sub_domain")
            micro_topic = classification.get("micro_topic")
            sub_topics = classification.get("sub_topics", [])
            
            # Validate major_domain
            if major_domain and major_domain not in domains:
                # Check if LLM confused a sub_domain as major_domain
                corrected = False
                for valid_major, sub_domains in domains.items():
                    if major_domain in sub_domains:
                        logger.warning(f"⚠️ LLM returned sub_domain '{major_domain}' as major_domain, correcting to '{valid_major}'")
                        # If sub_domain wasn't provided, use the one LLM returned
                        if not sub_domain:
                            sub_domain = major_domain
                        major_domain = valid_major
                        corrected = True
                        break
                
                # If not a sub_domain either, use rule-based fallback
                if not corrected:
                    logger.warning(f"⚠️ Invalid major_domain '{major_domain}', using rule-based fallback")
                    rule_meta = detect_topic(chunk['content'], subject)
                    major_domain = rule_meta.get("major_domain") or "Unclassified"
                    sub_domain = rule_meta.get("sub_domain") or sub_domain or "Unknown"
            
            # Fallback to rule-based if GPT didn't provide domain
            if not major_domain:
                rule_meta = detect_topic(chunk['content'], subject)
                major_domain = rule_meta.get("major_domain") or "Unclassified"
                sub_domain = rule_meta.get("sub_domain") or sub_domain or "Unknown"
            
            # Update metadata
            meta.update({
                "subject": subject,
                "major_domain": major_domain,
                "sub_domain": sub_domain or "Unknown",
                "micro_topic": micro_topic or "General Concepts",
                "sub_topics": sub_topics if isinstance(sub_topics, list) else []
            })
            
            enriched.append({
                "content": chunk["content"],
                "metadata": meta
            })
        
        # Small delay between batches to avoid rate limits
        if i + CLASSIFICATION_BATCH_SIZE < len(chunks):
            time.sleep(0.5)
    
    return enriched


def enrich_metadata(chunk_text: str, filename: str, chapter: str, section: str, llm_client: OpenAI) -> Dict[str, Any]:
    """Hybrid enrichment — rules first, then LLM fallback."""
    rule_meta = detect_topic(chunk_text)
    
    # Detect source_type from filename
    source_info = detect_source_type(filename)

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
            **source_info  # Add source_type and source_subtype
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
            "filename": filename,
            **source_info  # Add source_type and source_subtype
        }

    meta = {
        "subject": "Geography",
        "chapter": chapter,
        "section": section,
        "filename": filename,
        **source_info  # Add source_type and source_subtype
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
