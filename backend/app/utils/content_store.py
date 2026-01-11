"""
Content Store for storing full chunk content locally using SQLite.
This complements Pinecone by storing full text (no embeddings).
Used for RetrievalQA chains that need full context.
"""
import logging
import os
import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path
from ..core.config import settings

logger = logging.getLogger(__name__)


class ContentStore:
    """
    Stores full chunk content in SQLite database (simple, fast, lightweight).
    Used to complement Pinecone which only stores content_preview.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize content store with SQLite database"""
        if db_path is None:
            # Use same directory as ChromaDB for consistency
            db_path = settings.DB_DIR / "content_store.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database and create table if needed
        self._init_database()
        
        logger.info(f"✅ Content store initialized: {self.db_path}")
    
    def _init_database(self):
        """Create database table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # ============================================================
        # Enable WAL mode for better concurrent read performance
        # ============================================================
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
        cursor.execute("PRAGMA cache_size=-64000")   # 64MB cache for better performance
        cursor.execute("PRAGMA temp_store=MEMORY")   # Use RAM for temp tables
        cursor.execute("PRAGMA mmap_size=268435456") # 256MB memory-mapped I/O
        
        logger.info("✅ SQLite optimizations enabled: WAL mode + 64MB cache + memory-mapped I/O")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                chapter TEXT,
                section TEXT,
                full_content TEXT NOT NULL,
                content_length INTEGER NOT NULL,
                content_preview TEXT NOT NULL,
                major_domain TEXT,
                sub_domain TEXT,
                micro_topic TEXT,
                sub_topics TEXT,
                source_type TEXT,
                source_subtype TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chunk_id, filename)
            )
        """)
        
        # Add domain metadata columns if they don't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN major_domain TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN sub_domain TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN micro_topic TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN sub_topics TEXT")
        except sqlite3.OperationalError:
            pass
        
        # Add source_type and source_subtype columns if they don't exist
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN source_type TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE chunks ADD COLUMN source_subtype TEXT")
        except sqlite3.OperationalError:
            pass
        
        # Create indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_filename ON chunks(chunk_id, filename)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filename ON chunks(filename)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapter ON chunks(chapter)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_major_domain ON chunks(major_domain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sub_domain ON chunks(sub_domain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_type ON chunks(source_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_subtype ON chunks(source_subtype)")
        
        conn.commit()
        conn.close()
    
    def store_chunk(self, chunk_id: str, filename: str, full_content: str, 
                    chapter: Optional[str] = None, section: Optional[str] = None,
                    content_preview: Optional[str] = None,
                    major_domain: Optional[str] = None,
                    sub_domain: Optional[str] = None,
                    micro_topic: Optional[str] = None,
                    sub_topics: Optional[List[str]] = None,
                    source_type: Optional[str] = None,
                    source_subtype: Optional[str] = None) -> bool:
        """
        Store a chunk's full content.
        
        Args:
            chunk_id: Unique chunk identifier
            filename: Source filename
            full_content: Full chunk text content
            chapter: Chapter name (optional, for matching)
            section: Section name (optional, for matching)
            content_preview: First 300 chars (for matching, auto-generated if not provided)
            major_domain: Major domain classification (optional, copied from Pinecone)
            sub_domain: Sub domain classification (optional, copied from Pinecone)
            micro_topic: Micro topic classification (optional, copied from Pinecone)
            sub_topics: List of sub topics (optional, copied from Pinecone, stored as JSON string)
            source_type: Source type (pyq, current_affairs, concept) - auto-detected from filename if not provided
            source_subtype: Source subtype (ncert, topic, None) - auto-detected from filename if not provided
        
        Returns:
            True if stored successfully
        """
        try:
            # Generate content_preview if not provided
            if not content_preview:
                content_preview = full_content[:300] if len(full_content) > 300 else full_content
            
            # Convert sub_topics list to JSON string if provided
            sub_topics_str = None
            if sub_topics:
                import json
                sub_topics_str = json.dumps(sub_topics) if isinstance(sub_topics, list) else str(sub_topics)
            
            # Auto-detect source_type and source_subtype from filename if not provided
            if source_type is None or source_subtype is None:
                from .metadata_enricher import detect_source_type
                source_info = detect_source_type(filename)
                if source_type is None:
                    source_type = source_info.get("source_type")
                if source_subtype is None:
                    source_subtype = source_info.get("source_subtype")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Use INSERT OR REPLACE to handle duplicates
            cursor.execute("""
                INSERT OR REPLACE INTO chunks 
                (chunk_id, filename, chapter, section, full_content, content_length, content_preview,
                 major_domain, sub_domain, micro_topic, sub_topics, source_type, source_subtype)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                filename,
                chapter,
                section,
                full_content,
                len(full_content),
                content_preview,
                major_domain,
                sub_domain,
                micro_topic,
                sub_topics_str,
                source_type,
                source_subtype
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"✅ Stored chunk: {chunk_id} in {filename} ({len(full_content)} chars)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store chunk {chunk_id}: {e}")
            return False
    
    def get_chunk(self, chunk_id: str, filename: str, 
                  chapter: Optional[str] = None) -> Optional[str]:
        """
        Retrieve full content for a chunk.
        
        Args:
            chunk_id: Chunk identifier
            filename: Source filename
            chapter: Chapter name (optional, for better matching)
        
        Returns:
            Full content string, or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Try exact match first (chunk_id + filename)
            if chapter:
                cursor.execute("""
                    SELECT full_content FROM chunks
                    WHERE chunk_id = ? AND filename = ? AND chapter = ?
                    LIMIT 1
                """, (chunk_id, filename, chapter))
            else:
                cursor.execute("""
                    SELECT full_content FROM chunks
                    WHERE chunk_id = ? AND filename = ?
                    LIMIT 1
                """, (chunk_id, filename))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            
            # If not found with chapter, try without chapter
            if chapter:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT full_content FROM chunks
                    WHERE chunk_id = ? AND filename = ?
                    LIMIT 1
                """, (chunk_id, filename))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    logger.debug(f"⚠️ Found chunk without chapter match: {chunk_id}")
                    return result[0]
            
            logger.debug(f"⚠️ Chunk not found: {chunk_id} in {filename}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve chunk {chunk_id}: {e}")
            return None
    
    def match_chunk(self, chunk_id: str, filename: str, content_length: int,
                   content_preview: str, chapter: Optional[str] = None,
                   tolerance: int = 10) -> Optional[Dict[str, Any]]:
        """
        Find matching chunk using multiple criteria.
        
        Args:
            chunk_id: Chunk identifier
            filename: Source filename
            content_length: Expected content length
            content_preview: First 300 chars for matching
            chapter: Chapter name (preferred but not required)
            tolerance: Length tolerance in chars (default: 10)
        
        Returns:
            Dict with full_content and metadata, or None if no match
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query - prefer chapter match if provided
            if chapter:
                cursor.execute("""
                    SELECT full_content, content_length, content_preview, chapter, section
                    FROM chunks
                    WHERE chunk_id = ? AND filename = ? AND chapter = ?
                """, (chunk_id, filename, chapter))
            else:
                cursor.execute("""
                    SELECT full_content, content_length, content_preview, chapter, section
                    FROM chunks
                    WHERE chunk_id = ? AND filename = ?
                """, (chunk_id, filename))
            
            candidates = cursor.fetchall()
            
            # If no results with chapter, try without chapter
            if not candidates and chapter:
                cursor.execute("""
                    SELECT full_content, content_length, content_preview, chapter, section
                    FROM chunks
                    WHERE chunk_id = ? AND filename = ?
                """, (chunk_id, filename))
                candidates = cursor.fetchall()
            
            conn.close()
            
            # Match by length and preview
            for row in candidates:
                stored_content, stored_length, stored_preview, stored_chapter, stored_section = row
                
                # Check length match (within tolerance)
                length_match = abs(stored_length - content_length) <= tolerance
                
                # Check preview match (first 300 chars)
                preview_match = stored_preview[:300] == content_preview[:300]
                
                if length_match and preview_match:
                    logger.debug(f"✅ Matched chunk: {chunk_id} (length: {stored_length}, preview match: {preview_match})")
                    return {
                        "full_content": stored_content,
                        "metadata": {
                            "chunk_id": chunk_id,
                            "filename": filename,
                            "chapter": stored_chapter,
                            "section": stored_section,
                            "content_length": stored_length
                        },
                        "match_quality": "exact" if chapter and stored_chapter == chapter else "good"
                    }
            
            logger.debug(f"⚠️ No match found for chunk: {chunk_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to match chunk {chunk_id}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get content store statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM chunks")
            total_chunks = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT filename) FROM chunks")
            total_files = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(content_length) FROM chunks")
            total_chars = cursor.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "total_chunks": total_chunks,
                "total_files": total_files,
                "total_characters": total_chars,
                "database_path": str(self.db_path)
            }
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {"error": str(e)}
    
    def batch_store(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Store multiple chunks in batch.
        
        Args:
            chunks: List of dicts with keys: chunk_id, filename, content, chapter, section, source_type, source_subtype
        
        Returns:
            Dict with success count and failures
        """
        success_count = 0
        failures = []
        
        from .metadata_enricher import detect_source_type
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            for chunk in chunks:
                try:
                    chunk_id = chunk.get("chunk_id")
                    filename = chunk.get("filename")
                    content = chunk.get("content", "")
                    chapter = chunk.get("chapter")
                    section = chunk.get("section")
                    content_preview = chunk.get("content_preview", content[:300])
                    
                    # Get source_type and source_subtype from chunk metadata or auto-detect
                    source_type = chunk.get("source_type")
                    source_subtype = chunk.get("source_subtype")
                    
                    # Auto-detect if not provided
                    if source_type is None or source_subtype is None:
                        source_info = detect_source_type(filename)
                        if source_type is None:
                            source_type = source_info.get("source_type")
                        if source_subtype is None:
                            source_subtype = source_info.get("source_subtype")
                    
                    if not chunk_id or not filename or not content:
                        failures.append(chunk_id or "unknown")
                        continue
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO chunks 
                        (chunk_id, filename, chapter, section, full_content, content_length, content_preview,
                         source_type, source_subtype)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        chunk_id,
                        filename,
                        chapter,
                        section,
                        content,
                        len(content),
                        content_preview,
                        source_type,
                        source_subtype
                    ))
                    success_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to store chunk in batch: {e}")
                    failures.append(chunk.get("chunk_id", "unknown"))
            
            conn.commit()
        finally:
            conn.close()
        
        return {
            "success": success_count,
            "failed": len(failures),
            "failures": failures
        }
