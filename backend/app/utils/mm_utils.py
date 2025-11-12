import random
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def enforce_source_diversity(
    chunks: List[Dict],
    total_target: int = 15,
    source_weights: Optional[Dict[str, float]] = None,
    concept_subweights: Optional[Dict[str, float]] = None,
    max_per_file: int = 2
) -> List[Dict]:
    """
    Weighted, source-aware diversity enforcement.
    
    Ensures retrieved chunks are balanced according to proportional weights
    between PYQs, Concept (NCERT + Topic), and Current Affairs.
    
    Example weights:
        source_weights = {"pyq": 0.2, "current_affairs": 0.3, "concept": 0.5}
        concept_subweights = {"ncert": 0.25, "topic": 0.25}  # fractions of concept
    
    Args:
        chunks: list of chunk dicts (each with metadata)
        total_target: total number of chunks desired after balancing
        source_weights: proportional weights for each source_type
        concept_subweights: optional distribution inside 'concept'
        max_per_file: max number of chunks from the same filename
        
    Returns:
        List of balanced chunks (shuffled)
    """
    if not chunks:
        return []

    # --- default weights if none provided ---
    if source_weights is None:
        source_weights = {"pyq": 0.2, "current_affairs": 0.3, "concept": 0.5}
    if concept_subweights is None:
        concept_subweights = {"ncert": 0.25, "topic": 0.25}

    # --- group by source_type + subtype ---
    source_map: Dict[str, List[Dict]] = {}
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        stype = meta.get("source_type", "concept")
        ssub = meta.get("source_subtype", None)
        key = f"{stype}:{ssub}" if ssub else stype
        source_map.setdefault(key, []).append(chunk)

    # --- count how many total available per source group ---
    total_available = {k: len(v) for k, v in source_map.items()}

    # --- helper: limit per file ---
    def limit_per_file(group: List[Dict], limit: int = max_per_file) -> List[Dict]:
        """Enforce per-file limit inside each source group."""
        file_map = {}
        for c in group:
            fname = c.get("metadata", {}).get("filename", "unknown")
            file_map.setdefault(fname, []).append(c)
        balanced = []
        for fname, g in file_map.items():
            balanced.extend(g[:limit])
        return balanced

    # --- step 1: compute target per top-level source ---
    targets = {}
    for stype, weight in source_weights.items():
        targets[stype] = max(1, round(total_target * weight))

    # --- step 2: split concept targets into subtypes ---
    if "concept" in targets and concept_subweights:
        concept_total = targets["concept"]
        for sub, sub_w in concept_subweights.items():
            targets[f"concept:{sub}"] = max(1, round(concept_total * (sub_w / sum(concept_subweights.values()))))
        del targets["concept"]

    # --- step 3: select chunks proportionally ---
    selected = []
    for key, target_count in targets.items():
        group = source_map.get(key, [])
        if not group:
            logger.debug(f"⚠️ No chunks found for {key}, skipping.")
            continue

        limited_group = limit_per_file(group, max_per_file)
        if len(limited_group) > target_count:
            limited_group = random.sample(limited_group, target_count)
        selected.extend(limited_group)
        logger.debug(f"📦 Selected {len(limited_group)}/{len(group)} from {key}")

    # --- step 4: if we have too few (e.g., missing categories), fill from others ---
    if len(selected) < total_target:
        missing = total_target - len(selected)
        # Gather all leftovers (not yet used)
        all_candidates = [c for key, grp in source_map.items() for c in grp if c not in selected]
        if all_candidates:
            fill = random.sample(all_candidates, min(missing, len(all_candidates)))
            selected.extend(fill)
            logger.debug(f"🧩 Filled {len(fill)} missing slots with fallback chunks")

    # --- step 5: shuffle for randomness ---
    random.shuffle(selected)

    logger.info(
        f"✅ Weighted source diversity applied: "
        f"{len(chunks)} → {len(selected)} chunks "
        f"({len(source_map)} source groups)"
    )
    return selected
