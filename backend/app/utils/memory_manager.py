"""
Memory Manager for Study Buddy (Recency + Feedback Memory)

-----------------------------------------------------------
Handles:
  1. Recency filtering → prevents repeated question topics/subtopics
  2. Feedback learning → stores quality-rated questions for style few-shots
"""

import os
import sqlite3
import json
import datetime
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from hashlib import sha256

from ..core.config import settings

logger = logging.getLogger(__name__)

# Use same directory as other databases for consistency
DB_PATH = settings.DB_DIR / "memory.db"

# -------------------------------------------------------------------
# INITIALIZATION
# -------------------------------------------------------------------

def init_memory_db():
    """Initialize memory database with recency and feedback tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recent_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_hash TEXT UNIQUE,
        question_text TEXT,
        topic TEXT,
        subtopic TEXT,
        difficulty TEXT,
        timestamp TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS question_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_hash TEXT UNIQUE,
        question_text TEXT,
        topic TEXT,
        difficulty TEXT,
        quality TEXT,
        reason TEXT,
        timestamp TEXT
    );
    """)

    # Create indexes for faster queries
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recent_timestamp ON recent_questions(timestamp DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_quality ON question_feedback(quality, timestamp DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_topic ON question_feedback(topic)")

    conn.commit()
    conn.close()
    logger.info(f"✅ Memory DB initialized: {DB_PATH}")

# -------------------------------------------------------------------
# UTILITY HELPERS
# -------------------------------------------------------------------

def _hash_question(text: str) -> str:
    """Stable hash to detect near-duplicates."""
    return sha256(text.strip().lower().encode("utf-8")).hexdigest()

# -------------------------------------------------------------------
# RECENCY MEMORY
# -------------------------------------------------------------------

def record_recent_question(question_text: str, topic: str, subtopic: str, difficulty: str):
    """Save generated question to recency memory."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    q_hash = _hash_question(question_text)
    timestamp = datetime.datetime.utcnow().isoformat()

    cur.execute("""
        INSERT OR REPLACE INTO recent_questions (question_hash, question_text, topic, subtopic, difficulty, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (q_hash, question_text, topic, subtopic, difficulty, timestamp))

    conn.commit()
    conn.close()
    logger.debug(f"📝 Recorded recent question: {q_hash[:8]}...")


def get_recent_questions(days: int = 7) -> List[str]:
    """Fetch all recent questions within given number of days."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
    cur.execute("SELECT question_text FROM recent_questions WHERE timestamp > ?", (cutoff,))
    results = [r[0] for r in cur.fetchall()]
    conn.close()
    logger.debug(f"📚 Retrieved {len(results)} recent questions (last {days} days)")
    return results


def filter_recency(chunks: List[Dict[str, Any]], recent_questions: List[str]) -> List[Dict[str, Any]]:
    """Remove chunks semantically close to recent question texts."""
    from difflib import SequenceMatcher

    if not recent_questions:
        logger.info("✅ No recent questions found, no recency filtering applied")
        return chunks

    def is_similar(a, b):
        """Check if two texts are similar (threshold: 0.82)."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.82

    filtered = []
    for chunk in chunks:
        text = chunk.get("content", "")
        if not text:
            filtered.append(chunk)
            continue
        
        # Check similarity with recent questions (compare first 250 chars)
        text_preview = text[:250]
        is_duplicate = False
        for recent_q in recent_questions:
            if is_similar(text_preview, recent_q[:250]):
                is_duplicate = True
                logger.debug(f"   → Filtered chunk (similar to recent question)")
                break
        
        if not is_duplicate:
            filtered.append(chunk)
    
    logger.info(f"🧹 Recency filter: {len(chunks)} → {len(filtered)} chunks kept")
    return filtered

# -------------------------------------------------------------------
# FEEDBACK MEMORY
# -------------------------------------------------------------------

def record_feedback(question_text: str, topic: str, difficulty: str,
                    quality: str, reason: Optional[str] = None):
    """
    Store human feedback (quality = 'high', 'medium', 'low').
    
    Args:
        question_text: The question text
        topic: Topic/subject area
        difficulty: Difficulty level (easy/medium/hard)
        quality: Quality rating ('high', 'medium', 'low')
        reason: Optional reason/comment for the rating
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    q_hash = _hash_question(question_text)
    timestamp = datetime.datetime.utcnow().isoformat()

    cur.execute("""
        INSERT OR REPLACE INTO question_feedback
        (question_hash, question_text, topic, difficulty, quality, reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (q_hash, question_text, topic, difficulty, quality, reason, timestamp))

    conn.commit()
    conn.close()
    logger.info(f"⭐ Feedback stored for {quality.upper()} quality question: {q_hash[:8]}...")


def get_high_quality_examples(limit: int = 3, topic: Optional[str] = None, 
                             difficulty: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return top high-quality questions for few-shot style reference.
    
    Args:
        limit: Maximum number of examples to return
        topic: Optional filter by topic
        difficulty: Optional filter by difficulty
    
    Returns:
        List of high-quality question examples
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    query = """
        SELECT question_text, topic, difficulty, reason
        FROM question_feedback
        WHERE quality='high'
    """
    params = []
    
    if topic:
        query += " AND topic = ?"
        params.append(topic)
    
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    results = [{"text": r[0], "topic": r[1], "difficulty": r[2], "reason": r[3]} 
               for r in cur.fetchall()]
    conn.close()
    
    logger.info(f"⭐ Retrieved {len(results)} high-quality examples")
    return results

