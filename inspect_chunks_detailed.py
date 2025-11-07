#!/usr/bin/env python3
"""
Script to inspect stored chunks in ChromaDB with detailed metadata structure.
Specifically shows chunks with "current affairs" in filename.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.utils.chroma_handler import ChromaHandler
from app.core.config import settings

def inspect_chunks_detailed(collection_name: str = "geography_docs_enriched", 
                           filter_filename: str = None,
                           limit: int = 20):
    """Inspect chunks with detailed metadata structure"""
    print(f"🔍 Inspecting chunks from collection: {collection_name}")
    if filter_filename:
        print(f"🔎 Filtering for filename containing: '{filter_filename}'")
    print("=" * 100)
    
    try:
        handler = ChromaHandler()
        handler.switch_to_collection(collection_name)
        
        # Get collection stats
        stats = handler.get_stats()
        print(f"\n📊 Collection Statistics:")
        print(f"   Total chunks: {stats.get('total_chunks', 0)}")
        print(f"   Collection name: {stats.get('collection_name', 'N/A')}")
        
        # Get all documents
        print(f"\n📥 Fetching all chunks...")
        all_docs = handler.get_all_documents_paginated()
        print(f"   ✅ Retrieved {len(all_docs)} chunks")
        
        # Filter by filename if specified
        if filter_filename:
            filtered_docs = [
                doc for doc in all_docs 
                if filter_filename.lower() in doc.get('metadata', {}).get('filename', '').lower()
            ]
            print(f"   🔎 Found {len(filtered_docs)} chunks matching '{filter_filename}' in filename")
            docs_to_show = filtered_docs[:limit]
        else:
            docs_to_show = all_docs[:limit]
        
        # Show sample chunks with full metadata
        print(f"\n📄 Sample Chunks (showing first {len(docs_to_show)}):")
        print("=" * 100)
        
        for i, doc in enumerate(docs_to_show, 1):
            print(f"\n{'═' * 100}")
            print(f"CHUNK #{i}")
            print(f"{'═' * 100}")
            
            # ID
            print(f"📌 ID: {doc.get('id', 'N/A')}")
            
            # Content preview
            content = doc.get('content', '')
            content_preview = content[:300] + "..." if len(content) > 300 else content
            print(f"\n📝 Content ({len(content)} characters):")
            print(f"   {content_preview}")
            
            # Full Metadata (formatted nicely)
            metadata = doc.get('metadata', {})
            print(f"\n🏷️  FULL METADATA STRUCTURE ({len(metadata)} fields):")
            print(f"{'─' * 100}")
            
            # Group metadata by category for better readability
            file_metadata = {}
            domain_metadata = {}
            content_metadata = {}
            other_metadata = {}
            
            for key, value in sorted(metadata.items()):
                if key in ['filename', 'source_type', 'file_path', 'page_number']:
                    file_metadata[key] = value
                elif key in ['major_domain', 'sub_domain', 'subject', 'topic', 'chapter', 'section']:
                    domain_metadata[key] = value
                elif key in ['difficulty', 'summary', 'chunk_id', 'chunk_index', 'content_type']:
                    content_metadata[key] = value
                else:
                    other_metadata[key] = value
            
            if file_metadata:
                print(f"\n📁 FILE METADATA:")
                for key, value in sorted(file_metadata.items()):
                    print(f"   • {key:25s}: {value}")
            
            if domain_metadata:
                print(f"\n🌍 DOMAIN/TOPIC METADATA:")
                for key, value in sorted(domain_metadata.items()):
                    print(f"   • {key:25s}: {value}")
            
            if content_metadata:
                print(f"\n📚 CONTENT METADATA:")
                for key, value in sorted(content_metadata.items()):
                    if key == 'summary' and isinstance(value, str) and len(value) > 150:
                        print(f"   • {key:25s}: {value[:150]}...")
                    else:
                        print(f"   • {key:25s}: {value}")
            
            if other_metadata:
                print(f"\n🔧 OTHER METADATA:")
                for key, value in sorted(other_metadata.items()):
                    print(f"   • {key:25s}: {value}")
            
            # Show raw JSON for exact structure
            print(f"\n📋 RAW METADATA (JSON):")
            print(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        # Metadata field analysis
        print(f"\n{'═' * 100}")
        print(f"📊 METADATA FIELD ANALYSIS (across all {len(all_docs)} chunks):")
        print(f"{'═' * 100}")
        
        all_metadata_keys = set()
        metadata_counts = {}
        metadata_examples = defaultdict(list)
        
        for doc in all_docs:
            meta = doc.get('metadata', {})
            for key, value in meta.items():
                all_metadata_keys.add(key)
                metadata_counts[key] = metadata_counts.get(key, 0) + 1
                # Store example values (first 3 unique values)
                if len(metadata_examples[key]) < 3:
                    if value not in metadata_examples[key]:
                        metadata_examples[key].append(value)
        
        print(f"\nTotal unique metadata fields: {len(all_metadata_keys)}")
        print(f"\nField frequency and examples:")
        for key in sorted(all_metadata_keys):
            count = metadata_counts.get(key, 0)
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            examples = metadata_examples[key][:2]  # Show first 2 examples
            examples_str = ", ".join([str(e)[:50] for e in examples])
            print(f"   • {key:25s}: {count:5d} chunks ({percentage:5.1f}%) | Examples: {examples_str}")
        
        # Filename analysis
        print(f"\n{'═' * 100}")
        print(f"📁 FILENAME ANALYSIS:")
        print(f"{'═' * 100}")
        
        filenames = defaultdict(int)
        for doc in all_docs:
            filename = doc.get('metadata', {}).get('filename', 'Unknown')
            filenames[filename] += 1
        
        print(f"\nTotal unique filenames: {len(filenames)}")
        print(f"\nFilename distribution (top 15):")
        for filename, count in sorted(filenames.items(), key=lambda x: x[1], reverse=True)[:15]:
            percentage = (count / len(all_docs) * 100) if all_docs else 0
            print(f"   • {filename:60s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        # Current Affairs specific analysis
        if filter_filename and 'current' in filter_filename.lower():
            print(f"\n{'═' * 100}")
            print(f"📰 CURRENT AFFAIRS CHUNKS ANALYSIS:")
            print(f"{'═' * 100}")
            
            ca_docs = [
                doc for doc in all_docs 
                if 'current' in doc.get('metadata', {}).get('filename', '').lower()
            ]
            
            print(f"\nTotal Current Affairs chunks: {len(ca_docs)}")
            
            # Domain distribution for CA chunks
            ca_domains = defaultdict(int)
            ca_sub_domains = defaultdict(int)
            
            for doc in ca_docs:
                meta = doc.get('metadata', {})
                major = meta.get('major_domain', 'Unknown')
                sub = meta.get('sub_domain', 'Unknown')
                ca_domains[major] += 1
                ca_sub_domains[sub] += 1
            
            print(f"\nMajor Domains in Current Affairs chunks:")
            for domain, count in sorted(ca_domains.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(ca_docs) * 100) if ca_docs else 0
                print(f"   • {domain:30s}: {count:5d} chunks ({percentage:5.1f}%)")
            
            print(f"\nSub Domains in Current Affairs chunks (top 10):")
            for domain, count in sorted(ca_sub_domains.items(), key=lambda x: x[1], reverse=True)[:10]:
                percentage = (count / len(ca_docs) * 100) if ca_docs else 0
                print(f"   • {domain:30s}: {count:5d} chunks ({percentage:5.1f}%)")
        
        # Export filtered chunks to JSON
        if filter_filename:
            export_file = f"chunks_{filter_filename.replace(' ', '_')}_detailed.json"
        else:
            export_file = "chunks_detailed_sample.json"
        
        export_data = []
        for doc in docs_to_show:
            export_data.append({
                "id": doc.get("id"),
                "content": doc.get("content"),
                "metadata": doc.get("metadata")
            })
        
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Sample chunks exported to: {export_file}")
        print(f"\n{'═' * 100}")
        print(f"✨ Inspection complete!")
        print(f"{'═' * 100}")
        
    except Exception as e:
        print(f"❌ Error inspecting chunks: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inspect ChromaDB chunks with detailed metadata")
    parser.add_argument("--collection", "-c", default="geography_docs_enriched",
                       help="Collection name to inspect (default: geography_docs_enriched)")
    parser.add_argument("--filter", "-f", type=str, default="current affairs",
                       help="Filter chunks by filename containing this string (default: 'current affairs')")
    parser.add_argument("--limit", "-l", type=int, default=20,
                       help="Number of sample chunks to display (default: 20)")
    parser.add_argument("--no-filter", action="store_true",
                       help="Don't filter by filename, show all chunks")
    
    args = parser.parse_args()
    
    filter_str = None if args.no_filter else args.filter
    
    sys.exit(inspect_chunks_detailed(args.collection, filter_str, args.limit))

