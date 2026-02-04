"""
Content Store Upload Endpoint

Separate endpoint for uploading files to content store (full text storage).
This complements Pinecone by storing full chunk content locally.
No embeddings, no metadata enrichment - just chunking and storage.
"""
import os
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, Request, File, UploadFile, HTTPException, Form
from pathlib import Path

from ..core.config import settings
from ..utils.hierarchical_chunker import HierarchicalChunker
from ..utils.pdf_reader import extract_text_from_pdf
from ..utils.content_store import ContentStore
from ..utils.pinecone_handler import PineconeHandler

logger = logging.getLogger(__name__)
router = APIRouter()

# Upload directory
UPLOAD_DIR = settings.UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Track uploads for sample checking
_upload_count = 0


def match_and_store_pinecone_chunks(
    content_chunks: List[dict], 
    pinecone_handler: PineconeHandler,
    content_store: ContentStore,
    filename: str
) -> dict:
    """
    Fetch all Pinecone chunks for filename, match with content store chunks, and store matched chunks.
    
    ⚠️ READ-ONLY FROM PINECONE - This function ONLY reads from Pinecone.
    It does NOT modify, delete, or write anything to Pinecone index.
    All writes go to SQLite content store only.
    
    Uses Pinecone native API directly (no LangChain).
    
    Args:
        content_chunks: List of chunks from content store upload (with full content)
        pinecone_handler: PineconeHandler instance for accessing Pinecone (read-only)
        content_store: ContentStore instance for storing matched chunks (SQLite writes)
        filename: Filename to fetch Pinecone chunks for
    
    Returns:
        Dict with matching statistics and storage results
    """
    matches = []
    no_matches = []
    stored_count = 0
    
    logger.info(f"🔍 Fetching Pinecone chunks for filename: {filename}...")
    logger.info("   ⚠️ READ-ONLY: Only reading from Pinecone, no modifications")
    
    try:
        # ⚠️ READ-ONLY: Fetch all Pinecone chunks for this filename (no writes to Pinecone)
        pinecone_chunks = pinecone_handler.fetch_all_chunks_native(filename=filename)
        
        if not pinecone_chunks:
            logger.warning(f"⚠️ No Pinecone chunks found for filename: {filename}")
            return {
                'total_content_chunks': len(content_chunks),
                'total_pinecone_chunks': 0,
                'matches': [],
                'no_matches': content_chunks,
                'stored_count': 0,
                'match_rate': 0.0
            }
        
        logger.info(f"   ✅ Found {len(pinecone_chunks)} Pinecone chunks")
        logger.info(f"🔍 Matching {len(content_chunks)} content store chunks with Pinecone chunks...")
        
        # Create a lookup dict for Pinecone chunks by chunk_id
        pinecone_lookup = {}
        for pc_chunk in pinecone_chunks:
            pc_meta = pc_chunk.get('metadata', {})
            pc_chunk_id = pc_meta.get('chunk_id')
            if pc_chunk_id:
                if pc_chunk_id not in pinecone_lookup:
                    pinecone_lookup[pc_chunk_id] = []
                pinecone_lookup[pc_chunk_id].append(pc_chunk)
        
        # Match each content store chunk with Pinecone chunks
        for content_chunk in content_chunks:
            chunk_id = content_chunk['metadata'].get('chunk_id')
            chapter = content_chunk['metadata'].get('chapter')
            section = content_chunk['metadata'].get('section')
            content = content_chunk['content']
            content_length = len(content)
            content_preview = content[:300]
            
            if not chunk_id:
                logger.warning(f"⚠️ Content chunk missing chunk_id, skipping")
                no_matches.append({
                    'chunk_id': None,
                    'filename': filename,
                    'reason': 'missing_chunk_id'
                })
                continue
            
            # Find matching Pinecone chunks
            pc_candidates = pinecone_lookup.get(chunk_id, [])
            
            if not pc_candidates:
                # Try without split suffix (e.g., "1_1_1_split1" -> "1_1_1")
                base_chunk_id = chunk_id.rsplit('_split', 1)[0] if '_split' in chunk_id else chunk_id
                pc_candidates = pinecone_lookup.get(base_chunk_id, [])
            
            best_match = None
            best_score = 0
            
            for pc_chunk in pc_candidates:
                pc_meta = pc_chunk.get('metadata', {})
                pc_chunk_id = pc_meta.get('chunk_id')
                pc_filename = pc_meta.get('filename')
                pc_chapter = pc_meta.get('chapter')
                pc_preview = pc_meta.get('content_preview', '')
                
                # Calculate match score with breakdown
                score = 0
                score_breakdown = {
                    'chunk_id_exact': False,
                    'chunk_id_base': False,
                    'filename_match': False,
                    'chapter_match': False,
                    'chapter_partial': False,
                    'preview_300_match': False,
                    'preview_200_match': False
                }
                
                # Chunk ID match (exact) = 10 points
                if pc_chunk_id == chunk_id:
                    score += 10
                    score_breakdown['chunk_id_exact'] = True
                elif pc_chunk_id and chunk_id and pc_chunk_id.rsplit('_split', 1)[0] == chunk_id.rsplit('_split', 1)[0]:
                    score += 8  # Base chunk ID matches (split chunks)
                    score_breakdown['chunk_id_base'] = True
                
                # Filename match (exact) = 5 points
                if pc_filename == filename:
                    score += 5
                    score_breakdown['filename_match'] = True
                
                # Chapter match (exact) = 3 points
                if pc_chapter and chapter:
                    if pc_chapter.lower() == chapter.lower():
                        score += 3
                        score_breakdown['chapter_match'] = True
                    elif pc_chapter.lower() in chapter.lower() or chapter.lower() in pc_chapter.lower():
                        score += 1  # Partial match
                        score_breakdown['chapter_partial'] = True
                
                # Preview match (first 300 chars) = 5 points
                # For split chunks: first split's preview should match Pinecone's preview
                if pc_preview and content_preview:
                    # Check if this is the first split (split1) - its preview should match Pinecone's preview
                    is_first_split = chunk_id.endswith('_split1')
                    is_base_chunk_in_pinecone = pc_chunk_id and not '_split' in pc_chunk_id
                    
                    # Exact match (300 chars)
                    if pc_preview[:300] == content_preview[:300]:
                        score += 5
                        score_breakdown['preview_300_match'] = True
                    # Partial match (200 chars)
                    elif pc_preview[:200] == content_preview[:200]:
                        score += 3
                        score_breakdown['preview_200_match'] = True
                    # Special case: If Pinecone has base chunk and this is first split, check if preview matches
                    elif is_first_split and is_base_chunk_in_pinecone:
                        # Pinecone preview is from original chunk, first split preview should match start
                        min_len = min(300, len(content_preview), len(pc_preview))
                        if pc_preview[:min_len] == content_preview[:min_len]:
                            score += 5
                            score_breakdown['preview_300_match'] = True
                        else:
                            min_len_200 = min(200, len(content_preview), len(pc_preview))
                            if pc_preview[:min_len_200] == content_preview[:min_len_200]:
                                score += 3
                                score_breakdown['preview_200_match'] = True
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'pinecone_chunk_id': pc_chunk_id,
                        'pinecone_filename': pc_filename,
                        'pinecone_chapter': pc_chapter,
                        'pinecone_preview': pc_preview[:100] if pc_preview else '',
                        'score': score,
                        'score_breakdown': score_breakdown
                    }
            
            # Match threshold: score >= 8
            if best_match and best_score >= 8:
                # ⚠️ WRITE TO SQLITE ONLY: Store matched chunk in SQLite with full content
                # No writes to Pinecone - Pinecone remains untouched
                # Copy domain metadata from Pinecone chunk if available
                pc_meta = None
                if best_match:
                    # Find the matching Pinecone chunk to get metadata
                    for pc_chunk in pc_candidates:
                        if pc_chunk.get('metadata', {}).get('chunk_id') == best_match.get('pinecone_chunk_id'):
                            pc_meta = pc_chunk.get('metadata', {})
                            break
                
                stored = content_store.store_chunk(
                    chunk_id=chunk_id,
                    filename=filename,
                    full_content=content,
                    chapter=chapter,
                    section=section,
                    content_preview=content_preview,
                    major_domain=pc_meta.get('major_domain') if pc_meta else None,
                    sub_domain=pc_meta.get('sub_domain') if pc_meta else None,
                    micro_topic=pc_meta.get('micro_topic') if pc_meta else None,
                    sub_topics=pc_meta.get('sub_topics') if pc_meta else None,
                    source_type=pc_meta.get('source_type') if pc_meta else None,
                    source_subtype=pc_meta.get('source_subtype') if pc_meta else None
                )
                
                if stored:
                    stored_count += 1
                    matches.append({
                        'content_chunk_id': chunk_id,
                        'content_filename': filename,
                        'content_chapter': chapter,
                        'content_length': content_length,
                        'match': best_match
                    })
                else:
                    logger.warning(f"⚠️ Failed to store matched chunk: {chunk_id}")
                    no_matches.append({
                        'chunk_id': chunk_id,
                        'filename': filename,
                        'reason': 'storage_failed',
                        'best_score': best_score
                    })
            else:
                # No good match found - still store it in SQLite (might be a new chunk)
                # ⚠️ WRITE TO SQLITE ONLY: No writes to Pinecone
                # Try to get domain metadata from content chunk metadata if available
                major_domain = content_chunk['metadata'].get('major_domain')
                sub_domain = content_chunk['metadata'].get('sub_domain')
                micro_topic = content_chunk['metadata'].get('micro_topic')
                sub_topics = content_chunk['metadata'].get('sub_topics')
                source_type = content_chunk['metadata'].get('source_type')
                source_subtype = content_chunk['metadata'].get('source_subtype')
                
                stored = content_store.store_chunk(
                    chunk_id=chunk_id,
                    filename=filename,
                    full_content=content,
                    chapter=chapter,
                    section=section,
                    content_preview=content_preview,
                    major_domain=major_domain,
                    sub_domain=sub_domain,
                    micro_topic=micro_topic,
                    sub_topics=sub_topics,
                    source_type=source_type,
                    source_subtype=source_subtype
                )
                
                if stored:
                    stored_count += 1
                
                no_matches.append({
                    'chunk_id': chunk_id,
                    'filename': filename,
                    'chapter': chapter,
                    'content_length': content_length,
                    'best_score': best_score if best_match else 0,
                    'reason': 'no_match' if not best_match else 'low_score'
                })
        
        match_rate = len(matches) / len(content_chunks) if content_chunks else 0.0
        
        logger.info(f"   ✅ Matching complete:")
        logger.info(f"      • Content chunks: {len(content_chunks)}")
        logger.info(f"      • Pinecone chunks: {len(pinecone_chunks)}")
        logger.info(f"      • Matches: {len(matches)}")
        logger.info(f"      • No matches: {len(no_matches)}")
        logger.info(f"      • Stored: {stored_count}")
        logger.info(f"      • Match rate: {match_rate:.1%}")
        
        return {
            'total_content_chunks': len(content_chunks),
            'total_pinecone_chunks': len(pinecone_chunks),
            'matches': matches,
            'no_matches': no_matches,
            'stored_count': stored_count,
            'match_rate': match_rate
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to match and store chunks: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'total_content_chunks': len(content_chunks),
            'total_pinecone_chunks': 0,
            'matches': [],
            'no_matches': content_chunks,
            'stored_count': 0,
            'match_rate': 0.0,
            'error': str(e)
        }


