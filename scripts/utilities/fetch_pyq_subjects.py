"""
Fetch ALL chunks from Pinecone and report which subjects they belong to,
broken down by source_type (pyq / concept / current_affairs / …).

Usage:
    cd backend && ../venv/bin/python3.11 ../scripts/utilities/fetch_pyq_subjects.py
"""
import os
import sys
import logging
from collections import defaultdict
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# The master .env with all API keys lives at the project root
from dotenv import load_dotenv
root_env = project_root / ".env"
backend_env = project_root / "backend" / ".env"

# Load root first (has PINECONE_API_KEY, OPENAI_API_KEY, etc.)
if root_env.exists():
    load_dotenv(dotenv_path=root_env)
    print(f"✅ Loaded env from {root_env}")
# Also overlay backend/.env in case it has extras (won't override already-set vars)
if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
    print(f"✅ Overlaid env from {backend_env}")

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Main ──────────────────────────────────────────────────────────────────────
def fetch_all_subjects():
    """
    Iterate over ALL vectors in Pinecone and report subjects + source_types.

    Strategy:
      1. Try Pinecone's list() + batch fetch() (clean pagination).
      2. Fall back to a zero-vector query (no filter) if list() fails.
    """
    from pinecone import Pinecone

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        logger.error("❌ PINECONE_API_KEY not set")
        sys.exit(1)

    index_name = os.getenv("PINECONE_INDEX_NAME", "study-buddy")
    logger.info(f"🔗 Connecting to Pinecone index: {index_name}")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    # ── Quick sanity check ─────────────────────────────────────────────────
    stats = index.describe_index_stats()
    total_vectors = stats.get("total_vector_count", 0)
    logger.info(f"📊 Total vectors in index: {total_vectors}")

    # ── Collect all PYQ chunk metadata ────────────────────────────────────
    all_metadata: list[dict] = []

    # -- Method 1: paginated list() + fetch() (preferred, O(n) not O(n²))
    try:
        logger.info("🔄 Using list() API to enumerate PYQ vectors …")
        pyq_ids: list[str] = []

        # list() returns all vector IDs with an optional prefix filter.
        # We gather all IDs first, then batch-fetch metadata.
        all_ids: list[str] = []
        for page in index.list(limit=99):            # Pinecone max < 100 per page
            if isinstance(page, list):
                all_ids.extend(page)
            else:
                all_ids.extend(getattr(page, "vectors", page) or [])

        logger.info(f"   Found {len(all_ids)} total IDs – fetching metadata …")

        FETCH_BATCH = 99
        for start in range(0, len(all_ids), FETCH_BATCH):
            batch = all_ids[start : start + FETCH_BATCH]
            resp = index.fetch(ids=batch)
            for vec_id, vec in resp.vectors.items():
                all_metadata.append(vec.metadata or {})

        logger.info(f"   ✅ Fetched metadata for {len(all_metadata)} chunks via list()+fetch()")

    except Exception as list_err:
        logger.warning(f"⚠️  list() approach failed ({list_err}); falling back to query …")
        all_metadata = []

        # -- Method 2: zero-vector query, no filter → fetch everything
        dim = 1536  # OpenAI text-embedding-3-small dimension
        dummy_vector = [0.0] * dim
        top_k = min(10_000, total_vectors or 10_000)

        results = index.query(
            vector=dummy_vector,
            top_k=top_k,
            include_metadata=True,
        )
        for match in results.matches:
            all_metadata.append(match.metadata or {})

        logger.info(f"   ✅ Fetched {len(all_metadata)} chunks via query()")

    if not all_metadata:
        logger.warning("⚠️  No PYQ chunks found in Pinecone.")
        return

    # ── Aggregate ──────────────────────────────────────────────────────────
    # subject → { source_type → count }
    subject_type_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    subject_files: dict[str, set] = defaultdict(set)

    unclassified: list[dict] = []

    for meta in all_metadata:
        subject     = meta.get("subject") or meta.get("major_domain") or "UNKNOWN"
        source_type = meta.get("source_type", "unknown")
        filename    = meta.get("filename", "unknown_file")

        subject_type_counts[subject][source_type] += 1
        subject_files[subject].add(filename)

        if subject == "UNKNOWN":
            unclassified.append(meta)

    # ── Print Report ──────────────────────────────────────────────────────
    subject_totals = {s: sum(t.values()) for s, t in subject_type_counts.items()}

    print("\n" + "=" * 70)
    print(f"  ALL CHUNKS — SUBJECT REPORT  ({len(all_metadata)} total chunks)")
    print("=" * 70)

    for subject in sorted(subject_type_counts.keys()):
        type_counts = subject_type_counts[subject]
        total       = sum(type_counts.values())
        files       = subject_files[subject]

        print(f"\n📚 Subject : {subject}  ({total} chunks)")
        for stype, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"   {'':3}{stype:<20} {cnt:>5} chunks")
        print(f"   Files ({len(files)}):")
        for f in sorted(files):
            print(f"      • {f}")

    print("\n" + "=" * 70)
    print(f"  SUMMARY")
    print("=" * 70)
    print(f"  Total chunks    : {len(all_metadata)}")
    print(f"  Unique subjects : {len(subject_type_counts)}")
    for s, c in sorted(subject_totals.items(), key=lambda x: -x[1]):
        print(f"    {c:>6}  {s}")
    if unclassified:
        print(f"\n  ⚠️  {len(unclassified)} chunks with UNKNOWN subject — sample metadata:")
        for m in unclassified[:3]:
            print(f"    {m}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    fetch_all_subjects()
