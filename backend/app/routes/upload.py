from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response, Form, Depends
from typing import List, Optional
import os
import shutil
import logging
from ..utils.pdf_reader import extract_text_from_pdf
from ..utils.ocr_processor import process_handwritten_document
from ..utils.handwritten_processor import process_pdf_with_roi, process_image_with_roi
from ..utils.gemini_ocr import process_pages_with_gemini_ocr
from ..utils.pdf_generator import generate_pdf_from_ocr_results
from ..core.config import settings
from ..utils.hierarchical_chunker import HierarchicalChunker
from ..utils.metadata_enricher import enrich_metadata
from ..utils.content_store import ContentStore
from openai import OpenAI

router = APIRouter()

@router.post("/reset")
async def reset_database(request: Request):
    """Delete all collections and start fresh"""
    try:
        vector_handler = request.app.state.vector_handler
        vector_handler.delete_all_collections()
        return {"message": "Successfully deleted all collections and created a fresh one"}
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete-collection/{collection_name}")
async def delete_collection(request: Request, collection_name: str):
    """Delete a specific collection by name"""
    try:
        vector_handler = request.app.state.vector_handler
        vector_handler.delete_collection(collection_name)
        return {"message": f"Successfully deleted collection: {collection_name}"}
    except Exception as e:
        logger.error(f"Failed to delete collection {collection_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sample-sheet")
async def upload_sample_sheet(sample_sheet: UploadFile = File(...)):
    """
    Upload a sample sheet (empty or with answers) for ROI detection.
    The sample sheet will be used to detect ROI coordinates that will be reused for all pages.
    
    Supported formats: WEBP, JPG, PNG, PDF
    """
    try:
        # Validate file type
        file_ext = os.path.splitext(sample_sheet.filename)[1].lower()
        allowed_extensions = ['.webp', '.jpg', '.jpeg', '.png', '.pdf']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(allowed_extensions)}"
            )
        
        # Delete old sample sheets first (for development/testing)
        logger.info("🗑️ Cleaning up old sample sheets...")
        old_sample_files = [f for f in os.listdir(SAMPLE_SHEET_DIR) if f.startswith("sample_")]
        deleted_count = 0
        for old_file in old_sample_files:
            old_path = os.path.join(SAMPLE_SHEET_DIR, old_file)
            try:
                os.remove(old_path)
                deleted_count += 1
                logger.info(f"   🗑️ Deleted old sample sheet: {old_file}")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to delete old sample sheet {old_file}: {e}")
        
        if deleted_count > 0:
            logger.info(f"   ✅ Deleted {deleted_count} old sample sheet(s)")
        
        # Save new sample sheet
        sample_sheet_path = os.path.join(SAMPLE_SHEET_DIR, f"sample_{sample_sheet.filename}")
        with open(sample_sheet_path, "wb") as buffer:
            shutil.copyfileobj(sample_sheet.file, buffer)
        
        logger.info(f"✅ Sample sheet uploaded: {sample_sheet.filename} -> {sample_sheet_path}")
        
        # Generate preview path for frontend
        preview_url = f"/upload/sample-sheet-preview"
        roi_preview_url = f"/upload/sample-sheet-roi-preview"
        
        logger.info(f"   📷 Preview URLs available:")
        logger.info(f"      • Original: {preview_url}")
        logger.info(f"      • ROI Preview: {roi_preview_url}")
        
        return {
            "message": "Sample sheet uploaded successfully",
            "filename": sample_sheet.filename,
            "path": sample_sheet_path,
            "file_type": file_ext,
            "preview_url": preview_url,
            "roi_preview_url": roi_preview_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error uploading sample sheet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload sample sheet: {str(e)}")

@router.get("/roi-preview/{file_name:path}")
async def get_roi_preview(file_name: str):
    """
    Serve ROI preview images for viewing in frontend
    """
    preview_path = os.path.join(ROI_PREVIEW_DIR, file_name)
    
    if not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="ROI preview not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(preview_path, media_type="image/png")

@router.get("/sample-sheet-preview")
async def get_sample_sheet_preview():
    """
    Serve the most recently uploaded sample sheet for preview
    """
    sample_files = [f for f in os.listdir(SAMPLE_SHEET_DIR) if f.startswith("sample_")]
    if not sample_files:
        raise HTTPException(status_code=404, detail="No sample sheet found")
    
    # Get most recent sample sheet
    latest_sample = sorted(sample_files)[-1]
    sample_path = os.path.join(SAMPLE_SHEET_DIR, latest_sample)
    
    if not os.path.exists(sample_path):
        raise HTTPException(status_code=404, detail="Sample sheet file not found")
    
    from fastapi.responses import FileResponse
    # Determine content type based on extension
    ext = os.path.splitext(latest_sample)[1].lower()
    content_type = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.pdf': 'application/pdf'
    }.get(ext, 'image/png')
    
    return FileResponse(sample_path, media_type=content_type)

