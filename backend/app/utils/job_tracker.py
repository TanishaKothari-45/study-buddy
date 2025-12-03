"""
Job Tracking System - In-memory tracking for async mock test generation
"""
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a mock test generation job"""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    
    # Request parameters
    num_questions: int = 0
    topics: List[str] = field(default_factory=list)
    difficulty: str = "medium"
    
    # Progress tracking
    questions_generated: int = 0
    batches_completed: int = 0
    total_batches: int = 0
    
    # Results
    questions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error handling
    error: Optional[str] = None
    retry_count: int = 0
    
    def update_progress(self, batches_completed: int, questions_generated: int):
        """Update job progress"""
        self.batches_completed = batches_completed
        self.questions_generated = questions_generated
        if self.total_batches > 0:
            self.progress = batches_completed / self.total_batches
    
    def mark_started(self):
        """Mark job as started"""
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.now()
    
    def mark_completed(self, questions: List[Dict[str, Any]]):
        """Mark job as completed"""
        self.status = JobStatus.COMPLETED
        self.questions = questions
        self.completed_at = datetime.now()
        self.progress = 1.0
    
    def mark_failed(self, error: str):
        """Mark job as failed"""
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "progress": round(self.progress, 3),
            "num_questions": self.num_questions,
            "topics": self.topics,
            "difficulty": self.difficulty,
            "questions_generated": self.questions_generated,
            "questions_target": self.num_questions,
            "batches_completed": self.batches_completed,
            "total_batches": self.total_batches,
            "questions": self.questions if self.status == JobStatus.COMPLETED else [],
            "error": self.error if self.status == JobStatus.FAILED else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "elapsed_seconds": (
                (self.completed_at or datetime.now()) - self.created_at
            ).total_seconds() if self.started_at else 0
        }


import sqlite3
import json
from pathlib import Path

class JobStore:
    """Persistent SQLite-backed storage for jobs"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to backend/data/question_bank.db (same as QuestionBank)
            backend_dir = Path(__file__).parent.parent.parent
            data_dir = backend_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "question_bank.db")
            
        self.db_path = db_path
        self._lock = Lock()
        self._cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.time()
        self._init_db()
        logger.info(f"📊 JobStore initialized at {self.db_path}")
    
    def _init_db(self):
        """Create jobs table if not exists"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress REAL,
                    num_questions INTEGER,
                    topics TEXT,  -- JSON array
                    difficulty TEXT,
                    questions_generated INTEGER,
                    batches_completed INTEGER,
                    total_batches INTEGER,
                    questions TEXT,  -- JSON array
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT
                )
            """)
            conn.commit()
            conn.close()

    def _row_to_job(self, row) -> Job:
        """Convert DB row to Job object"""
        if not row:
            return None
            
        return Job(
            job_id=row[0],
            status=JobStatus(row[1]),
            progress=row[2],
            num_questions=row[3],
            topics=json.loads(row[4]) if row[4] else [],
            difficulty=row[5],
            questions_generated=row[6],
            batches_completed=row[7],
            total_batches=row[8],
            questions=json.loads(row[9]) if row[9] else [],
            created_at=datetime.fromisoformat(row[10]) if row[10] else datetime.now(),
            started_at=datetime.fromisoformat(row[11]) if row[11] else None,
            completed_at=datetime.fromisoformat(row[12]) if row[12] else None,
            error=row[13]
        )

    def create_job(
        self,
        job_id: str,
        num_questions: int,
        topics: List[str],
        difficulty: str
    ) -> Job:
        """Create a new job"""
        with self._lock:
            job = Job(
                job_id=job_id,
                num_questions=num_questions,
                topics=topics,
                difficulty=difficulty
            )
            
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT INTO jobs (
                    job_id, status, progress, num_questions, topics, difficulty,
                    questions_generated, batches_completed, total_batches, questions,
                    created_at, started_at, completed_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id, job.status.value, job.progress, job.num_questions,
                json.dumps(job.topics), job.difficulty,
                job.questions_generated, job.batches_completed, job.total_batches,
                json.dumps(job.questions),
                job.created_at.isoformat(),
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.error
            ))
            conn.commit()
            conn.close()
            
            logger.info(f"📋 Created job {job_id}: {num_questions} questions")
            return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            conn.close()
            return self._row_to_job(row)
    
    def update_job(self, job_id: str, **kwargs):
        """Update job attributes"""
        with self._lock:
            # Query database directly to avoid nested lock (deadlock)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return
            
            # Convert row to job object
            job = self._row_to_job(row)

            # Update attributes on the object
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            
            # Persist changes
            conn.execute("""
                UPDATE jobs SET
                    status = ?, progress = ?, questions_generated = ?,
                    batches_completed = ?, total_batches = ?, questions = ?,
                    started_at = ?, completed_at = ?, error = ?
                WHERE job_id = ?
            """, (
                job.status.value, job.progress, job.questions_generated,
                job.batches_completed, job.total_batches, json.dumps(job.questions),
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.error,
                job_id
            ))
            conn.commit()
            conn.close()
    
    def delete_job(self, job_id: str):
        """Delete a job"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            conn.close()
            logger.info(f"🗑️ Deleted job {job_id}")
    
    def cleanup_old_jobs(self, max_age_hours: int = 1):
        """Remove jobs older than max_age_hours"""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        with self._lock:
            cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                DELETE FROM jobs 
                WHERE created_at < ? AND status IN (?, ?)
            """, (cutoff_time, JobStatus.COMPLETED.value, JobStatus.FAILED.value))
            deleted = conn.total_changes
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 Cleaned up {deleted} old jobs")
            self._last_cleanup = current_time
    
    def cleanup_stale_jobs(self):
        """Mark stale 'processing' and 'pending' jobs as failed (from server restart)"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            
            # Find both 'processing' and 'pending' jobs (both can be stale after restart)
            cursor = conn.execute("""
                SELECT job_id, status FROM jobs 
                WHERE status IN (?, ?)
            """, (JobStatus.PROCESSING.value, JobStatus.PENDING.value))
            stale_jobs = cursor.fetchall()
            
            if stale_jobs:
                # Mark all stale jobs as failed
                conn.execute("""
                    UPDATE jobs 
                    SET status = ?, error = ?, completed_at = ?
                    WHERE status IN (?, ?)
                """, (
                    JobStatus.FAILED.value,
                    "Job interrupted by server restart",
                    datetime.now().isoformat(),
                    JobStatus.PROCESSING.value,
                    JobStatus.PENDING.value
                ))
                conn.commit()
                logger.info(f"🧹 Marked {len(stale_jobs)} stale jobs as failed (server restart)")
                for job_id, status in stale_jobs:
                    logger.debug(f"   - {job_id} (was {status})")
            
            conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get job store statistics"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            total = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
            by_status = dict(cursor.fetchall())
            conn.close()
            
            return {
                "total_jobs": total,
                "by_status": by_status
            }


# Global singleton instance
_job_store_instance = None
_job_store_lock = Lock()


def get_job_store() -> JobStore:
    """Get singleton JobStore instance (thread-safe)"""
    global _job_store_instance
    if _job_store_instance is None:
        with _job_store_lock:
            if _job_store_instance is None:  # Double-checked locking
                _job_store_instance = JobStore()
    return _job_store_instance