@router.post("/")
async def upload_content_store(
    request: Request,
    files: List[UploadFile] = File(...),
    subject: str = Form("Geography")
):
    """
    Upload files to content store (full text storage, no embeddings).
    
    ⚠️ READ-ONLY FROM PINECONE - This endpoint ONLY reads from Pinecone.
    It does NOT modify, delete, or write anything to Pinecone index.
    All writes go to SQLite content store only.
    
    This endpoint:
    1. Processes files with same cleaning/chunking as Pinecone upload
    2. Stores full content in SQLite content_store database
    3. Fetches matching chunks from Pinecone (READ-ONLY)
    4. Matches content store chunks with Pinecone chunks
    5. Stores matched chunks in SQLite with full content
    6. No embeddings, no metadata enrichment, no Pinecone writes
    
    Use this to build a local content store that complements Pinecone.
    """
    global _upload_count
    
    try:
        # Initialize content store
        content_store = ContentStore()
        
        # Get Pinecone handler for matching (if available)
        pinecone_handler = None
        try:
            pinecone_handler = request.app.state.vector_handler
            if not isinstance(pinecone_handler, PineconeHandler):
                pinecone_handler = None
        except:
            pass
        
        # Initialize chunker (same as normal upload)
        chunker = HierarchicalChunker()
        
        processed_files = []
        all_chunks = []
        
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            try:
                # Save uploaded file
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                chunks = []
                
                if file_ext == '.pdf':
                    # Process PDF (same as normal upload)
                    pages_content = extract_text_from_pdf(file_path)
                    text = "\n".join(page["text"] for page in pages_content if page.get("text"))
                    
                    if text and len(text.strip()) >= 200:
                        # Use hierarchical chunker (same as Pinecone upload)
                        chunks = chunker.process_pdf(
                            pdf_path=file_path,
                            filename=file.filename,
                            subject=subject
                        )
                    else:
                        logger.warning(f"⚠️ PDF {file.filename} has insufficient text, skipping")
                        continue
                
                elif file_ext == '.txt':
                    # Process TXT file (same as normal upload)
                    chunks = chunker.process_txt(
                        txt_path=file_path,
                        filename=file.filename,
                        subject=subject
                    )
                else:
                    logger.warning(f"⚠️ Unsupported file type: {file_ext}")
                    continue
                
                if not chunks:
                    logger.warning(f"⚠️ No chunks generated for {file.filename}")
                    continue
                
                # Apply same splitting logic as Pinecone upload (before storing)
                MAX_WORDS_PER_CHUNK = 1500  # Match Pinecone limit
                
                def split_long_chunk_by_sentences(text: str, max_words: int = 1500, overlap_words: int = 100):
                    """Same splitting logic as pinecone_handler.py"""
                    import re
                    words = text.split()
                    word_count = len(words)
                    
                    if word_count <= max_words:
                        return [text]
                    
                    # Split by sentences
                    sentences = re.split(r'([.!?]+\s+)', text)
                    sentence_list = []
                    for i in range(0, len(sentences) - 1, 2):
                        if i + 1 < len(sentences):
                            sentence_list.append(sentences[i] + sentences[i + 1])
                        else:
                            sentence_list.append(sentences[i])
                    
                    # Fallback to word-based if no sentences
                    if len(sentence_list) <= 1:
                        chunks = []
                        for i in range(0, word_count, max_words - overlap_words):
                            chunk = " ".join(words[i:i + max_words])
                            if chunk.strip():
                                chunks.append(chunk)
                        return chunks
                    
                    # Build chunks from sentences
                    chunks = []
                    current_chunk = []
                    current_word_count = 0
                    
                    for sentence in sentence_list:
                        sentence_words = sentence.split()
                        sentence_word_count = len(sentence_words)
                        
                        if current_word_count + sentence_word_count > max_words and current_chunk:
                            chunk_text = "".join(current_chunk).strip()
                            if chunk_text:
                                chunks.append(chunk_text)
                            
                            # Overlap: last N words
                            overlap_text = " ".join(words[max(0, current_word_count - overlap_words):current_word_count])
                            current_chunk = [overlap_text + " "] if overlap_text else []
                            current_word_count = len(overlap_text.split()) if overlap_text else 0
                        
                        current_chunk.append(sentence)
                        current_word_count += sentence_word_count
                    
                    if current_chunk:
                        chunk_text = "".join(current_chunk).strip()
                        if chunk_text:
                            chunks.append(chunk_text)
                    
                    return chunks if chunks else [text]
                
                # Process chunks (apply splitting if needed, but don't store yet - will store after matching)
                processed_chunks = []
                for chunk in chunks:
                    content = chunk.get('content', '')
                    metadata = chunk.get('metadata', {}).copy()
                    
                    if not content or len(content.strip()) < 10:
                        continue
                    
                    # Ensure filename is in metadata
                    if 'filename' not in metadata:
                        metadata['filename'] = file.filename
                    
                    # Check if chunk needs splitting (same logic as Pinecone)
                    word_count = len(content.split())
                    if word_count > MAX_WORDS_PER_CHUNK:
                        logger.warning(f"⚠️ Chunk {metadata.get('chunk_id')} is too long ({word_count} words), splitting...")
                        split_chunks = split_long_chunk_by_sentences(content, MAX_WORDS_PER_CHUNK, overlap_words=100)
                        logger.info(f"   ✅ Split into {len(split_chunks)} chunks")
                        
                        # Process each split chunk
                        for split_idx, split_chunk in enumerate(split_chunks):
                            if split_chunk.strip() and len(split_chunk.strip()) > 10:
                                # Create metadata copy for split chunk
                                split_meta = metadata.copy()
                                # Add split indicator to chunk_id (same as Pinecone)
                                if 'chunk_id' in split_meta:
                                    split_meta['chunk_id'] = f"{split_meta['chunk_id']}_split{split_idx + 1}"
                                
                                processed_chunks.append({
                                    'content': split_chunk.strip(),
                                    'metadata': split_meta
                                })
                    else:
                        # Process original chunk (no splitting needed)
                        processed_chunks.append({
                            'content': content,
                            'metadata': metadata
                        })
                
                # Add to all_chunks for matching
                all_chunks.extend(processed_chunks)
                
                processed_files.append({
                    'filename': file.filename,
                    'chunks_created': len(processed_chunks),
                    'chunk_ids': [c['metadata'].get('chunk_id') for c in processed_chunks[:5]]  # First 5 IDs
                })
                
                logger.info(f"✅ Created {len(processed_chunks)} chunks from {file.filename} (ready for matching)")
                
            except Exception as e:
                logger.error(f"❌ Error processing {file.filename}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                processed_files.append({
                    'filename': file.filename,
                    'error': str(e)
                })
                continue  # Continue processing other files even if one fails
        
        # Match and store chunks with Pinecone for each file
        all_matching_results = {}
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 Starting matching phase for {len(processed_files)} file(s)")
        logger.info(f"{'='*60}")
        
        if pinecone_handler:
            # Group chunks by filename
            chunks_by_filename = {}
            for chunk in all_chunks:
                filename = chunk['metadata'].get('filename')
                if not filename:
                    # Try to get filename from processed_files
                    if processed_files:
                        filename = processed_files[0].get('filename', 'unknown')
                    else:
                        filename = 'unknown'
                
                if filename not in chunks_by_filename:
                    chunks_by_filename[filename] = []
                chunks_by_filename[filename].append(chunk)
            
            # Match and store for each filename
            total_files_to_match = len(chunks_by_filename)
            current_file_num = 0
            
            for filename, file_chunks in chunks_by_filename.items():
                current_file_num += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"📊 Matching chunks for file {current_file_num}/{total_files_to_match}: {filename}")
                logger.info(f"   Chunks to match: {len(file_chunks)}")
                logger.info(f"{'='*60}")
                
                matching_results = match_and_store_pinecone_chunks(
                    content_chunks=file_chunks,
                    pinecone_handler=pinecone_handler,
                    content_store=content_store,
                    filename=filename
                )
                
                all_matching_results[filename] = matching_results
                
                # Log detailed results
                if matching_results.get('matches'):
                    logger.info(f"\n   ✅ Matched chunks ({len(matching_results['matches'])}):")
                    for match in matching_results['matches'][:5]:
                        score_breakdown = match['match'].get('score_breakdown', {})
                        logger.info(f"      - {match['content_chunk_id']} (score: {match['match']['score']})")
                        logger.info(f"        Breakdown: chunk_id_base={score_breakdown.get('chunk_id_base', False)}, "
                                  f"filename={score_breakdown.get('filename_match', False)}, "
                                  f"chapter={score_breakdown.get('chapter_match', False)}, "
                                  f"preview_300={score_breakdown.get('preview_300_match', False)}, "
                                  f"preview_200={score_breakdown.get('preview_200_match', False)}")
                
                if matching_results.get('no_matches'):
                    logger.warning(f"\n   ⚠️ Unmatched chunks ({len(matching_results['no_matches'])}):")
                    for no_match in matching_results['no_matches'][:5]:
                        reason = no_match.get('reason', 'unknown')
                        score = no_match.get('best_score', 0)
                        logger.warning(f"      - {no_match.get('chunk_id', 'N/A')} (reason: {reason}, best_score: {score})")
                
                logger.info(f"\n✅ Completed matching for file {current_file_num}/{total_files_to_match}: {filename}")
                logger.info(f"   Stored: {matching_results.get('stored_count', 0)} chunks")
        else:
            logger.warning("⚠️ Pinecone handler not available - skipping matching")
        
        # Get content store stats
        stats = content_store.get_stats()
        
        return {
            "status": "success",
            "message": f"Stored chunks from {len(processed_files)} file(s)",
            "processed_files": processed_files,
            "content_store_stats": stats,
            "matching_results": all_matching_results
        }
    
    except Exception as e:
        logger.error(f"❌ Content store upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content store upload failed: {str(e)}")