@router.get("/sample-sheet-roi-preview")
async def get_sample_sheet_roi_preview():
    """
    Generate and return ROI preview from sample sheet (shows what will be detected)
    """
    import cv2
    from ..utils.roi_detector import extract_answer_roi
    
    sample_files = [f for f in os.listdir(SAMPLE_SHEET_DIR) if f.startswith("sample_")]
    if not sample_files:
        raise HTTPException(status_code=404, detail="No sample sheet found")
    
    # Get most recent sample sheet
    latest_sample = sorted(sample_files)[-1]
    sample_path = os.path.join(SAMPLE_SHEET_DIR, latest_sample)
    
    if not os.path.exists(sample_path):
        raise HTTPException(status_code=404, detail="Sample sheet file not found")
    
    try:
        # Load and process sample sheet
        logger.info(f"📷 Loading sample sheet for ROI preview: {sample_path}")
        img = cv2.imread(sample_path)
        if img is None:
            logger.error(f"❌ Failed to load sample sheet image: {sample_path}")
            raise HTTPException(status_code=400, detail="Failed to load sample sheet image")
        
        logger.info(f"   ✅ Image loaded: shape={img.shape}")
        
        # Extract ROI (try Hough Lines first, fallback if needed)
        logger.info("   🔍 Attempting ROI detection...")
        try:
            roi_image, metadata = extract_answer_roi(img, use_fallback=False)
            logger.info(f"   ✅ ROI detected using {metadata['method']}")
        except Exception as e:
            logger.warning(f"   ⚠️ Hough Lines failed: {e}. Using fallback...")
            roi_image, metadata = extract_answer_roi(img, use_fallback=True)
            logger.info(f"   ✅ ROI detected using fallback method")
        
        # Extract original ROI crop for preview (before preprocessing)
        top = metadata["coordinates"]["top"]
        left = metadata["coordinates"]["left"]
        right = metadata["coordinates"]["right"]
        bottom = metadata["coordinates"]["bottom"]
        original_roi = img[top:bottom, left:right]
        
        # Save original ROI crop (not binary thresholded) for preview
        temp_preview_path = os.path.join(ROI_PREVIEW_DIR, "sample_sheet_roi_preview.png")
        cv2.imwrite(temp_preview_path, original_roi)
        logger.info(f"   💾 Saved ROI preview (original crop): {temp_preview_path}")
        logger.info(f"      • Preview size: {original_roi.shape[1]}x{original_roi.shape[0]} pixels")
        
        from fastapi.responses import FileResponse
        return FileResponse(temp_preview_path, media_type="image/png")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to generate sample sheet ROI preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate ROI preview: {str(e)}")

logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"
SAMPLE_SHEET_DIR = "data/sample_sheets"
ROI_PREVIEW_DIR = "data/roi_previews"
OCR_OUTPUT_DIR = "data/ocr_outputs"  # Directory for generated PDFs
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SAMPLE_SHEET_DIR, exist_ok=True)
os.makedirs(ROI_PREVIEW_DIR, exist_ok=True)
os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)

# Initialize components
chunker = HierarchicalChunker(llm_client=OpenAI(api_key=os.getenv("OPENAI_API_KEY")))
content_store = ContentStore()

