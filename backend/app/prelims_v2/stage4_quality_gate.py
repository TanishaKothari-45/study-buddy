"""
Stage 4 — Quality Gate

Validates each generated question without LLM calls:
1.  Structural      — 4 options, valid correct_answer letter, non-empty explanation
2.  Trap presence   — at least one wrong option contains a trap-related keyword
3.  CA in stem      — CA-flagged questions: CA event keywords appear in the question stem
4.  Distractor plausibility — wrong options must sit in the "plausible but wrong" similarity
                              range vs the correct answer (not near-copies, not unrelated fillers)
5.  Semantic dedup  — embedding-based cosine similarity < 0.85 against all prior questions

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

# ── Distractor plausibility thresholds ────────────────────────────────────────
# Sweet spot for good UPSC distractors: similarity 0.55–0.85 (plausible but wrong).
# Tuned conservatively: only flag extremes to avoid false positives.
#   > _DISTRACTOR_TOO_SIMILAR  → near-copy of correct answer (copy-paste distractor)
#   < _DISTRACTOR_TOO_DISTANT  → completely unrelated filler (only flagged for long options
#                                 to avoid false positives from short placeholder text)
_DISTRACTOR_TOO_SIMILAR  = 0.92
_DISTRACTOR_TOO_DISTANT  = 0.40
_DISTRACTOR_MIN_WORDS    = 5    # "too distant" check only applied to options with ≥ N words


def _strip_option_prefix(opt: str) -> str:
    """Strip leading option labels like 'A)', '(a)', 'A.', '(A) ' from option text."""
    return re.sub(r"^\s*[\(\[]?[A-Da-d][\)\]\.]\s*", "", opt).strip()


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


def _check_v45_controlled_constraints(question: V2GeneratedQuestion, skeleton: QuestionSkeleton) -> Tuple[bool, str]:
    """
    Validate v4.5 Controlled pre-sampling constraints:
    1. question_type matches available_question_types
    2. trap_id matches available_trap_ids
    3. All required aspects are covered in question + explanation

    Returns (is_valid, reason_if_invalid)
    """
    # Check 1: question_type constraint
    available_qts = getattr(skeleton, "available_question_types", [])
    if available_qts and question.question_type not in available_qts:
        return False, f"question_type '{question.question_type}' not in available types {available_qts}"

    # Check 2: trap_id constraint
    available_traps = getattr(skeleton, "available_trap_ids", [])
    if available_traps and skeleton.trap_strategy not in available_traps:
        return False, f"trap_id '{skeleton.trap_strategy}' not in available traps {available_traps}"

    # Check 3: aspect coverage (soft check — warn but don't fail)
    # Verify that all required aspects from sub_concepts appear in question or explanation
    combined_text = (question.question + " " + question.explanation).lower()
    aspects_to_check = set(sc.aspect.lower() for sc in skeleton.sub_concepts)
    missing_aspects = [
        asp for asp in aspects_to_check
        if asp not in combined_text
    ]
    if missing_aspects:
        logger.debug(
            f"   ⚠️ {question.skeleton_id} — missing aspects in question: {missing_aspects}"
        )
        # Soft warning, not a failure

    return True, ""


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    import math
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _embed_texts(embedder, texts: List[str]) -> List[List[float]]:
    """
    Embed texts for quality-gate checks (distractor plausibility + dedup).

    Priority: local SBERT first (free, ~384 dims) → LangChain → OpenAI fallback.
    Quality gate only needs relative cosine similarity, so dimension consistency
    with Pinecone index is NOT required — local SBERT is ideal here.
    """
    if not texts:
        return []
    # 1. Prefer local SentenceTransformer (free, no API call)
    if hasattr(embedder, "get_sbert_embeddings"):
        try:
            return embedder.get_sbert_embeddings(texts)
        except Exception:
            pass  # fall through to next option
    # 2. LangChain wrapper
    if hasattr(embedder, "embed_documents"):
        return embedder.embed_documents(texts)
    # 3. Custom Embedder (tries OpenAI → SBERT internally)
    if hasattr(embedder, "get_embeddings"):
        return embedder.get_embeddings(texts)
    # 4. Single-query loop fallback
    if hasattr(embedder, "embed_query"):
        return [embedder.embed_query(t) for t in texts]
    raise AttributeError(
        f"Embedder {type(embedder).__name__} has no embedding method"
    )


# ── Phase 2: Quality scoring helpers ────────────────────────────────────────

def _score_trap(q: V2GeneratedQuestion, sk: QuestionSkeleton) -> float:
    """
    0-1: how well the trap is embedded in the question.
      0.5 — trap keyword found in at least one wrong option
      0.3 — trap mechanism explicitly named in explanation
      0.2 — explanation contains reasoning words (because/since/therefore/whereas)
    """
    trap_id    = sk.trap_strategy if sk else ""
    hints      = _TRAP_KEYWORDS.get(trap_id, _GENERIC_TRAP_WORDS)
    wrong_text = " ".join(_wrong_options(q)).lower()
    expl_lower = q.explanation.lower()

    score = 0.0
    # Trap present in wrong options
    if any(re.search(re.escape(h), wrong_text, re.IGNORECASE) for h in hints):
        score += 0.5
    # Trap mechanism mentioned in explanation
    if any(h.lower() in expl_lower for h in hints):
        score += 0.3
    # Explanation contains causal/contrastive reasoning
    if re.search(r"\b(because|since|therefore|whereas|however|but|although)\b", expl_lower):
        score += 0.2
    return min(score, 1.0)


def _score_explanation(q: V2GeneratedQuestion) -> float:
    """
    0-1: depth and quality of the explanation.
      0.4 — word count ≥ 80 (thorough); 0.2 for ≥ 40 (adequate)
      0.3 — mentions at least 2 wrong option letters (A/B/C/D) → explains why wrong
      0.3 — contains reasoning words (because/since/incorrect/correct/explains)
    """
    words     = q.explanation.split()
    expl_lower = q.explanation.lower()

    score = 0.0
    # Word count depth
    if len(words) >= 80:
        score += 0.4
    elif len(words) >= 40:
        score += 0.2

    # Wrong option letters mentioned
    letters_mentioned = sum(
        1 for letter in ("a)", "b)", "c)", "d)", "option a", "option b", "option c", "option d")
        if letter in expl_lower
    )
    if letters_mentioned >= 2:
        score += 0.3
    elif letters_mentioned >= 1:
        score += 0.15

    # Reasoning / correctness vocabulary
    if re.search(r"\b(because|since|therefore|incorrect|correct|explains|reason|whereas)\b", expl_lower):
        score += 0.3

    return min(score, 1.0)


def _score_coverage(q: V2GeneratedQuestion, sk: QuestionSkeleton) -> float:
    """
    0-1: CA integration + sub_concept aspect coverage.
      0.5 — CA in stem (if ca_flag) or CA not required
      0.5 — aspect keywords from sub_concepts present in question + explanation
    """
    score = 0.0

    # CA integration
    if not sk or not sk.ca_flag:
        score += 0.5  # Not required → full marks
    else:
        q.ca_in_stem = _check_ca_in_stem(q, sk)
        if q.ca_in_stem:
            score += 0.5

    # Aspect coverage
    if sk and sk.sub_concepts:
        combined = (q.question + " " + q.explanation).lower()
        aspects  = [sc.aspect.lower() for sc in sk.sub_concepts]
        matched  = sum(1 for asp in aspects if asp in combined)
        score   += 0.5 * (matched / len(aspects))
    else:
        score += 0.5  # No sub_concepts to check → full marks

    return min(score, 1.0)


def _score_distractor_from_embeddings(
    correct_emb: List[float],
    wrong_embs: List[List[float]],
    wrong_texts: List[str],
) -> float:
    """
    0-1: fraction of wrong options in the plausible [0.55–0.85] similarity range.
    Options outside this range are either near-copies or completely unrelated fillers.
    """
    if not wrong_embs:
        return 1.0
    good = 0
    for w_text, w_emb in zip(wrong_texts, wrong_embs):
        sim        = _cosine_sim(correct_emb, w_emb)
        word_count = len(w_text.split())
        too_close  = sim > _DISTRACTOR_TOO_SIMILAR
        too_far    = sim < _DISTRACTOR_TOO_DISTANT and word_count >= _DISTRACTOR_MIN_WORDS
        if not too_close and not too_far:
            good += 1
    return round(good / len(wrong_embs), 2)


def _compute_composite_score(
    trap: float,
    distractor: float,
    explanation: float,
    coverage: float,
) -> float:
    """Combine sub-scores (each 0-1) into a 0-100 composite."""
    return round(trap * 40 + distractor * 30 + explanation * 20 + coverage * 10, 1)


# ── Phase 3: MMR-style diversity selection ──────────────────────────────────

def _mmr_select(
    questions: List[V2GeneratedQuestion],
    embeddings: List[List[float]],
    target: int,
    sim_threshold: float,
) -> Tuple[List[V2GeneratedQuestion], List[V2GeneratedQuestion]]:
    """
    Greedy diversity-aware selection.
    Questions are pre-sorted by quality_score (desc) before calling this.
    Picks up to `target` questions ensuring no two selected are more similar
    than `sim_threshold` (cosine).

    Returns (selected, rejected).
    """
    selected:      List[V2GeneratedQuestion] = []
    selected_embs: List[List[float]]         = []
    rejected:      List[V2GeneratedQuestion] = []

    for q, emb in zip(questions, embeddings):
        if len(selected) >= target:
            rejected.append(q)
            continue
        too_similar = any(
            _cosine_sim(emb, prev_emb) >= sim_threshold
            for prev_emb in selected_embs
        )
        if too_similar:
            rejected.append(q)
        else:
            selected.append(q)
            selected_embs.append(emb)

    return selected, rejected


# ── Main entry point ─────────────────────────────────────────────────────────

async def run_quality_gate(
    questions: List[V2GeneratedQuestion],
    skeletons: List[QuestionSkeleton],
    embedder=None,
    dedup_threshold: float = 0.85,  # kept for backwards compat, not used directly
) -> Tuple[List[V2GeneratedQuestion], List[str]]:
    """
    Stage 4 — 3-phase quality gate. Returns (selected, failed_skeleton_ids).

    PHASE 1 — Hard gates (per-question, no embeddings):
      a) Structural check: 4 options, valid answer letter, non-trivial text
      b) Constraint check: question_type + trap_id match v4.5 skeleton
      → Failures immediately discarded with failure_reason set

    PHASE 2 — Quality scoring (batch embeddings for distractors):
      a) Trap score      (0-40): trap in wrong options + explanation reasoning
      b) Distractor score(0-30): fraction of wrong options in plausible range
      c) Explanation score(0-20): depth, reasoning words, wrong options addressed
      d) Coverage score  (0-10): CA integration + sub_concept aspects
      → composite quality_score 0-100 assigned to each question

    PHASE 3 — MMR diversity selection:
      a) Sort all scored questions by quality_score (desc)
      b) Greedy pick at 88% similarity threshold → keep top target_count
      c) Gap fill: if < target, lower to 75% on rejected pool
      d) Questions still short → returned as failed (trigger Stage 5 retry)
    """
    target = len(skeletons)  # Primary skeleton count = how many we need
    logger.info(
        f"🔍 [Stage 4] Running 3-phase quality gate on {len(questions)} questions "
        f"(target={target}) …"
    )

    skeleton_map: Dict[str, QuestionSkeleton] = {sk.skeleton_id: sk for sk in skeletons}
    failed_ids: List[str] = []

    # ── PHASE 1: Hard gates ──────────────────────────────────────────────────
    logger.info("   [P1] Hard gates …")
    survivors: List[V2GeneratedQuestion] = []

    for q in questions:
        sk = skeleton_map.get(q.skeleton_id)  # None for extra/buffer questions

        # Structural check
        if not _structural_check(q):
            q.failure_reason = "STRUCTURE_FAIL"
            logger.debug(f"   ❌ {q.skeleton_id} — structural check failed")
            if not q.is_extra:
                failed_ids.append(q.skeleton_id)
            continue

        # Constraint check (only for primary skeleton questions)
        if sk is not None:
            v45_ok, v45_reason = _check_v45_controlled_constraints(q, sk)
            if not v45_ok:
                q.failure_reason = "CONSTRAINT_VIOLATION"
                logger.debug(f"   ❌ {q.skeleton_id} — constraint violated: {v45_reason}")
                failed_ids.append(q.skeleton_id)
                continue

        survivors.append(q)

    logger.info(
        f"   [P1] {len(survivors)}/{len(questions)} passed hard gates "
        f"({len(questions) - len(survivors)} failed)"
    )

    if not survivors:
        return [], failed_ids

    # ── PHASE 2: Quality scoring (batch embeddings) ──────────────────────────
    logger.info(f"   [P2] Quality scoring {len(survivors)} questions …")

    # Trap + explanation + coverage scores (no embeddings needed)
    for q in survivors:
        sk             = skeleton_map.get(q.skeleton_id)
        trap_s         = _score_trap(q, sk)
        explanation_s  = _score_explanation(q)
        coverage_s     = _score_coverage(q, sk)
        q.trap_verified = trap_s >= 0.5

        q.quality_breakdown = {
            "trap":        round(trap_s, 3),
            "distractor":  0.0,     # filled after embeddings
            "explanation": round(explanation_s, 3),
            "coverage":    round(coverage_s, 3),
        }

    # Distractor score: batch-embed all options in one call
    if embedder:
        try:
            correct_texts:    List[str]       = []
            wrong_texts_per_q: List[List[str]] = []

            for q in survivors:
                correct_idx = ord(q.correct_answer) - ord("A")
                correct_raw = q.options[correct_idx] if correct_idx < len(q.options) else ""
                correct_texts.append(_strip_option_prefix(correct_raw))
                wrong_raw = [
                    _strip_option_prefix(opt)
                    for j, opt in enumerate(q.options) if j != correct_idx
                ]
                wrong_texts_per_q.append(wrong_raw)

            flat_wrong: List[str] = []
            flat_offsets: List[int] = []
            for wrongs in wrong_texts_per_q:
                flat_offsets.append(len(flat_wrong))
                flat_wrong.extend(wrongs)

            correct_embs = await asyncio.to_thread(_embed_texts, embedder, correct_texts)
            wrong_embs   = await asyncio.to_thread(_embed_texts, embedder, flat_wrong) if flat_wrong else []

            for idx, q in enumerate(survivors):
                c_emb   = correct_embs[idx]
                start   = flat_offsets[idx]
                w_texts = wrong_texts_per_q[idx]
                w_embs  = wrong_embs[start: start + len(w_texts)]

                d_score = _score_distractor_from_embeddings(c_emb, w_embs, w_texts)
                q.distractor_quality                  = d_score
                q.quality_breakdown["distractor"]     = d_score

        except Exception as e:
            logger.warning(f"⚠️ [Stage 4] Distractor embedding failed: {e} — using default score")
            for q in survivors:
                q.quality_breakdown["distractor"] = 0.8  # neutral default

    # Assign composite quality_score
    for q in survivors:
        bd = q.quality_breakdown
        q.quality_score = _compute_composite_score(
            trap        = bd.get("trap", 0.5),
            distractor  = bd.get("distractor", 0.8),
            explanation = bd.get("explanation", 0.5),
            coverage    = bd.get("coverage", 0.5),
        )

    # Sort by quality_score descending before MMR selection
    survivors.sort(key=lambda q: q.quality_score, reverse=True)

    logger.info(
        f"   [P2] Quality scores: "
        + ", ".join(f"{q.skeleton_id}={q.quality_score}" for q in survivors)
    )

    # ── PHASE 3: MMR diversity selection ────────────────────────────────────
    logger.info(f"   [P3] MMR selection (target={target}) …")

    if not embedder or len(survivors) <= 1:
        # No embedder — just take top-target by quality score
        selected  = survivors[:target]
        remainder = survivors[target:]
        for q in remainder:
            q.failure_reason = "QUALITY_RANK_DROP"
            if not q.is_extra:
                failed_ids.append(q.skeleton_id)
    else:
        try:
            stem_texts = [q.question for q in survivors]
            stem_embs  = await asyncio.to_thread(_embed_texts, embedder, stem_texts)

            # Phase 3a: strict MMR at 88%
            selected, rejected = _mmr_select(survivors, stem_embs, target, sim_threshold=0.88)
            logger.info(
                f"   [P3a] MMR@0.88: {len(selected)} selected, {len(rejected)} rejected"
            )

            # Phase 3b: gap fill at 75% if we're short
            if len(selected) < target and rejected:
                still_need = target - len(selected)
                logger.info(
                    f"   [P3b] Gap fill needed ({len(selected)}/{target}). "
                    f"Loosening to 0.75 on {len(rejected)} candidates …"
                )
                # Sort gap candidates by quality desc (survivors was already sorted, rejected preserves that order)
                selected_embs = [stem_embs[survivors.index(q)] for q in selected]
                gap_fill, still_rejected = [], []

                for q in rejected:
                    if len(gap_fill) >= still_need:
                        still_rejected.append(q)
                        continue
                    q_emb = stem_embs[survivors.index(q)]
                    all_embs = selected_embs + [stem_embs[survivors.index(gq)] for gq in gap_fill]
                    too_similar = any(_cosine_sim(q_emb, e) >= 0.75 for e in all_embs)
                    if not too_similar:
                        gap_fill.append(q)
                        logger.debug(f"   ✓ {q.skeleton_id} gap-filled at 0.75")
                    else:
                        still_rejected.append(q)

                selected.extend(gap_fill)
                rejected = still_rejected
                logger.info(f"   [P3b] After gap fill: {len(selected)}/{target}")

            # Mark rejected questions with failure reason
            for q in rejected:
                q.failure_reason = "DUPLICATE_DEDUP" if not q.failure_reason else q.failure_reason
                if not q.is_extra:
                    failed_ids.append(q.skeleton_id)

        except Exception as e:
            logger.warning(f"⚠️ [Stage 4] MMR selection failed: {e} — falling back to quality sort")
            selected  = survivors[:target]
            remainder = survivors[target:]
            for q in remainder:
                q.failure_reason = "QUALITY_RANK_DROP"
                if not q.is_extra:
                    failed_ids.append(q.skeleton_id)

    # Sub-domain entropy
    sd_counts: Dict[str, int] = defaultdict(int)
    for q in selected:
        sd_counts[q.sub_domain or "Unknown"] += 1
    logger.info(f"   📊 Sub-domain distribution: {dict(sd_counts)}")

    logger.info(
        f"✅ [Stage 4] Complete: {len(selected)} selected, {len(failed_ids)} failed "
        f"(need retry in Stage 5)"
    )
    return selected, failed_ids
