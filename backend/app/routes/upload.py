from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response
from typing import List
import os
import shutil
import logging
from ..utils.pdf_reader import extract_text_from_pdf
from ..core.config import settings
from ..utils.hierarchical_chunker import HierarchicalChunker
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
    Uploads multiple PDF files, extracts text, chunks it, creates embeddings,
    and stores them in a new ChromaDB collection.
    """
    processed_files_summary = []
    chroma_handler = request.app.state.chroma_handler

    # Switch to or create the new collection
    chroma_handler.switch_to_collection(new_collection_name)

    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        try:
            # Save the uploaded file temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Read the PDF text
            pages_content = extract_text_from_pdf(file_path)
            text = "\n".join(page["text"] for page in pages_content if page.get("text"))

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

            # Add chunks to ChromaDB (chunks already have "content" and "metadata" keys)
            if chunks:
                try:
                    chroma_handler.add_documents(chunks)
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "success",
                        "chunks_added": len(chunks)
                    })
                    logger.info(f"✅ Successfully processed and added {len(chunks)} chunks for {file.filename}")
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
                    "reason": "No chunks created from PDF"
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
        raise HTTPException(status_code=400, detail="No PDFs were processed.")

    return {"message": "PDFs processing complete", "summary": processed_files_summary}