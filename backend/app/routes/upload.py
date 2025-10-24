from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import List
import os
import shutil
import logging
from ..utils.pdf_reader import process_pdf_for_chunks
from ..core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/")
async def upload_pdfs(request: Request, files: List[UploadFile] = File(...)):
    """
    Uploads multiple PDF files, extracts text, chunks it, creates embeddings,
    and stores them in ChromaDB.
    """
    processed_files_summary = []
    chroma_handler = request.app.state.chroma_handler

    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        try:
            # Save the uploaded file temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Process the PDF
            chunks_with_metadata = process_pdf_for_chunks(
                file_path,
                file.filename,
                settings.CHUNK_SIZE,
                settings.CHUNK_OVERLAP
            )

            if chunks_with_metadata:
                chroma_handler.add_documents(chunks_with_metadata)
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "success",
                    "chunks_added": len(chunks_with_metadata)
                })
                logger.info(f"Successfully processed and added {len(chunks_with_metadata)} chunks for {file.filename}")
            else:
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "failed",
                    "reason": "No text extracted or chunks generated"
                })
                logger.warning(f"No text or chunks for {file.filename}")

        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            processed_files_summary.append({
                "filename": file.filename,
                "status": "failed",
                "reason": str(e)
            })
        finally:
            # Clean up the temporary file
            if os.path.exists(file_path):
                os.remove(file_path)

    if not processed_files_summary:
        raise HTTPException(status_code=400, detail="No PDFs were processed.")

    return {"message": "PDFs processing complete", "summary": processed_files_summary}