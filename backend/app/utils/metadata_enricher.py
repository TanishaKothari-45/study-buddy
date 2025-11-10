import re
import json
import logging
import time
from typing import Dict, Any, List
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

# Legacy GEOGRAPHY_TOPICS for backward compatibility
GEOGRAPHY_TOPICS = GEOGRAPHY_DOMAINS.copy()
GEOGRAPHY_TOPICS["Map-Based Questions"] = [
    "Mapping", "Political and Physical Features"
]

# System prompt for batch classification
SYSTEM_PROMPT = f"""
You are a UPSC Geography domain expert.

Classify each provided passage according to the following hierarchy:

• major_domain  → one of: {list(GEOGRAPHY_DOMAINS.keys())}

• sub_domain    → choose only from the valid sub-domains under that major domain:

{json.dumps(GEOGRAPHY_DOMAINS, indent=2)}

• micro_topic   → the main concept or phenomenon described (free-form, 1-4 words)

• sub_topics    → optional list of smaller ideas/examples if multiple appear (array of strings)

Guidelines:
- Use exact names from the lists for major_domain and sub_domain.
- Infer micro_topic and sub_topics contextually from the passage.
- Keep micro_topic concise (1–4 words).
- If unsure about micro_topic, use "General Concepts".
- Return pure JSON array — one object per passage, no explanations.

Example output format:
[
  {{"major_domain": "Indian Geography", "sub_domain": "Indian Climate", "micro_topic": "Monsoon", "sub_topics": ["El Niño", "La Niña"]}},
  {{"major_domain": "Physical Geography", "sub_domain": "Climatology", "micro_topic": "Jet Streams", "sub_topics": []}}
]
"""

# Configuration
CLASSIFICATION_BATCH_SIZE = 5
MAX_RETRIES = 1

# --- simple rule-based detection (fallback) --- #
def detect_topic(text: str) -> Dict[str, str]:
    """Rule-based fallback for domain detection"""
    text_lower = text.lower()
    for domain, subtopics in GEOGRAPHY_TOPICS.items():
        for sub in subtopics:
            if re.search(rf"\b{sub.lower().split()[0]}\b", text_lower):
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


def enrich_batch(batch: List[Dict[str, Any]], client: OpenAI) -> List[Dict[str, Any]]:
    """Send a batch of chunks to GPT and return enriched classifications."""
    # Prepare combined input
    combined = "\n\n".join([
        f"CHUNK {i+1}:\n{chunk['content'][:1800]}"
        for i, chunk in enumerate(batch)
    ])
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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


def classify_chunks_batch(chunks: List[Dict[str, Any]], client: OpenAI) -> List[Dict[str, Any]]:
    """
    Classify all chunks in batches and merge results into metadata.
    
    Args:
        chunks: List of dicts with 'content' and 'metadata' keys
        client: OpenAI client instance
    
    Returns:
        List of enriched chunks with major_domain, sub_domain, micro_topic, sub_topics added
    """
    enriched = []
    
    for i in range(0, len(chunks), CLASSIFICATION_BATCH_SIZE):
        batch = chunks[i:i + CLASSIFICATION_BATCH_SIZE]
        batch_num = (i // CLASSIFICATION_BATCH_SIZE) + 1
        total_batches = (len(chunks) + CLASSIFICATION_BATCH_SIZE - 1) // CLASSIFICATION_BATCH_SIZE
        
        logger.info(f"   Processing classification batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        
        results = enrich_batch(batch, client)
        
        for j, chunk in enumerate(batch):
            classification = results[j] if j < len(results) else {}
            meta = chunk["metadata"].copy()
            
            # Extract classification fields
            major_domain = classification.get("major_domain")
            sub_domain = classification.get("sub_domain")
            micro_topic = classification.get("micro_topic")
            sub_topics = classification.get("sub_topics", [])
            
            # Validate major_domain
            if major_domain and major_domain not in GEOGRAPHY_DOMAINS:
                # Check if LLM confused a sub_domain as major_domain
                corrected = False
                for valid_major, sub_domains in GEOGRAPHY_DOMAINS.items():
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
                    rule_meta = detect_topic(chunk['content'])
                    major_domain = rule_meta.get("major_domain") or "Unclassified"
                    sub_domain = rule_meta.get("sub_domain") or sub_domain or "Unknown"
            
            # Fallback to rule-based if GPT didn't provide domain
            if not major_domain:
                rule_meta = detect_topic(chunk['content'])
                major_domain = rule_meta.get("major_domain") or "Unclassified"
                sub_domain = rule_meta.get("sub_domain") or sub_domain or "Unknown"
            
            # Update metadata
            meta.update({
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
