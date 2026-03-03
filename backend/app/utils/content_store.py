"""
Content Store for storing full chunk content locally or in Cloud SQL.
This complements Pinecone by storing full text (no embeddings).
"""
import logging
import json
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from ..core.database import engine

logger = logging.getLogger(__name__)


class ContentStore:
    """
    Stores full chunk content in shared database (Postgres or SQLite).
    Used to complement Pinecone which only stores content_preview.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize content store using the shared application engine"""
        # We ignore db_path as we now use the shared engine from app.core.database
        self.engine = engine
        
        # Initialize database and create table if needed
        self._init_database()
        
        logger.info("✅ Content store initialized (using shared database engine)")
    
    def _init_database(self):
        """Create database table if it doesn't exist"""
        try:
            with self.engine.begin() as conn:
                # Create table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id SERIAL PRIMARY KEY,
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
                """))
                
                # Create indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chunk_filename ON chunks(chunk_id, filename)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_filename ON chunks(filename)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_source_type ON chunks(source_type)"))
                
                logger.debug("✅ ContentStore table and indexes verified")
        except Exception as e:
            # Handle SQLite vs Postgres differences in syntax if necessary
            # SERIAL vs AUTOINCREMENT etc.
            # actually SERIAL is postgres, SQLite uses INTEGER PRIMARY KEY AUTOINCREMENT
            # But SQLAlchemy handles some of this if we were using Models. 
            # Since we use raw SQL, we might need a fallback.
            if "SERIAL" in str(e) and "sqlite" in str(self.engine.url).lower():
                with self.engine.begin() as conn:
                    conn.execute(text("""
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
                    """))
                    logger.debug("✅ ContentStore table verified (SQLite fallback)")
            else:
                logger.error(f"❌ Failed to initialize ContentStore database: {e}")
    
    def store_chunk(self, chunk_id: str, filename: str, full_content: str, 
                    chapter: Optional[str] = None, section: Optional[str] = None,
                    content_preview: Optional[str] = None,
                    major_domain: Optional[str] = None,
                    sub_domain: Optional[str] = None,
                    micro_topic: Optional[str] = None,
                    sub_topics: Optional[List[str]] = None,
                    source_type: Optional[str] = None,
                    source_subtype: Optional[str] = None) -> bool:
        """Store a chunk's full content using SQLAlchemy"""
        try:
            if not content_preview:
                content_preview = full_content[:300] if len(full_content) > 300 else full_content
            
            sub_topics_str = json.dumps(sub_topics) if sub_topics else None

            # Logic to detect source_type if missing
            if source_type is None:
                from .metadata_enricher import detect_source_type
                source_info = detect_source_type(filename)
                source_type = source_info.get("source_type")
                source_subtype = source_info.get("source_subtype")

            with self.engine.begin() as conn:
                # Use UPSERT logic (Postgres style)
                # For SQLite it might need different syntax, but we'll try standard INSERT OR REPLACE or similar
                # To be truly cross-platform we can do DELETE then INSERT or use appropriate syntax
                
                if "sqlite" in str(self.engine.url).lower():
                    query = text("""
                        INSERT OR REPLACE INTO chunks 
                        (chunk_id, filename, chapter, section, full_content, content_length, content_preview,
                         major_domain, sub_domain, micro_topic, sub_topics, source_type, source_subtype)
                        VALUES (:cid, :fname, :chap, :sec, :cont, :clen, :prev, :maj, :sub, :mic, :topics, :stype, :ssub)
                    """)
                else:
                    # Postgres UPSERT
                    query = text("""
                        INSERT INTO chunks 
                        (chunk_id, filename, chapter, section, full_content, content_length, content_preview,
                         major_domain, sub_domain, micro_topic, sub_topics, source_type, source_subtype)
                        VALUES (:cid, :fname, :chap, :sec, :cont, :clen, :prev, :maj, :sub, :mic, :topics, :stype, :ssub)
                        ON CONFLICT (chunk_id, filename) DO UPDATE SET
                        full_content = EXCLUDED.full_content,
                        content_length = EXCLUDED.content_length,
                        content_preview = EXCLUDED.content_preview,
                        major_domain = EXCLUDED.major_domain,
                        sub_domain = EXCLUDED.sub_domain,
                        micro_topic = EXCLUDED.micro_topic,
                        sub_topics = EXCLUDED.sub_topics,
                        source_type = EXCLUDED.source_type,
                        source_subtype = EXCLUDED.source_subtype
                    """)

                conn.execute(query, {
                    "cid": chunk_id, "fname": filename, "chap": chapter, "sec": section,
                    "cont": full_content, "clen": len(full_content), "prev": content_preview,
                    "maj": major_domain, "sub": sub_domain, "mic": micro_topic,
                    "topics": sub_topics_str, "stype": source_type, "ssub": source_subtype
                })
            
            logger.debug(f"✅ Stored chunk: {chunk_id} in {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to store chunk {chunk_id}: {e}")
            return False

    def get_chunk(self, chunk_id: str, filename: str, chapter: Optional[str] = None) -> Optional[str]:
        """Retrieve full content for a chunk with explicit logging"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT full_content FROM chunks
                    WHERE chunk_id = :cid AND filename = :fname
                    LIMIT 1
                """)
                result = conn.execute(query, {"cid": chunk_id, "fname": filename}).fetchone()
                
                if result:
                    content = result[0]
                    logger.info(f"🟢 [STORE-HIT] Retrieved FULL TEXT ({len(content)} chars) for {chunk_id}")
                    return content
                
            logger.warning(f"🔴 [STORE-MISS] No full content found in shared DB for {chunk_id} in {filename}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to retrieve chunk {chunk_id}: {e}")
            return None

    def get_enriched_chunk(self, chunk_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Retrieve full content and metadata for a chunk"""
        logger.debug(f"🔍 [ENRICH-LOOKUP] Searching for chunk_id='{chunk_id}', filename='{filename}'")
        try:
            with self.engine.connect() as conn:
                query = text("SELECT * FROM chunks WHERE chunk_id = :cid AND filename = :fname LIMIT 1")
                result = conn.execute(query, {"cid": chunk_id, "fname": filename}).fetchone()
                
                if result:
                    # Convert row to dict
                    res = dict(result._mapping)
                    logger.info(f"🟢 [ENRICH-HIT] Found enriched chunk for {chunk_id}")
                    if res.get("sub_topics"):
                        try:
                            res["sub_topics"] = json.loads(res["sub_topics"])
                        except:
                            pass
                    return res
                else:
                    logger.warning(f"🔴 [ENRICH-MISS] No match for chunk_id='{chunk_id}', filename='{filename}'")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to retrieve enriched chunk {chunk_id}: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            with self.engine.connect() as conn:
                total_chunks = conn.execute(text("SELECT COUNT(*) FROM chunks")).scalar()
                total_files = conn.execute(text("SELECT COUNT(DISTINCT filename) FROM chunks")).scalar()
                total_chars = conn.execute(text("SELECT SUM(content_length) FROM chunks")).scalar() or 0
                
            return {
                "total_chunks": total_chunks,
                "total_files": total_files,
                "total_characters": total_chars,
                "engine": str(self.engine.url)
            }
        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {"error": str(e)}

    def batch_store(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Store multiple chunks in batch"""
        success_count = 0
        failures = []
        
        # Simple implementation for now (can be optimized with executemany)
        for chunk in chunks:
            res = self.store_chunk(
                chunk_id=chunk.get("chunk_id"),
                filename=chunk.get("filename"),
                full_content=chunk.get("content", ""),
                chapter=chunk.get("chapter"),
                section=chunk.get("section"),
                major_domain=chunk.get("major_domain"),
                sub_domain=chunk.get("sub_domain"),
                micro_topic=chunk.get("micro_topic"),
                sub_topics=chunk.get("sub_topics"),
                source_type=chunk.get("source_type"),
                source_subtype=chunk.get("source_subtype")
            )
            if res:
                success_count += 1
            else:
                failures.append(chunk.get("chunk_id", "unknown"))
        
        return {"success": success_count, "failed": len(failures), "failures": failures}