# Store sample sheet path in app state (will be set per session)
# In production, you might want to use a database or session storage

@router.post("/")
async def upload_pdfs(
    request: Request, 
    files: List[UploadFile] = File(...),
    subject: str = Form("Unclassified"),
    major_domain: str = Form("Unclassified"),
    source_type: Optional[str] = Form(None),
    dpi: Optional[int] = Form(None),
    sample_sheet_path: Optional[str] = Form(None),
    skip_embedding: bool = Form(False)
):
    """
    Uploads multiple PDF, TXT, or image files, processes them, chunks them,
    creates embeddings, and stores them in Pinecone.
    
    Args:
        files: List of PDF, TXT, or image files to upload
        dpi: DPI for PDF conversion (300 or 600, default: 600) - only used for images/scanned PDFs
        sample_sheet_path: Optional path to sample sheet for ROI detection (for images/scanned PDFs)
    
    Supported formats:
    - PDF: Text-based PDFs (extracted directly) or scanned/image-based PDFs (OCR with ROI)
    - TXT: Plain text files (processed directly with hierarchical chunker)
    - Images: JPG, JPEG, PNG, WEBP, GIF, BMP, TIFF (processed with OCR and ROI)
    """
    # Debug: Log received parameters
    logger.info(f"📥 Upload request received:")
    logger.info(f"   • subject: {subject}")
    logger.info(f"   • major_domain: {major_domain}")
    logger.info(f"   • source_type: '{source_type}' (type: {type(source_type).__name__})")
    logger.info(f"   • files: {[f.filename for f in files]}")
    
    processed_files_summary = []
    # Use vector_handler (which is PineconeHandler when USE_PINECONE=True)
    vector_handler = request.app.state.vector_handler
    # Keep backward compatibility
    chroma_handler = vector_handler

    # No need to switch collection - using single Pinecone index from config

    # Validate DPI (only required for handwritten/image processing)
    # DPI is optional - only used when processing handwritten content (images or scanned PDFs)
    if dpi is not None and dpi not in [300, 600]:
        raise HTTPException(status_code=400, detail="DPI must be 300 or 600")
    # Default DPI for handwritten processing if not provided (will be used only if needed)
    if dpi is None:
        dpi = 600  # Default to 600 for handwritten processing (only used if ROI+OCR is needed)
    
    # Find sample sheet if not provided
    if not sample_sheet_path:
        # Look for most recent sample sheet
        sample_files = [f for f in os.listdir(SAMPLE_SHEET_DIR) if f.startswith("sample_")]
        if sample_files:
            sample_sheet_path = os.path.join(SAMPLE_SHEET_DIR, sorted(sample_files)[-1])
            logger.info(f"📋 Using sample sheet: {sample_sheet_path}")
    
    # Check if sample sheet exists
    if sample_sheet_path and not os.path.exists(sample_sheet_path):
        logger.warning(f"⚠️ Sample sheet not found: {sample_sheet_path}. Proceeding without it.")
        sample_sheet_path = None

    # Supported image extensions
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.tif']
    
    # ==========================================================================
    # PHASE 1: Collect all files and identify which need OCR
    # ==========================================================================
    files_needing_ocr = []  # List of {filename, file_path, pages, roi_result, roi_preview_paths}
    files_with_text = []    # List of {filename, file_path, text, pages_content}
    txt_files = []          # List of {filename, file_path}
    image_files = []        # List of {filename, file_path}
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📁 PHASE 1: Analyzing {len(files)} file(s) for processing")
    logger.info(f"{'='*70}\n")
    
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        try:
            # Save the uploaded file temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            if file_ext == '.pdf':
                # Try to extract text directly from PDF
                pages_content = extract_text_from_pdf(file_path)
                text = "\n".join(page["text"] for page in pages_content if page.get("text"))
                
                logger.info(f"📄 {file.filename}: {len(pages_content)} pages, {len(text)} chars extracted")
                
                # If PDF has no extractable text, it needs OCR
                if not text or len(text.strip()) < 200:
                    logger.info(f"   → Scanned/image-based PDF, will use OCR")
                    
                    # Process PDF with ROI detection
                    roi_result = process_pdf_with_roi(
                        pdf_path=file_path,
                        dpi=dpi,
                        sample_sheet_path=sample_sheet_path,
                        save_roi_previews=True,
                        preview_dir=os.path.join(ROI_PREVIEW_DIR, os.path.splitext(file.filename)[0])
                    )
                    
                    roi_preview_paths = [page.get("roi_preview_path") for page in roi_result["pages"] if page.get("roi_preview_path")]
                    
                    files_needing_ocr.append({
                        "filename": file.filename,
                        "file_path": file_path,
                        "pages": roi_result["pages"],
                        "roi_result": roi_result,
                        "roi_preview_paths": roi_preview_paths,
                        "page_count": len(roi_result["pages"])
                    })
                else:
                    logger.info(f"   → Text-extractable PDF, no OCR needed")
                    files_with_text.append({
                        "filename": file.filename,
                        "file_path": file_path,
                        "text": text,
                        "pages_content": pages_content
                    })
                    
            elif file_ext == '.txt':
                logger.info(f"📝 {file.filename}: TXT file")
                txt_files.append({
                    "filename": file.filename,
                    "file_path": file_path
                })
                
            elif file_ext in image_extensions:
                logger.info(f"🖼️ {file.filename}: Image file, will use OCR")
                
                # Process image with ROI detection
                roi_result = process_image_with_roi(
                    image_path=file_path,
                    sample_sheet_path=sample_sheet_path,
                    save_roi_preview=True,
                    preview_dir=os.path.join(ROI_PREVIEW_DIR, os.path.splitext(file.filename)[0])
                )
                
                image_files.append({
                    "filename": file.filename,
                    "file_path": file_path,
                    "roi_result": roi_result,
                    "page_data": [{
                        "page_number": 1,
                        "roi_image_preprocessed": roi_result["roi_image_preprocessed"]
                    }]
                })
            else:
                logger.warning(f"⚠️ {file.filename}: Unsupported file type {file_ext}")
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"Unsupported file type: {file_ext}"
                })
                
        except Exception as e:
            logger.error(f"❌ Error analyzing {file.filename}: {e}")
            processed_files_summary.append({
                "filename": file.filename,
                "status": "failed",
                "reason": f"Analysis failed: {str(e)}"
            })
    
    # ==========================================================================
    # PHASE 2: Batch OCR all scanned PDFs and images together
    # ==========================================================================
    ocr_results_by_file = {}  # filename -> list of OCR results
    
    if files_needing_ocr or image_files:
        logger.info(f"\n{'='*70}")
        logger.info(f"🔍 PHASE 2: Batch OCR Processing")
        logger.info(f"   • Scanned PDFs: {len(files_needing_ocr)} files")
        logger.info(f"   • Images: {len(image_files)} files")
        logger.info(f"{'='*70}\n")
        
        try:
            from ..gemini_core import settings_gemini_key
            gemini_api_key = settings_gemini_key.GEMINI_API_KEY
            
            if not gemini_api_key:
                raise Exception("GEMINI_API_KEY not configured")
            
            # Collect ALL pages from all files with tracking metadata
            all_pages_for_ocr = []
            page_to_file_map = []  # Maps each page index to (filename, local_page_number)
            
            # Add pages from scanned PDFs
            for file_info in files_needing_ocr:
                filename = file_info["filename"]
                for local_idx, page in enumerate(file_info["pages"]):
                    # Add filename tracking to page data
                    page_with_tracking = page.copy()
                    page_with_tracking["_source_filename"] = filename
                    page_with_tracking["_local_page_number"] = local_idx + 1
                    all_pages_for_ocr.append(page_with_tracking)
                    page_to_file_map.append((filename, local_idx + 1))
            
            # Add pages from images
            for img_info in image_files:
                filename = img_info["filename"]
                for page in img_info["page_data"]:
                    page_with_tracking = page.copy()
                    page_with_tracking["_source_filename"] = filename
                    page_with_tracking["_local_page_number"] = 1
                    all_pages_for_ocr.append(page_with_tracking)
                    page_to_file_map.append((filename, 1))
            
            total_pages = len(all_pages_for_ocr)
            logger.info(f"⏳ Running Gemini OCR on {total_pages} total pages from {len(files_needing_ocr) + len(image_files)} files...")
            
            # BATCH OCR all pages together WITH RECONSTRUCTION (for PDF uploads to Pinecone)
            from ..utils.gemini_ocr import process_pages_with_gemini_ocr_with_reconstruction
            ocr_results = await process_pages_with_gemini_ocr_with_reconstruction(all_pages_for_ocr, gemini_api_key, max_workers=2)
            
            # Check for OCR failures
            failed_pages = [r for r in ocr_results if r.get("error")]
            if failed_pages:
                error_details = "; ".join([f"Page {r['page_number']}: {r['error']}" for r in failed_pages[:5]])
                logger.error(f"❌ OCR failed for {len(failed_pages)} page(s): {error_details}")
            
            logger.info(f"✅ OCR completed for {len(ocr_results)} pages")
            
            # Group OCR results back by filename
            for idx, ocr_result in enumerate(ocr_results):
                if idx < len(page_to_file_map):
                    filename, local_page_num = page_to_file_map[idx]
                    if filename not in ocr_results_by_file:
                        ocr_results_by_file[filename] = []
                    
                    # Add local page number to result
                    ocr_result["page_number"] = local_page_num
                    ocr_results_by_file[filename].append(ocr_result)
            
            logger.info(f"\n📊 OCR results grouped by file:")
            for filename, results in ocr_results_by_file.items():
                logger.info(f"   • {filename}: {len(results)} pages")
                
        except Exception as ocr_error:
            logger.error(f"❌ Batch OCR failed: {ocr_error}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Mark all OCR files as failed
            for file_info in files_needing_ocr:
                processed_files_summary.append({
                    "filename": file_info["filename"],
                    "status": "failed",
                    "reason": f"Batch OCR failed: {str(ocr_error)}"
                })
            for img_info in image_files:
                processed_files_summary.append({
                    "filename": img_info["filename"],
                    "status": "failed",
                    "reason": f"Batch OCR failed: {str(ocr_error)}"
                })
            
            # Clear these lists so we don't try to process them further
            files_needing_ocr = []
            image_files = []
    
    # ==========================================================================
    # PHASE 3: Reconstruct and chunk each file separately
    # ==========================================================================
    logger.info(f"\n{'='*70}")
    logger.info(f"📝 PHASE 3: Reconstruct & Chunk per file")
    logger.info(f"{'='*70}\n")
    
    # Process scanned PDFs (from OCR results)
    for file_info in files_needing_ocr:
        filename = file_info["filename"]
        file_path = file_info["file_path"]
        roi_info = {
            "roi_preview_paths": file_info["roi_preview_paths"],
            "roi_method": file_info["roi_result"]["roi_method"],
            "roi_coordinates": file_info["roi_result"]["roi_coordinates"]
        }
        
        if filename not in ocr_results_by_file:
            logger.error(f"❌ No OCR results for {filename}")
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": "No OCR results available"
            })
            continue
        
        file_ocr_results = ocr_results_by_file[filename]
        
        try:
            # Simply combine OCR text from all pages (no LLM reconstruction needed for uploads)
            logger.info(f"📄 Combining {len(file_ocr_results)} pages of OCR text for {filename}...")
            
            # Join text from all pages - use full_text or text field from OCR results
            page_texts = []
            for page_result in file_ocr_results:
                # Prefer full_text (raw Gemini output), fall back to text (merged blocks)
                page_text = page_result.get("full_text") or page_result.get("text", "")
                if page_text:
                    page_texts.append(page_text)
            
            ocr_text = "\n\n".join(page_texts)
            
            if not ocr_text or len(ocr_text.strip()) < 50:
                logger.error(f"❌ OCR produced insufficient text for {filename}")
                processed_files_summary.append({
                    "filename": filename,
                    "status": "failed",
                    "reason": "OCR produced insufficient text"
                })
                continue
            
            logger.info(f"   ✅ Combined {len(ocr_text)} chars from {len(page_texts)} pages")
            
            # Create single chunk for this file
            chunks = chunker.process_as_single_chunk(text_override=ocr_text, filename=filename, subject=subject)
            
            # Continue to classification and storage (shared code below)
            # We need to add this file to a processing queue
            # For now, process inline...
            
            if not chunks:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "skipped",
                    "reason": "No chunks created"
                })
                continue
            
            # Skip embedding if requested
            if skip_embedding:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "success",
                    "message": "Processed (embedding skipped)",
                    "chunks_created": len(chunks),
                    "content_preview": ocr_text[:200] + "..." if len(ocr_text) > 200 else ocr_text
                })
                continue
            
            # Classify and store chunks
            logger.info(f"🤖 Classifying {len(chunks)} chunks for {filename}...")
            from ..utils.metadata_enricher import classify_chunks_batch
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            classified_chunks = classify_chunks_batch(chunks, openai_client, subject=subject, provided_major_domain=major_domain, source_type=source_type)
            
            # Store in Pinecone
            logger.info(f"💾 Storing {len(classified_chunks)} chunks in Pinecone...")
            vector_handler.add_documents(classified_chunks)
            
            # Store in SQL ContentStore
            logger.info(f"💾 Storing in SQL ContentStore...")
            cs_result = content_store.batch_store(classified_chunks)
            
            processed_files_summary.append({
                "filename": filename,
                "status": "success",
                "message": f"OCR + Chunking completed",
                "chunks_created": len(chunks),
                "chunks_stored": len(classified_chunks),
                "pages_processed": len(file_ocr_results),
                "content_preview": ocr_text[:200] + "..." if len(ocr_text) > 200 else ocr_text,
                "roi_info": roi_info
            })
            
        except Exception as e:
            logger.error(f"❌ Error processing {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": str(e)
            })
    
    # Process images (from OCR results)
    for img_info in image_files:
        filename = img_info["filename"]
        file_path = img_info["file_path"]
        
        if filename not in ocr_results_by_file:
            logger.error(f"❌ No OCR results for image {filename}")
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": "No OCR results available"
            })
            continue
        
        file_ocr_results = ocr_results_by_file[filename]
        
        try:
            # Simply get OCR text (no LLM reconstruction needed for uploads)
            logger.info(f"🖼️ Processing OCR text for image {filename}...")
            
            # Get text from OCR result (images have single page)
            page_texts = []
            for page_result in file_ocr_results:
                page_text = page_result.get("full_text") or page_result.get("text", "")
                if page_text:
                    page_texts.append(page_text)
            
            ocr_text = "\n\n".join(page_texts)
            
            if not ocr_text or len(ocr_text.strip()) < 50:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "failed",
                    "reason": "OCR produced insufficient text"
                })
                continue
            
            # Create chunk
            chunks = chunker.process_as_single_chunk(text_override=ocr_text, filename=filename, subject=subject)
            
            if not chunks:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "skipped",
                    "reason": "No chunks created"
                })
                continue
            
            if skip_embedding:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "success",
                    "message": "Processed (embedding skipped)",
                    "chunks_created": len(chunks),
                    "content_preview": ocr_text[:200] + "..."
                })
                continue
            
            # Classify and store
            from ..utils.metadata_enricher import classify_chunks_batch
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            classified_chunks = classify_chunks_batch(chunks, openai_client, subject=subject, provided_major_domain=major_domain, source_type=source_type)
            
            vector_handler.add_documents(classified_chunks)
            cs_result = content_store.batch_store(classified_chunks)
            
            processed_files_summary.append({
                "filename": filename,
                "status": "success",
                "message": "Image OCR + Chunking completed",
                "chunks_created": len(chunks),
                "chunks_stored": len(classified_chunks),
                "content_preview": ocr_text[:200] + "..."
            })
            
        except Exception as e:
            logger.error(f"❌ Error processing image {filename}: {e}")
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": str(e)
            })
    
    # Process text-extractable PDFs (no OCR needed)
    for file_info in files_with_text:
        filename = file_info["filename"]
        file_path = file_info["file_path"]
        
        try:
            logger.info(f"📄 Processing text PDF: {filename}")
            
            # Process PDF using the hierarchical chunker
            chunks = chunker.process_pdf(file_path, filename, subject=subject)
            
            if not chunks:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "skipped",
                    "reason": "No chunks created"
                })
                continue
            
            if skip_embedding:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "success",
                    "message": "Processed (embedding skipped)",
                    "chunks_created": len(chunks)
                })
                continue
            
            # Classify and store
            logger.info(f"🤖 Classifying {len(chunks)} chunks for {filename}...")
            from ..utils.metadata_enricher import classify_chunks_batch
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            classified_chunks = classify_chunks_batch(chunks, openai_client, subject=subject, provided_major_domain=major_domain, source_type=source_type)
            
            logger.info(f"💾 Storing {len(classified_chunks)} chunks in Pinecone...")
            vector_handler.add_documents(classified_chunks)
            
            logger.info(f"💾 Storing in SQL ContentStore...")
            cs_result = content_store.batch_store(classified_chunks)
            
            chapters = sorted(list(set(c.get('metadata', {}).get('chapter', 'General') for c in chunks)))
            
            processed_files_summary.append({
                "filename": filename,
                "status": "success",
                "message": "Text PDF processed successfully",
                "chunks_created": len(chunks),
                "chunks_stored": len(classified_chunks),
                "chapters": chapters
            })
            
        except Exception as e:
            logger.error(f"❌ Error processing {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": str(e)
            })
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    
    # Process TXT files
    for file_info in txt_files:
        filename = file_info["filename"]
        file_path = file_info["file_path"]
        
        try:
            logger.info(f"📝 Processing TXT file: {filename}")
            chunks = chunker.process_txt(file_path, filename)
            
            if not chunks:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "skipped",
                    "reason": "No chunks created from TXT file"
                })
                continue
            
            if skip_embedding:
                processed_files_summary.append({
                    "filename": filename,
                    "status": "success",
                    "message": "Processed (embedding skipped)",
                    "chunks_created": len(chunks)
                })
                continue
            
            # Classify and store
            from ..utils.metadata_enricher import classify_chunks_batch
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            classified_chunks = classify_chunks_batch(chunks, openai_client, subject=subject, provided_major_domain=major_domain, source_type=source_type)
            
            vector_handler.add_documents(classified_chunks)
            cs_result = content_store.batch_store(classified_chunks)
            
            processed_files_summary.append({
                "filename": filename,
                "status": "success",
                "message": "TXT file processed successfully",
                "chunks_created": len(chunks),
                "chunks_stored": len(classified_chunks)
            })
            
        except Exception as e:
            logger.error(f"❌ Error processing {filename}: {e}")
            processed_files_summary.append({
                "filename": filename,
                "status": "failed",
                "reason": str(e)
            })
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    
    # ==========================================================================
    # PHASE 4: Final Summary
    # ==========================================================================
    logger.info(f"\n{'='*70}")
    logger.info(f"✅ PROCESSING COMPLETE")
    logger.info(f"   • Total files: {len(files)}")
    logger.info(f"   • Successful: {len([f for f in processed_files_summary if f.get('status') == 'success'])}")
    logger.info(f"   • Failed: {len([f for f in processed_files_summary if f.get('status') == 'failed'])}")
    logger.info(f"   • Skipped: {len([f for f in processed_files_summary if f.get('status') == 'skipped'])}")
    logger.info(f"{'='*70}\n")

    if not processed_files_summary:
        raise HTTPException(status_code=400, detail="No files were processed.")

    return {"message": "Files processing complete", "summary": processed_files_summary}

@router.get("/download/{filename:path}")
async def download_ocr_pdf(filename: str):
    """
    Download generated OCR PDF file
    
    Args:
        filename: Name of the PDF file to download
    
    Returns:
        PDF file as download
    """
    try:
        pdf_path = os.path.join(OCR_OUTPUT_DIR, filename)
        
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail=f"PDF file not found: {filename}")
        
        if not filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files can be downloaded.")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to download PDF {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {str(e)}")