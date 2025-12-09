"""
Test script to upload a PDF and print chunking diagnostics
Shows chunks and metadata without enriching
"""
import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.core.env import load_env_vars
from backend.app.utils.hierarchical_chunker import HierarchicalChunker
from openai import OpenAI

# Load environment variables
load_env_vars()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_chunking(pdf_path: str):
    """Test chunking on a PDF and print diagnostics"""
    if not os.path.exists(pdf_path):
        logger.error(f"❌ PDF not found: {pdf_path}")
        return
    
    filename = os.path.basename(pdf_path)
    logger.info(f"📄 Testing chunking on: {filename}")
    logger.info(f"   Path: {pdf_path}")
    
    # Initialize chunker
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    chunker = HierarchicalChunker(llm_client=openai_client)
    
    # Process PDF
    logger.info("\n" + "="*80)
    logger.info("🔍 PROCESSING PDF...")
    logger.info("="*80 + "\n")
    
    chunks = chunker.process_pdf(pdf_path, filename)
    
    if not chunks:
        logger.error("❌ No chunks created!")
        return
    
    logger.info("\n" + "="*80)
    logger.info(f"✅ CHUNKING COMPLETE: {len(chunks)} chunks created")
    logger.info("="*80 + "\n")
    
    # Print summary statistics
    logger.info("📊 SUMMARY STATISTICS:")
    logger.info("-" * 80)
    
    # Collect metadata fields
    all_metadata_keys = set()
    chapters = set()
    sections = set()
    page_ranges = []
    chunk_sizes = []
    
    for chunk in chunks:
        meta = chunk.get('metadata', {})
        all_metadata_keys.update(meta.keys())
        chapters.add(meta.get('chapter', 'Unknown'))
        sections.add(meta.get('section', 'Unknown'))
        
        if 'page_start' in meta and 'page_end' in meta:
            page_ranges.append((meta['page_start'], meta['page_end']))
        
        chunk_sizes.append(len(chunk['content'].split()))
    
    logger.info(f"   • Total chunks: {len(chunks)}")
    logger.info(f"   • Unique chapters: {len(chapters)}")
    logger.info(f"   • Unique sections: {len(sections)}")
    logger.info(f"   • Average chunk size: {sum(chunk_sizes) / len(chunk_sizes):.1f} words")
    logger.info(f"   • Min chunk size: {min(chunk_sizes)} words")
    logger.info(f"   • Max chunk size: {max(chunk_sizes)} words")
    
    if page_ranges:
        all_pages = [p for start, end in page_ranges for p in range(start, end + 1)]
        logger.info(f"   • Page range: {min(all_pages)} - {max(all_pages)}")
    
    logger.info(f"\n   • Metadata fields: {sorted(all_metadata_keys)}")
    
    # Show sample chunks with full metadata
    logger.info("\n" + "="*80)
    logger.info("📝 SAMPLE CHUNKS (First 5):")
    logger.info("="*80 + "\n")
    
    for i, chunk in enumerate(chunks[:5], 1):
        logger.info(f"--- Chunk {i} ---")
        logger.info(f"Content length: {len(chunk['content'])} chars, {len(chunk['content'].split())} words")
        logger.info(f"Content preview: {chunk['content'][:200].replace(chr(10), ' ')}...")
        logger.info(f"\nMetadata:")
        for key, value in sorted(chunk['metadata'].items()):
            logger.info(f"   • {key}: {value}")
        logger.info("")
    
    # Show last chunk
    if len(chunks) > 5:
        logger.info("--- Last Chunk ---")
        logger.info(f"Content length: {len(chunks[-1]['content'])} chars, {len(chunks[-1]['content'].split())} words")
        logger.info(f"Content preview: {chunks[-1]['content'][:200].replace(chr(10), ' ')}...")
        logger.info(f"\nMetadata:")
        for key, value in sorted(chunks[-1]['metadata'].items()):
            logger.info(f"   • {key}: {value}")
        logger.info("")
    
    # Show chapter distribution
    logger.info("="*80)
    logger.info("📚 CHAPTER DISTRIBUTION:")
    logger.info("="*80 + "\n")
    
    chapter_counts = {}
    for chunk in chunks:
        chapter = chunk['metadata'].get('chapter', 'Unknown')
        chapter_counts[chapter] = chapter_counts.get(chapter, 0) + 1
    
    for chapter, count in sorted(chapter_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        logger.info(f"   • {chapter}: {count} chunks")
    
    if len(chapter_counts) > 10:
        logger.info(f"   ... and {len(chapter_counts) - 10} more chapters")
    
    # Save to JSON for inspection
    output_file = "chunking_test_output.json"
    logger.info(f"\n💾 Saving full output to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "filename": filename,
            "total_chunks": len(chunks),
            "chunks": chunks[:10],  # Save first 10 for inspection
            "summary": {
                "chapters": list(chapters),
                "metadata_fields": list(all_metadata_keys),
                "avg_chunk_size": sum(chunk_sizes) / len(chunk_sizes),
                "min_chunk_size": min(chunk_sizes),
                "max_chunk_size": max(chunk_sizes)
            }
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ Test complete! Check {output_file} for full details.")
    
    return chunks

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test chunking on a PDF")
    parser.add_argument("pdf_path", type=str, help="Path to PDF file to test")
    
    args = parser.parse_args()
    
    test_chunking(args.pdf_path)


