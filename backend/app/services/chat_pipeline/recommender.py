"""
Stage 3: Recommendations

Pure metadata-driven — no LLM needed.

Strategy (tightest → broadest):
  1. sub_topic overlap  — chunks sharing a sub_topic with retrieved chunks
  2. keyword match      — micro_topics containing keywords from current micro_topics
  3. same sub_domain + chapter — same book section, different micro_topic
  4. PYQ / current_affairs — scoped to current sub_domains only

Deliberately avoids major_domain lookup (too broad, pulls unrelated topics).
"""
import json
import re
import logging
from sqlalchemy import text, bindparam
from .state import RetrievedChunk, Recommendation

logger = logging.getLogger(__name__)

_MAX_RECOMMENDATIONS = 7


def _extract_meta(chunks: list[RetrievedChunk]) -> dict:
    major_domains: set[str] = set()
    sub_domains: set[str] = set()
    micro_topics: set[str] = set()
    sub_topics_all: set[str] = set()
    filenames: set[str] = set()

    for chunk in chunks:
        meta = chunk.metadata
        if meta.get("major_domain"):
            major_domains.add(meta["major_domain"])
        if meta.get("sub_domain"):
            sub_domains.add(meta["sub_domain"])
        if meta.get("micro_topic"):
            micro_topics.add(meta["micro_topic"])
        if meta.get("filename"):
            filenames.add(meta["filename"])
        raw = meta.get("sub_topics")
        if raw:
            try:
                topics = json.loads(raw) if isinstance(raw, str) else raw
                sub_topics_all.update(t for t in topics if t)
            except Exception:
                pass

    return {
        "major_domains": major_domains,
        "sub_domains": sub_domains,
        "micro_topics": micro_topics,
        "sub_topics": sub_topics_all,
        "filenames": filenames,
    }


def _keywords_from_micro_topics(micro_topics: set[str]) -> list[str]:
    """
    Extract meaningful keywords (≥4 chars) from micro_topic strings.
    E.g. "Southwest Monsoon" → ["Southwest", "Monsoon"]
    """
    keywords: list[str] = []
    stop = {"and", "the", "for", "with", "from", "over", "into", "that"}
    for mt in micro_topics:
        for word in re.split(r"[\s\-–/,]+", mt):
            w = word.strip()
            if len(w) >= 4 and w.lower() not in stop:
                keywords.append(w)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            result.append(k)
    return result[:6]  # top 6 keywords max


