"""
Question Provenance Database - Track generation metadata for all questions
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class QuestionProvenance(BaseModel):
    """Complete provenance tracking for generated questions"""
    
    # Question content
    question_id: str  # Unique ID
    question_text: str
    options: List[str]
    correct_answer: str
    explanation: str
    
    # Generation metadata
    generated_at: str  # ISO datetime
    model_used: str  # "gpt-4o-mini", "gpt-4o"
    prompt_tokens: int
    completion_tokens: int
    total_cost: float
    
    # Content sources
    source_chunks: List[Dict[str, Any]]  # Chunks used for this question
    source_domains: List[str]  # ["Physical Geography", "Climate"]
    pyq_examples_used: List[str]  # IDs of PYQ examples in prompt
    
    # Quality metrics
    validation_passed: bool
    quality_score: float  # From validation/scoring
    
    # Context
    batch_id: str  # Which batch this came from
    job_id: str  # Which generation job
    difficulty: str
    topics_requested: List[str]
    
    # User feedback (populated later)
    user_rating: Optional[int] = None
    reported_issue: Optional[str] = None


class QuestionBank:
    """Persistent storage for generated questions with provenance"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to backend/data/question_bank.db
            backend_dir = Path(__file__).parent.parent.parent
            data_dir = backend_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "question_bank.db")
        
        self.db_path = db_path
        self._init_db()
        logger.info(f"📚 QuestionBank initialized at {self.db_path}")
    
    def _init_db(self):
        """Create SQLite database with provenance schema"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                question_id TEXT PRIMARY KEY,
                question_text TEXT NOT NULL,
                options TEXT NOT NULL,  -- JSON array
                correct_answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                
                generated_at TEXT NOT NULL,
                model_used TEXT NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_cost REAL,
                
                source_chunks TEXT,  -- JSON array
                source_domains TEXT,  -- JSON array
                pyq_examples_used TEXT,  -- JSON array
                
                validation_passed INTEGER,  -- Boolean as 0/1
                quality_score REAL,
                
                batch_id TEXT,
                job_id TEXT,
                difficulty TEXT,
                topics_requested TEXT,  -- JSON array
                
                user_rating INTEGER,
                reported_issue TEXT
            )
        """)
        
        # Create indexes for common queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_id ON questions(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domains ON questions(source_domains)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_difficulty ON questions(difficulty)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality ON questions(quality_score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_at ON questions(generated_at)")
        
        conn.commit()
        conn.close()
    
    def store_question(self, provenance: QuestionProvenance) -> bool:
        """Store question with full provenance"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO questions (
                    question_id, question_text, options, correct_answer, explanation,
                    generated_at, model_used, prompt_tokens, completion_tokens, total_cost,
                    source_chunks, source_domains, pyq_examples_used,
                    validation_passed, quality_score,
                    batch_id, job_id, difficulty, topics_requested,
                    user_rating, reported_issue
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                provenance.question_id,
                provenance.question_text,
                json.dumps(provenance.options),
                provenance.correct_answer,
                provenance.explanation,
                provenance.generated_at,
                provenance.model_used,
                provenance.prompt_tokens,
                provenance.completion_tokens,
                provenance.total_cost,
                json.dumps(provenance.source_chunks),
                json.dumps(provenance.source_domains),
                json.dumps(provenance.pyq_examples_used),
                1 if provenance.validation_passed else 0,
                provenance.quality_score,
                provenance.batch_id,
                provenance.job_id,
                provenance.difficulty,
                json.dumps(provenance.topics_requested),
                provenance.user_rating,
                provenance.reported_issue
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to store question {provenance.question_id}: {e}")
            return False
    
    def store_batch(self, questions: List[QuestionProvenance]) -> int:
        """Store multiple questions efficiently"""
        stored_count = 0
        for q in questions:
            if self.store_question(q):
                stored_count += 1
        logger.info(f"📝 Stored {stored_count}/{len(questions)} questions in database")
        return stored_count
    
    def get_question(self, question_id: str) -> Optional[QuestionProvenance]:
        """Retrieve a single question by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT * FROM questions WHERE question_id = ?",
                (question_id,)
            )
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            # Convert row to QuestionProvenance
            return self._row_to_provenance(row)
        except Exception as e:
            logger.error(f"❌ Failed to retrieve question {question_id}: {e}")
            return None
    
    def get_by_job(self, job_id: str) -> List[QuestionProvenance]:
        """Get all questions from a specific job"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT * FROM questions WHERE job_id = ? ORDER BY generated_at",
                (job_id,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            return [self._row_to_provenance(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to retrieve questions for job {job_id}: {e}")
            return []
    
    def get_high_quality_questions(
        self,
        domain: Optional[str] = None,
        difficulty: Optional[str] = None,
        min_quality: float = 0.7,
        limit: int = 10
    ) -> List[QuestionProvenance]:
        """Retrieve high-quality questions matching criteria"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            query = """
                SELECT * FROM questions
                WHERE validation_passed = 1 AND quality_score >= ?
            """
            params = [min_quality]
            
            if domain:
                query += " AND source_domains LIKE ?"
                params.append(f'%"{domain}"%')
            
            if difficulty:
                query += " AND difficulty = ?"
                params.append(difficulty)
            
            query += " ORDER BY quality_score DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            return [self._row_to_provenance(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to retrieve high-quality questions: {e}")
            return []
    
    def update_user_feedback(self, question_id: str, rating: int, issue: str = None):
        """Update user feedback for a question"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE questions SET user_rating = ?, reported_issue = ? WHERE question_id = ?",
                (rating, issue, question_id)
            )
            conn.commit()
            conn.close()
            logger.info(f"✅ Updated feedback for question {question_id}")
        except Exception as e:
            logger.error(f"❌ Failed to update feedback: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Total questions
            cursor = conn.execute("SELECT COUNT(*) FROM questions")
            total = cursor.fetchone()[0]
            
            # By difficulty
            cursor = conn.execute("""
                SELECT difficulty, COUNT(*) 
                FROM questions 
                GROUP BY difficulty
            """)
            by_difficulty = dict(cursor.fetchall())
            
            # Average quality
            cursor = conn.execute("SELECT AVG(quality_score) FROM questions WHERE validation_passed = 1")
            avg_quality = cursor.fetchone()[0] or 0
            
            # Total cost
            cursor = conn.execute("SELECT SUM(total_cost) FROM questions")
            total_cost = cursor.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "total_questions": total,
                "by_difficulty": by_difficulty,
                "avg_quality_score": round(avg_quality, 3),
                "total_cost": round(total_cost, 4)
            }
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {}
    
    def _row_to_provenance(self, row) -> QuestionProvenance:
        """Convert database row to QuestionProvenance object"""
        # SQLite returns tuples, need to map to field names
        # Column order matches CREATE TABLE statement
        return QuestionProvenance(
            question_id=row[0],
            question_text=row[1],
            options=json.loads(row[2]),
            correct_answer=row[3],
            explanation=row[4],
            generated_at=row[5],
            model_used=row[6],
            prompt_tokens=row[7],
            completion_tokens=row[8],
            total_cost=row[9],
            source_chunks=json.loads(row[10]) if row[10] else [],
            source_domains=json.loads(row[11]) if row[11] else [],
            pyq_examples_used=json.loads(row[12]) if row[12] else [],
            validation_passed=bool(row[13]),
            quality_score=row[14] or 0.0,
            batch_id=row[15],
            job_id=row[16],
            difficulty=row[17],
            topics_requested=json.loads(row[18]) if row[18] else [],
            user_rating=row[19],
            reported_issue=row[20]
        )


# Global instance
_question_bank_instance = None

def get_question_bank() -> QuestionBank:
    """Get singleton QuestionBank instance"""
    global _question_bank_instance
    if _question_bank_instance is None:
        _question_bank_instance = QuestionBank()
    return _question_bank_instance
