from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response
from typing import List
import os
import shutil
import logging
from ..utils.pdf_reader import extract_text_from_pdf
from ..core.config import settings
from ..utils.hierarchical_chunker import HierarchicalChunker
from ..utils.metadata_enricher import enrich_metadata
from openai import OpenAI

router = APIRouter()

@router.post("/reset")
async def reset_database(request: Request):
    """Delete all collections and start fresh"""
    try:
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.delete_all_collections()
        return {"message": "Successfully deleted all collections and created a fresh one"}
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete-collection/{collection_name}")
async def delete_collection(request: Request, collection_name: str):
    """Delete a specific collection by name"""
    try:
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.delete_collection(collection_name)
        return {"message": f"Successfully deleted collection: {collection_name}"}
    except Exception as e:
        logger.error(f"Failed to delete collection {collection_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize the hierarchical chunker
chunker = HierarchicalChunker(llm_client=OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Specify the name of the new collection for enriched chunks
new_collection_name = "geography_docs_enriched"

@router.post("/")
async def upload_pdfs(request: Request, files: List[UploadFile] = File(...)):
    """
    Uploads multiple PDF or TXT files, extracts text, chunks it, creates embeddings,
    and stores them in a new ChromaDB collection.
    """
    processed_files_summary = []
    chroma_handler = request.app.state.chroma_handler

    # Switch to or create the new collection
    chroma_handler.switch_to_collection(new_collection_name)

    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        try:
            # Save the uploaded file temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Determine file type and process accordingly
            if file_ext == '.pdf':
                # Read the PDF text
                pages_content = extract_text_from_pdf(file_path)
                text = "\n".join(page["text"] for page in pages_content if page.get("text"))

                # Log PDF text extraction details
                logger.info(f"📄 PDF Text Extraction for {file.filename}:")
                logger.info(f"   • Total pages: {len(pages_content)}")
                logger.info(f"   • Total text length: {len(text)} characters")
                if text:
                    # Show first 500 characters as sample
                    sample_text = text[:500].replace('\n', ' ')
                    logger.info(f"   • Sample text (first 500 chars): {sample_text}...")
                    # Show last 200 characters
                    if len(text) > 200:
                        sample_end = text[-200:].replace('\n', ' ')
                        logger.info(f"   • Sample text (last 200 chars): ...{sample_end}")
                else:
                    logger.warning(f"   ⚠️ No text extracted from PDF!")

                if not text or len(text.strip()) < 200:
                    logger.warning(f"{file.filename} has very little extractable text — check if it's scanned.")
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "skipped",
                        "reason": "Text too short or empty"
                    })
                    continue

                # Process PDF using the hierarchical chunker
                chunks = chunker.process_pdf(file_path, file.filename)
                
            elif file_ext == '.txt':
                # Process TXT file directly
                logger.info(f"📝 Processing TXT file: {file.filename}")
                chunks = chunker.process_txt(file_path, file.filename)
                
                if not chunks:
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "skipped",
                        "reason": "No chunks created from TXT file"
                    })
                    continue
            else:
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"Unsupported file type: {file_ext}. Only PDF and TXT files are supported."
                })
                logger.warning(f"⚠️ Unsupported file type: {file_ext} for {file.filename}")
                continue

            # Log chunk creation details
            if chunks:
                logger.info(f"📦 Chunk Creation Summary for {file.filename}:")
                logger.info(f"   • Total chunks created: {len(chunks)}")
                
                # Show sample chunks (first 3)
                for i, chunk in enumerate(chunks[:3], 1):
                    content_preview = chunk['content'][:200].replace('\n', ' ')
                    metadata = chunk.get('metadata', {})
                    logger.info(f"   • Sample Chunk {i}:")
                    logger.info(f"     - Content preview: {content_preview}...")
                    logger.info(f"     - Content length: {len(chunk['content'])} chars")
                    logger.info(f"     - Metadata: {metadata}")
                
                if len(chunks) > 3:
                    logger.info(f"   • ... and {len(chunks) - 3} more chunks")

            # Add chunks to ChromaDB (chunks already have "content" and "metadata" keys)
            if chunks:
                try:
                    # Enrich metadata automatically before storing
                    logger.info(f"🔍 Enriching metadata for {len(chunks)} chunks...")
                    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    enriched_chunks = []
                    
                    for chunk in chunks:
                        chunk_text = chunk['content']
                        existing_meta = chunk.get('metadata', {})
                        filename = existing_meta.get('filename', file.filename)
                        chapter = existing_meta.get('chapter', 'Unknown')
                        section = existing_meta.get('section', 'Unknown')
                        
                        # Enrich metadata
                        try:
                            enriched_meta = enrich_metadata(chunk_text, filename, chapter, section, openai_client)
                            # Merge enriched metadata with existing metadata
                            existing_meta.update(enriched_meta)
                            chunk['metadata'] = existing_meta
                        except Exception as enrich_error:
                            logger.warning(f"⚠️ Metadata enrichment failed for one chunk: {enrich_error}")
                            # Continue with original metadata if enrichment fails
                        
                        enriched_chunks.append(chunk)
                    
                    logger.info(f"✅ Metadata enrichment complete for {len(enriched_chunks)} chunks")
                    
                    # Store enriched chunks
                    chroma_handler.add_documents(enriched_chunks)
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "success",
                        "chunks_added": len(enriched_chunks)
                    })
                    logger.info(f"✅ Successfully processed and added {len(enriched_chunks)} chunks (with enriched metadata) for {file.filename}")
                except Exception as embedding_error:
                    # Chunks were created but embedding/storage failed
                    logger.error(f"❌ Chunks created but embedding failed for {file.filename}: {embedding_error}")
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "failed",
                        "reason": f"Embedding failed: {str(embedding_error)}",
                        "chunks_created": len(chunks)  # Info: chunks were created but not stored
                    })
                    raise  # Re-raise to be caught by outer exception handler
            else:
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"No chunks created from {file_ext.upper()} file"
                })
                logger.warning(f"⚠️ No chunks created for {file.filename}")

        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            processed_files_summary.append({
                "filename": file.filename,
                "status": "failed",
                "reason": str(e)
            })
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    if not processed_files_summary:
        raise HTTPException(status_code=400, detail="No files were processed.")

    return {"message": "Files processing complete", "summary": processed_files_summary}