def build_recommendations(
    chunks: list[RetrievedChunk],
    content_store_engine,
) -> list[Recommendation]:
    if not chunks:
        return []

    meta = _extract_meta(chunks)
    covered_micro_topics = meta["micro_topics"]
    covered_sub_domains = meta["sub_domains"]
    recommendations: list[Recommendation] = []
    seen_labels: set[str] = set()

    def add(rec: Recommendation):
        key = rec.label.lower()
        if key not in seen_labels and rec.topic not in covered_micro_topics:
            seen_labels.add(key)
            recommendations.append(rec)

    keywords = _keywords_from_micro_topics(covered_micro_topics)

    # SQLAlchemy text() needs expanding bindparam for IN clauses
    sds_list = list(covered_sub_domains) if covered_sub_domains else ["__none__"]

    try:
        with content_store_engine.connect() as conn:

            # ── 1. sub_topic overlap ────────────────────────────────────────
            for st in list(meta["sub_topics"])[:5]:
                stmt = text("""
                    SELECT DISTINCT micro_topic, sub_domain, major_domain
                    FROM chunks
                    WHERE sub_topics LIKE :pattern
                      AND micro_topic IS NOT NULL AND micro_topic != ''
                      AND sub_domain IN :sds
                    LIMIT 4
                """).bindparams(bindparam("sds", expanding=True))
                rows = conn.execute(stmt, {"pattern": f"%{st}%", "sds": sds_list}).fetchall()

                for row in rows:
                    micro, sd, md = row[0], row[1], row[2]
                    if micro:
                        add(Recommendation(
                            type="deep_dive",
                            label=micro,
                            topic=micro,
                            sub_domain=sd or "",
                            major_domain=md or "",
                            query=f"Explain {micro} for UPSC",
                        ))

            # ── 2. Keyword match within same sub_domain ─────────────────────
            for kw in keywords[:4]:
                stmt = text("""
                    SELECT DISTINCT micro_topic, sub_domain, major_domain
                    FROM chunks
                    WHERE micro_topic LIKE :kw
                      AND micro_topic IS NOT NULL AND micro_topic != ''
                      AND sub_domain IN :sds
                    LIMIT 4
                """).bindparams(bindparam("sds", expanding=True))
                rows = conn.execute(stmt, {"kw": f"%{kw}%", "sds": sds_list}).fetchall()

                for row in rows:
                    micro, sd, md = row[0], row[1], row[2]
                    if micro:
                        add(Recommendation(
                            type="deep_dive",
                            label=micro,
                            topic=micro,
                            sub_domain=sd or "",
                            major_domain=md or "",
                            query=f"Explain {micro} for UPSC",
                        ))

            # ── 3. Same source file, different micro_topic ─────────────────
            for filename in list(meta["filenames"])[:2]:
                stmt = text("""
                    SELECT DISTINCT micro_topic, sub_domain, major_domain
                    FROM chunks
                    WHERE filename = :fn
                      AND micro_topic IS NOT NULL AND micro_topic != ''
                      AND sub_domain IN :sds
                    ORDER BY RANDOM()
                    LIMIT 5
                """).bindparams(bindparam("sds", expanding=True))
                rows = conn.execute(stmt, {"fn": filename, "sds": sds_list}).fetchall()

                for row in rows:
                    micro, sd, md = row[0], row[1], row[2]
                    if micro:
                        add(Recommendation(
                            type="related_concept",
                            label=micro,
                            topic=micro,
                            sub_domain=sd or "",
                            major_domain=md or "",
                            query=f"What is {micro}? Explain for UPSC",
                        ))

            # ── 4. PYQ available — scoped to current sub_domains ────────────
            for sd in list(covered_sub_domains)[:2]:
                row = conn.execute(text("""
                    SELECT COUNT(*) FROM chunks
                    WHERE sub_domain = :sd AND source_type = 'pyq'
                """), {"sd": sd}).fetchone()
                if row and row[0] > 0:
                    label = f"PYQs on {sd}"
                    if label.lower() not in seen_labels:
                        seen_labels.add(label.lower())
                        recommendations.append(Recommendation(
                            type="pyq_available",
                            label=label,
                            topic=sd,
                            sub_domain=sd,
                            major_domain=next(iter(meta["major_domains"]), ""),
                            query=f"Previous year UPSC questions on {sd}",
                        ))

            # ── 5. Current affairs — scoped to current sub_domains ──────────
            for sd in list(covered_sub_domains)[:2]:
                row = conn.execute(text("""
                    SELECT COUNT(*) FROM chunks
                    WHERE sub_domain = :sd AND source_type = 'current_affairs'
                """), {"sd": sd}).fetchone()
                if row and row[0] > 0:
                    label = f"Current Affairs — {sd}"
                    if label.lower() not in seen_labels:
                        seen_labels.add(label.lower())
                        recommendations.append(Recommendation(
                            type="current_affairs",
                            label=label,
                            topic=sd,
                            sub_domain=sd,
                            major_domain=next(iter(meta["major_domains"]), ""),
                            query=f"Recent current affairs related to {sd} for UPSC",
                        ))

    except Exception as e:
        logger.warning(f"⚠️ Recommendations query failed: {e}")

    # Priority: deep_dive first, then related_concept, then pyq/current_affairs
    priority = {"deep_dive": 0, "related_concept": 1, "pyq_available": 2, "current_affairs": 3}
    recommendations.sort(key=lambda r: priority.get(r.type, 9))

    result = recommendations[:_MAX_RECOMMENDATIONS]
    logger.info(f"💡 Generated {len(result)} recommendations (from {len(chunks)} chunks, keywords={keywords})")
    return result
