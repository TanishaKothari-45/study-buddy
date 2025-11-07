#!/usr/bin/env python3
"""
Script to inspect stored chunks in ChromaDB with all their metadata.
This helps understand the foundation for improving mock prelims questions.
"""

import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.utils.chroma_handler import ChromaHandler
from app.core.config import settings

def inspect_chunks(collection_name: str = "geography_docs_enriched", limit: int = 10):
    """Inspect chunks from the specified collection"""
    print(f"🔍 Inspecting chunks from collection: {collection_name}")
    print("=" * 80)
    
    try:
        handler = ChromaHandler()
        handler.switch_to_collection(collection_name)
        
        # Get collection stats
        stats = handler.get_stats()
        print(f"\n📊 Collection Statistics:")
        print(f"   Total chunks: {stats.get('total_chunks', 0)}")
        print(f"   Collection name: {stats.get('collection_name', 'N/A')}")
        
        # Get sample chunks
        print(f"\n📄 Sample Chunks (showing first {limit}):")
        print("=" * 80)
        
        all_docs = handler.get_all_documents_paginated(batch_size=limit)
        sample_docs = all_docs[:limit]
        
        for i, doc in enumerate(sample_docs, 1):
            print(f"\n{'─' * 80}")
            print(f"Chunk #{i}")
            print(f"{'─' * 80}")
            
            # ID
            print(f"📌 ID: {doc.get('id', 'N/A')}")
            
            # Content preview
            content = doc.get('content', '')
            content_preview = content[:200] + "..." if len(content) > 200 else content
            print(f"\n📝 Content Preview ({len(content)} chars):")
            print(f"   {content_preview}")
            
            # Metadata
            metadata = doc.get('metadata', {})
            print(f"\n🏷️  Metadata ({len(metadata)} fields):")
            for key, value in sorted(metadata.items()):
                # Format value nicely
                if isinstance(value, str) and len(value) > 100:
                    value_display = value[:100] + "..."
                else:
                    value_display = value
                print(f"   • {key:20s}: {value_display}")
            
            # Metadata summary
            print(f"\n📋 Metadata Summary:")
            print(f"   • Subject: {metadata.get('subject', 'N/A')}")
            print(f"   • Major Domain: {metadata.get('major_domain', 'N/A')}")
            print(f"   • Sub Domain: {metadata.get('sub_domain', 'N/A')}")
            print(f"   • Difficulty: {metadata.get('difficulty', 'N/A')}")
            print(f"   • Chapter: {metadata.get('chapter', 'N/A')}")
            print(f"   • Section: {metadata.get('section', 'N/A')}")
            print(f"   • Filename: {metadata.get('filename', 'N/A')}")
            print(f"   • Chunk ID: {metadata.get('chunk_id', 'N/A')}")
            if 'summary' in metadata:
                summary = metadata.get('summary', '')
                summary_preview = summary[:150] + "..." if len(summary) > 150 else summary
                print(f"   • Summary: {summary_preview}")
        
        # Metadata field analysis
        print(f"\n{'=' * 80}")
        print(f"📊 Metadata Field Analysis (across all chunks):")
        print(f"{'=' * 80}")
        
        all_metadata_keys = set()
        metadata_counts = {}
        
        for doc in all_docs:
            meta = doc.get('metadata', {})
            for key in meta.keys():
                all_metadata_keys.add(key)
                metadata_counts[key] = metadata_counts.get(key, 0) + 1
        
        print(f"\nTotal unique metadata fields: {len(all_metadata_keys)}")
        print(f"\nField frequency (how many chunks have each field):")
        for key in sorted(all_metadata_keys):
            count = metadata_counts.get(key, 0)
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            print(f"   • {key:25s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        # Domain distribution
        print(f"\n{'=' * 80}")
        print(f"🌍 Domain Distribution:")
        print(f"{'=' * 80}")
        
        major_domains = {}
        sub_domains = {}
        difficulties = {}
        
        for doc in all_docs:
            meta = doc.get('metadata', {})
            
            major = meta.get('major_domain', 'Unknown')
            sub = meta.get('sub_domain', 'Unknown')
            diff = meta.get('difficulty', 'Unknown')
            
            major_domains[major] = major_domains.get(major, 0) + 1
            sub_domains[sub] = sub_domains.get(sub, 0) + 1
            difficulties[diff] = difficulties.get(diff, 0) + 1
        
        print(f"\nMajor Domains:")
        for domain, count in sorted(major_domains.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            print(f"   • {domain:30s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        print(f"\nSub Domains (top 10):")
        for domain, count in sorted(sub_domains.items(), key=lambda x: x[1], reverse=True)[:10]:
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            print(f"   • {domain:30s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        print(f"\nDifficulty Levels:")
        for diff, count in sorted(difficulties.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            print(f"   • {diff:30s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        # Export sample to JSON for detailed inspection
        export_file = "chunk_inspection_sample.json"
        sample_export = []
        for doc in sample_docs:
            sample_export.append({
                "id": doc.get("id"),
                "content": doc.get("content"),
                "metadata": doc.get("metadata")
            })
        
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(sample_export, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Sample chunks exported to: {export_file}")
        print(f"\n{'=' * 80}")
        print(f"✨ Inspection complete!")
        print(f"{'=' * 80}")
        
    except Exception as e:
        print(f"❌ Error inspecting chunks: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inspect ChromaDB chunks with metadata")
    parser.add_argument("--collection", "-c", default="geography_docs_enriched",
                       help="Collection name to inspect (default: geography_docs_enriched)")
    parser.add_argument("--limit", "-l", type=int, default=10,
                       help="Number of sample chunks to display (default: 10)")
    
    args = parser.parse_args()
    
    sys.exit(inspect_chunks(args.collection, args.limit))

