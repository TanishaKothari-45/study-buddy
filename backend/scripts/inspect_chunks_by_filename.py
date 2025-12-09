#!/usr/bin/env python3
"""
Inspect chunks from SQLite content store by filename.
Shows how chunks are created and stored.
"""
import sqlite3
import json
from pathlib import Path
import sys

# Add backend to path (parent of scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

def inspect_chunks_by_filename(filename: str, limit: int = 10, show_content: bool = False):
    """
    Inspect chunks from SQLite content store for a specific filename.
    
    Args:
        filename: Filename to search for (supports partial match)
        limit: Maximum number of chunks to display (default: 10)
        show_content: If True, show full content (default: False, shows preview only)
    """
    # Get database path
    db_path = settings.DB_DIR / "content_store.db"
    
    if not db_path.exists():
        print(f"❌ Content store database not found at: {db_path}")
        print("   Make sure you've uploaded files to the content store first.")
        return
    
    print(f"📂 Database: {db_path}")
    print(f"🔍 Searching for filename containing: '{filename}'")
    print("=" * 80)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()
    
    # Query chunks by filename (case-insensitive partial match)
    cursor.execute("""
        SELECT 
            chunk_id,
            filename,
            chapter,
            section,
            content_length,
            content_preview,
            full_content,
            major_domain,
            sub_domain,
            micro_topic,
            sub_topics,
            created_at
        FROM chunks
        WHERE filename LIKE ?
        ORDER BY chunk_id
        LIMIT ?
    """, (f"%{filename}%", limit * 2))  # Get more to account for splits
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"⚠️  No chunks found for filename containing '{filename}'")
        
        # Show available filenames
        cursor.execute("SELECT DISTINCT filename FROM chunks LIMIT 20")
        available = cursor.fetchall()
        if available:
            print("\n📋 Available filenames in database:")
            for row in available:
                print(f"   • {row[0]}")
        conn.close()
        return
    
    print(f"✅ Found {len(rows)} chunks\n")
    
    # Group by base chunk_id (to show splits together)
    chunks_by_base = {}
    for row in rows:
        chunk_id = row['chunk_id']
        base_id = chunk_id.rsplit('_split', 1)[0] if '_split' in chunk_id else chunk_id
        
        if base_id not in chunks_by_base:
            chunks_by_base[base_id] = []
        chunks_by_base[base_id].append(row)
    
    # Display chunks
    displayed = 0
    for base_id, chunk_group in sorted(chunks_by_base.items())[:limit]:
        if displayed >= limit:
            break
        
        # Sort chunks in group (handle splits)
        chunk_group.sort(key=lambda r: r['chunk_id'])
        
        for chunk in chunk_group:
            if displayed >= limit:
                break
            
            print(f"\n{'='*80}")
            print(f"📄 Chunk ID: {chunk['chunk_id']}")
            print(f"   Filename: {chunk['filename']}")
            print(f"   Chapter: {chunk['chapter'] or 'N/A'}")
            print(f"   Section: {chunk['section'] or 'N/A'}")
            print(f"   Length: {chunk['content_length']} characters ({chunk['content_length']//4} ~tokens)")
            
            # Show domain metadata prominently
            print(f"\n   📊 Domain Metadata:")
            if chunk['major_domain']:
                print(f"      🌍 Major Domain: {chunk['major_domain']}")
            else:
                print(f"      🌍 Major Domain: (not set)")
            
            if chunk['sub_domain']:
                print(f"      📍 Sub-domain: {chunk['sub_domain']}")
            else:
                print(f"      📍 Sub-domain: (not set)")
            
            if chunk['micro_topic']:
                print(f"      🔬 Micro-topic: {chunk['micro_topic']}")
            
            if chunk['sub_topics']:
                try:
                    sub_topics = json.loads(chunk['sub_topics'])
                    if sub_topics:
                        print(f"      📚 Sub-topics: {', '.join(sub_topics[:5])}{'...' if len(sub_topics) > 5 else ''}")
                except:
                    if chunk['sub_topics']:
                        print(f"      📚 Sub-topics: {chunk['sub_topics']}")
            
            print(f"   Created: {chunk['created_at']}")
            
            # Show content preview or full content
            if show_content:
                print(f"\n   📝 Full Content ({chunk['content_length']} chars):")
                print(f"   {'-'*76}")
                content = chunk['full_content']
                # Show first 500 chars + last 200 chars if too long
                if len(content) > 700:
                    print(f"   {content[:500]}...")
                    print(f"   ... [truncated {len(content) - 700} chars] ...")
                    print(f"   ...{content[-200:]}")
                else:
                    print(f"   {content}")
                print(f"   {'-'*76}")
            else:
                preview = chunk['content_preview']
                print(f"\n   📝 Preview ({len(preview)} chars):")
                print(f"   {preview[:200]}{'...' if len(preview) > 200 else ''}")
            
            displayed += 1
    
    # Get domain distribution for ALL chunks (not just displayed)
    cursor.execute("""
        SELECT major_domain, sub_domain, COUNT(*) as count
        FROM chunks
        WHERE filename LIKE ?
        GROUP BY major_domain, sub_domain
        ORDER BY count DESC
        LIMIT 10
    """, (f"%{filename}%",))
    
    domain_distribution = cursor.fetchall()
    
    # Close connection after all queries
    conn.close()
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 Summary:")
    print(f"   • Total chunks found: {len(rows)}")
    print(f"   • Unique base chunk IDs: {len(chunks_by_base)}")
    print(f"   • Chunks displayed: {displayed}")
    
    # Check for split chunks
    split_chunks = [r for r in rows if '_split' in r['chunk_id']]
    if split_chunks:
        print(f"   • Split chunks: {len(split_chunks)}")
        print(f"     (Chunks that were split due to length > 1500 words)")
    
    # Domain distribution summary
    if domain_distribution:
        print(f"\n📈 Domain Distribution:")
        for dist in domain_distribution:
            major = dist['major_domain'] or '(not set)'
            sub = dist['sub_domain'] or '(not set)'
            count = dist['count']
            print(f"   • {major} → {sub}: {count} chunks")
    
    print(f"\n💡 Tip: Use --show-content to see full chunk content")
    print(f"💡 Tip: Use --limit N to show more chunks")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Inspect chunks from SQLite content store by filename")
    parser.add_argument("filename", help="Filename to search for (supports partial match)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of chunks to display (default: 10)")
    parser.add_argument("--show-content", action="store_true", help="Show full content instead of preview")
    
    args = parser.parse_args()
    
    inspect_chunks_by_filename(args.filename, args.limit, args.show_content)

