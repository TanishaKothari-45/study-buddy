"""
Stage 4 — Quality Gate

Validates each generated question without LLM calls:
1.  Trap presence   — at least one wrong option contains a trap-related keyword
2.  CA in stem      — CA-flagged questions: CA event keywords appear in the question stem
3.  Structural      — 4 options, valid correct_answer letter, non-empty explanation
4.  Semantic dedup  — embedding-based cosine similarity < 0.85 against all prior questions

Returns (passed, failed_skeleton_ids) tuple.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .models import QuestionSkeleton, V2GeneratedQuestion

logger = logging.getLogger(__name__)

# ── Trap keyword hints (regex fragments) by trap_id prefix ────────────────────
# These are deliberately loose — if ANY hint appears in the wrong options we pass.
_TRAP_KEYWORDS: Dict[str, List[str]] = {
    "GEO_T01": ["feeds", "flows into", "directly feeds", "feeder", "tributary"],
    "GEO_T02": ["longest", "shortest", "border", "boundary", "km"],
    "GEO_T03": ["salinity", "precipitation", "river inflow", "evaporation"],
    "GEO_T04": ["thicker", "thinner", "equator", "poles", "higher at", "lower at"],
    "GEO_T05": ["source of", "extracted from", "ore", "mineral"],
    "GEO_T06": ["arable", "irrigated", "productivity", "per hectare"],
    "GEO_T07": ["first", "largest", "registered", "greenfield", "private"],
    "GEO_T08": ["nitrogen", "sulphur", "pyroclastic", "ash", "all of the above"],
    "GEO_T09": ["deciduous", "evergreen", "tropical", "sheds"],
    "GEO_T10": ["greenfield", "brownfield", "new", "expanded", "upgraded"],
    "POL_T01": ["president", "speaker", "chairman", "disqualification", "anti-defection"],
    "POL_T02": ["political party", "constitution", "tenth schedule", "mentioned"],
    "POL_T03": ["may accept", "must accept", "amendments", "money bill", "rajya sabha"],
    "POL_T04": ["part ix", "part x", "part xviii", "schedule", "emergency"],
    "POL_T05": ["union list", "state list", "concurrent list", "inter-state"],
    "POL_T06": ["command", "advise", "coordinate", "cds", "service chief"],
    "POL_T07": ["18th lok sabha", "delimitation", "15 years", "reservation"],
    "POL_T08": ["habeas corpus", "mandamus", "certiorari", "prohibition", "quo warranto"],
    "POL_T09": ["only a member", "any citizen", "mp", "ethics committee", "complaint"],
    "POL_T10": ["lokpal", "inquiry", "sitting pm", "public servant", "outside india"],
    "HIS_T01": ["swatantra", "socialist", "congress", "rajagopalachari", "narendra dev"],
    "HIS_T02": ["madhyama", "kavyalankara", "natyashastra", "mahabhashya", "bhasa"],
    "HIS_T03": ["provisional president", "sachchidananda", "rajendra prasad", "drafting"],
    "HIS_T04": ["governor-general", "federal legislature", "reserved", "transferred"],
    "HIS_T05": ["ryotwari", "zamindari", "mahalwari", "revenue", "bad harvest"],
    "HIS_T06": ["theravada", "mahayana", "sarvastivada", "visuddhimagga"],
    "HIS_T07": ["2023", "2022", "shantiniketan", "hoysala", "rani-ki-vav"],
    "HIS_T08": ["mitra shakti", "bangladesh", "sri lanka", "nepal", "aundh"],
    "ECO_T01": ["40%", "20%", "centre", "states", "debt", "gdp"],
    "ECO_T02": ["monetisation", "bank", "borrowing", "creation of new money"],
    "ECO_T03": ["tax evasion", "revenue", "exchequer", "primary"], 
    "ECO_T04": ["interest coverage", "emerging risk", "present risk", "icr"],
    "ECO_T05": ["customs duty", "nil duty", "import", "edible oil"],
}

# Generic fallback keywords for unknown trap_ids
_GENERIC_TRAP_WORDS = [
    "only", "never", "always", "all", "none", "first", "last", "solely",
    "not", "except", "incorrect", "false"
]


def _wrong_options(question: V2GeneratedQuestion) -> List[str]:
    """Return text of the wrong options (exclude correct answer letter)."""
    wrong = []
    for opt in question.options:
        letter = opt[0].upper() if opt else ""
        if letter != question.correct_answer:
            wrong.append(opt.lower())
    return wrong


def _check_trap_presence(question: V2GeneratedQuestion, skeleton: QuestionSkeleton) -> bool:
    """Check if a trap-related keyword appears in at least one wrong option."""
    trap_id = skeleton.trap_strategy
    wrong_text = " ".join(_wrong_options(question))

    hints = _TRAP_KEYWORDS.get(trap_id, _GENERIC_TRAP_WORDS)
    for hint in hints:
        if re.search(re.escape(hint), wrong_text, re.IGNORECASE):
            return True

    # Also scan explanation — trap should be called out there
    explanation_lower = question.explanation.lower()
    for hint in hints:
        if hint.lower() in explanation_lower:
            return True

    return False


def _check_ca_in_stem(question: V2GeneratedQuestion, skeleton: QuestionSkeleton) -> bool:
    """For CA-flagged questions, verify the CA event appears in the question stem."""
    if not skeleton.ca_flag:
        return True  # not applicable

    ca_event = skeleton.ca_event.lower()
    q_lower = question.question.lower()

    if not ca_event:
        return True  # no specific CA event required

    # Extract keywords from ca_event (skip stopwords)
    stopwords = {"the", "a", "an", "of", "in", "for", "and", "or", "to", "with"}
    keywords = [w for w in re.split(r"\W+", ca_event) if len(w) > 2 and w not in stopwords]

    # At least half the CA keywords must appear in the stem
    matches = sum(1 for kw in keywords if kw in q_lower)
    return matches >= max(1, len(keywords) // 2)


def _structural_check(question: V2GeneratedQuestion) -> bool:
    """Basic structural validation."""
    return (
        len(question.question.strip()) > 30
        and len(question.options) >= 4
        and question.correct_answer in ("A", "B", "C", "D")
        and len(question.explanation.strip()) > 20
    )


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    import math
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


async def run_quality_gate(
    questions: List[V2GeneratedQuestion],
    skeletons: List[QuestionSkeleton],
    embedder=None,
    dedup_threshold: float = 0.85,
) -> Tuple[List[V2GeneratedQuestion], List[str]]:
    """
    Stage 4: validate questions. Returns (passed, failed_skeleton_ids).

    Checks (in order):
    1. Structural validity
    2. Trap presence in wrong options / explanation
    3. CA event in question stem (for ca_flag=True)
    4. Semantic deduplication (if embedder available)
    """
    logger.info(f"🔍 [Stage 4] Running quality gate on {len(questions)} questions …")

    skeleton_map: Dict[str, QuestionSkeleton] = {sk.skeleton_id: sk for sk in skeletons}
    passed: List[V2GeneratedQuestion] = []
    failed_ids: List[str] = []

    for q in questions:
        sk = skeleton_map.get(q.skeleton_id)
        if sk is None:
            logger.warning(f"⚠️ [Stage 4] No skeleton found for {q.skeleton_id} — skipping")
            failed_ids.append(q.skeleton_id)
            continue

        # 1. Structure
        if not _structural_check(q):
            logger.debug(f"   ❌ {q.skeleton_id} — structural check failed")
            failed_ids.append(q.skeleton_id)
            continue

        # 2. Trap presence
        trap_ok = _check_trap_presence(q, sk)
        q.trap_verified = trap_ok
        if not trap_ok:
            logger.debug(f"   ⚠️ {q.skeleton_id} — trap not detected in wrong options")
            # Don't fail yet — trap verification is soft; mark and continue

        # 3. CA in stem
        ca_ok = _check_ca_in_stem(q, sk)
        q.ca_in_stem = ca_ok
        if sk.ca_flag and not ca_ok:
            logger.debug(f"   ⚠️ {q.skeleton_id} — CA event not found in stem")
            # Also soft fail

        # Quality score (0–1)
        score = 0.5
        if trap_ok:
            score += 0.3
        if ca_ok or not sk.ca_flag:
            score += 0.2
        q.quality_score = round(score, 2)

        passed.append(q)

    # 4. Semantic deduplication
    if embedder and len(passed) > 1:
        logger.info(f"   🔗 Running embedding-based dedup on {len(passed)} questions …")
        try:
            texts = [q.question for q in passed]
            embeddings = await asyncio.to_thread(embedder.embed_documents, texts)

            kept: List[V2GeneratedQuestion] = []
            kept_embeddings: List[List[float]] = []
            seen_ids: Set[str] = set()

            for q, emb in zip(passed, embeddings):
                too_similar = any(
                    _cosine_sim(emb, prev_emb) >= dedup_threshold
                    for prev_emb in kept_embeddings
                )
                if too_similar:
                    logger.debug(f"   🔁 {q.skeleton_id} — duplicate detected, dropping")
                    failed_ids.append(q.skeleton_id)
                else:
                    kept.append(q)
                    kept_embeddings.append(emb)
                    seen_ids.add(q.skeleton_id)

            passed = kept
        except Exception as e:
            logger.warning(f"⚠️ [Stage 4] Dedup failed: {e} — skipping dedup step")

    # Sub-domain entropy check
    sd_counts: Dict[str, int] = defaultdict(int)
    for q in passed:
        sd_counts[q.sub_domain or "Unknown"] += 1
    logger.info(f"   📊 Sub-domain distribution: {dict(sd_counts)}")

    logger.info(
        f"✅ [Stage 4] Quality gate complete: "
        f"{len(passed)} passed, {len(failed_ids)} failed"
    )
    return passed, failed_ids
