from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response, Form
from typing import List, Optional
import os
import shutil
import logging
from ..utils.pdf_reader import extract_text_from_pdf
from ..utils.ocr_processor import process_handwritten_document
from ..utils.handwritten_processor import process_pdf_with_roi, process_image_with_roi
from ..utils.ocr_processor_v2 import process_pages_parallel_google_vision
from ..utils.pdf_generator import generate_pdf_from_ocr_results
from ..utils.answer_reconstructor import reconstruct_pages_blocks
from ..core.config import settings
from ..utils.hierarchical_chunker import HierarchicalChunker
from ..utils.metadata_enricher import enrich_metadata
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

# Initialize the hierarchical chunker
chunker = HierarchicalChunker(llm_client=OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Store sample sheet path in app state (will be set per session)
# In production, you might want to use a database or session storage

@router.post("/")
async def upload_pdfs(
    request: Request, 
    files: List[UploadFile] = File(...),
    dpi: Optional[int] = Form(None),
    sample_sheet_path: Optional[str] = Form(None)
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
    
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        file_ext = os.path.splitext(file.filename)[1].lower()
        roi_info = None  # Initialize ROI info for this file
        
        try:
            # Save the uploaded file temporarily
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Determine file type and process accordingly
            if file_ext == '.pdf':
                # Optional: Compress PDF if it's too large (disabled by default to avoid issues)
                # Uncomment the lines below if you want compression enabled
                # from ..utils.pdf_compressor import compress_pdf_if_needed
                # file_path = compress_pdf_if_needed(file_path, threshold_mb=40)
                
                # First try to extract text directly from PDF
                pages_content = extract_text_from_pdf(file_path)
                text = "\n".join(page["text"] for page in pages_content if page.get("text"))

                # Log PDF text extraction details
                logger.info(f"📄 PDF Text Extraction for {file.filename}:")
                logger.info(f"   • Total pages: {len(pages_content)}")
                logger.info(f"   • Total text length: {len(text)} characters")
                
                # If PDF has no extractable text (scanned/image-based), use ROI + OCR
                if not text or len(text.strip()) < 200:
                    logger.warning(f"   ⚠️ PDF appears to be scanned/image-based. Using ROI + OCR...")
                    try:
                        # Process PDF with ROI detection
                        roi_result = process_pdf_with_roi(
                            pdf_path=file_path,
                            dpi=dpi,
                            sample_sheet_path=sample_sheet_path,
                            save_roi_previews=True,
                            preview_dir=os.path.join(ROI_PREVIEW_DIR, os.path.splitext(file.filename)[0])
                        )
                        
                        # Extract ROI preview paths
                        roi_preview_paths = [page.get("roi_preview_path") for page in roi_result["pages"] if page.get("roi_preview_path")]
                        
                        # TODO: Run OCR on ROI images (PaddleOCR → EasyOCR → Tesseract)
                        # For now, we'll prepare the ROI images for OCR
                        # This is where OCR will be integrated in the next step
                        
                        # Create placeholder text from ROI metadata
                        ocr_text = f"ROI extracted from {len(roi_result['pages'])} pages. ROI method: {roi_result['roi_method']}. OCR processing pending."
                        
                        # Save temporary text file (will be replaced with actual OCR results)
                        temp_txt_path = file_path.replace('.pdf', '_roi_ocr.txt')
                        with open(temp_txt_path, 'w', encoding='utf-8') as f:
                            f.write(ocr_text)
                        
                        logger.info(f"   ✅ ROI extracted from {len(roi_result['pages'])} pages")
                        logger.info(f"   • ROI method: {roi_result['roi_method']}")
                        logger.info(f"   • ROI previews saved: {len(roi_preview_paths)} files")
                        
                        # Process using chunker (will be updated when OCR is integrated)
                        chunks = chunker.process_txt(temp_txt_path, file.filename)
                        
                        # Store ROI preview paths in summary
                        roi_info = {
                            "roi_preview_paths": roi_preview_paths,
                            "roi_method": roi_result["roi_method"],
                            "roi_coordinates": roi_result["roi_coordinates"]
                        }
                        
                        # Clean up temp file
                        if os.path.exists(temp_txt_path):
                            os.remove(temp_txt_path)
                    except Exception as roi_error:
                        logger.error(f"   ❌ ROI + OCR processing failed: {roi_error}")
                        processed_files_summary.append({
                            "filename": file.filename,
                            "status": "failed",
                            "reason": f"ROI + OCR processing failed: {str(roi_error)}"
                        })
                        continue
                else:
                    # PDF has extractable text, process normally
                    if text:
                        # Show first 500 characters as sample
                        sample_text = text[:500].replace('\n', ' ')
                        logger.info(f"   • Sample text (first 500 chars): {sample_text}...")
                    
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
                    
            elif file_ext in image_extensions:
                # Process image file with ROI + OCR + PDF generation
                logger.info(f"🖼️ Processing image file with ROI + OCR: {file.filename}")
                try:
                    # Step 1: Process image with ROI detection
                    roi_result = process_image_with_roi(
                        image_path=file_path,
                        sample_sheet_path=sample_sheet_path,
                        save_roi_preview=True,
                        preview_dir=os.path.join(ROI_PREVIEW_DIR, os.path.splitext(file.filename)[0])
                    )
                    
                    logger.info(f"   ✅ ROI extracted using method: {roi_result['roi_method']}")
                    
                    # Step 2: Prepare page data for OCR (single page)
                    page_data = [{
                        "page_number": 1,
                        "roi_image_preprocessed": roi_result["roi_image_preprocessed"]
                    }]
                    
                    # Step 3: Run OCR using Google Vision API
                    logger.info("")
                    logger.info("   " + "="*70)
                    logger.info("   🔍 STEP 3: Starting OCR Processing")
                    logger.info("   " + "="*70)
                    logger.info("   📋 OCR Pipeline: Google Vision API")
                    logger.info("   ⏳ Processing with Google Vision API...")
                    logger.info("   " + "="*70)
                    logger.info("")
                    try:
                        ocr_results = process_pages_parallel_google_vision(page_data, max_workers=1)
                        logger.info("")
                        logger.info("   ✅ STEP 3: OCR Processing Complete!")
                        logger.info("")
                        
                        # Step 4: No post-processing cleaning - only block filtering (len > 2) done in vision_blocks
                        # Blocks are primary data - merged text is for backward compatibility only
                        # No cleaning applied to preserve spatial structure
                    except Exception as ocr_error:
                        logger.error(f"   ❌ OCR processing failed: {ocr_error}")
                        # Create empty OCR result so PDF can still be generated
                        ocr_results = [{
                            "page_number": 1,
                            "text": f"OCR processing failed: {str(ocr_error)}\n\nPlease check:\n1. Google Vision API credentials are set\n2. GOOGLE_APPLICATION_CREDENTIALS environment variable\n3. Backend logs for details",
                            "error": str(ocr_error),
                            "blocks": []
                        }]
                    
                    # Step 5: Reconstruct blocks using LLM
                    logger.info("")
                    logger.info("   " + "="*70)
                    logger.info("   🤖 STEP 5: Starting LLM Reconstruction")
                    logger.info("   " + "="*70)
                    logger.info("   📋 Reconstructing OCR blocks into clean prose...")
                    logger.info("   " + "="*70)
                    logger.info("")
                    
                    try:
                        # Log OCR data being sent to LLM (for user inspection)
                        logger.info("   📋 OCR Data Summary (before LLM reconstruction):")
                        for result in ocr_results:
                            page_no = result.get("page_number", 0)
                            blocks = result.get("blocks", [])
                            full_text = result.get("full_text", "")
                            width = result.get("width", 0)
                            height = result.get("height", 0)
                            
                            logger.info(f"      Page {page_no}:")
                            logger.info(f"         • Blocks: {len(blocks)}")
                            logger.info(f"         • Full text: {len(full_text)} chars")
                            logger.info(f"         • Dimensions: {width}x{height} pixels")
                            
                            if blocks:
                                # Show first few blocks as preview
                                for i, block in enumerate(blocks[:3], 1):
                                    text_preview = block.get("text", "")[:60]
                                    conf = block.get("conf", 0.0)
                                    bbox = block.get("bbox", [])
                                    logger.info(f"         Block {i}: '{text_preview}...' (conf={conf:.2f}) bbox={bbox}")
                                if len(blocks) > 3:
                                    logger.info(f"         ... and {len(blocks) - 3} more blocks")
                        
                        # Initialize OpenAI client for reconstruction
                        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                        
                        # Reconstruct OCR data using LLM (combine pages for single reconstruction)
                        ocr_results = reconstruct_pages_blocks(
                            ocr_results=ocr_results,
                            llm_client=openai_client,
                            model=settings.LLM_MODEL,
                            combine_pages=True  # Combine all pages into one reconstruction
                        )
                        
                        logger.info("")
                        logger.info("   ✅ STEP 5: LLM Reconstruction Complete!")
                        logger.info("")
                        
                    except Exception as recon_error:
                        logger.error(f"   ❌ LLM reconstruction failed: {recon_error}")
                        logger.warning(f"   ⚠️ Using original merged text as fallback")
                        # Add empty reconstructed_text to results
                        for result in ocr_results:
                            if "reconstructed_text" not in result:
                                result["reconstructed_text"] = result.get("text", "")
                    
                    # Step 6: Generate PDF (even if OCR failed, generate PDF with error message)
                    pdf_filename = os.path.splitext(file.filename)[0] + "_ocr.pdf"
                    pdf_path = os.path.join(OCR_OUTPUT_DIR, pdf_filename)
                    
                    logger.info(f"   📄 Generating PDF: {pdf_filename}")
                    try:
                        # Use reconstructed text if available, otherwise use original text
                        pdf_results = []
                        for result in ocr_results:
                            reconstructed_text = result.get("reconstructed_text", "")
                            original_text = result.get("text", "")
                            text_to_use = reconstructed_text if reconstructed_text else original_text
                            
                            logger.info(f"   📄 Page {result.get('page_number', 1)}:")
                            logger.info(f"      • Using {'reconstructed' if reconstructed_text else 'original'} text")
                            logger.info(f"      • Text length: {len(text_to_use)} chars")
                            if text_to_use:
                                logger.info(f"      • Preview: {text_to_use[:100]}...")
                            else:
                                logger.warning(f"      • ⚠️ No text available for this page!")
                            
                            pdf_result = {
                                "page_number": result.get("page_number", 1),
                                "text": text_to_use
                            }
                            pdf_results.append(pdf_result)
                        
                        generate_pdf_from_ocr_results(
                            ocr_results=pdf_results,
                            output_path=pdf_path,
                            title=f"OCR Extracted Text: {file.filename}"
                        )
                    except Exception as pdf_error:
                        logger.error(f"   ❌ PDF generation failed: {pdf_error}")
                        raise Exception(f"Failed to generate PDF: {str(pdf_error)}")
                    
                    # Store results
                    roi_info = {
                        "roi_preview_path": roi_result.get("roi_preview_path"),
                        "roi_method": roi_result["roi_method"],
                        "roi_coordinates": roi_result["roi_coordinates"],
                        "pdf_path": pdf_path,
                        "pdf_filename": pdf_filename,
                        "ocr_results": ocr_results
                    }
                    
                    # Return success with PDF download link
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "success",
                        "pdf_path": pdf_path,
                        "pdf_filename": pdf_filename,
                        "pdf_download_url": f"/upload/download/{pdf_filename}",
                        "roi_preview_path": roi_info["roi_preview_path"],
                        "roi_method": roi_info["roi_method"],
                        "ocr_results": [
                            {
                                "page_number": r["page_number"],
                                "text": r.get("text", ""),  # Original merged text from blocks
                                "full_text": r.get("full_text", ""),  # Full text from Vision API
                                "reconstructed_text": r.get("reconstructed_text", ""),  # LLM reconstructed prose
                                "identified_question": r.get("identified_question", ""),  # Question identified from OCR blocks
                                "text_length": len(r.get("text", "")),
                                "full_text_length": len(r.get("full_text", "")),
                                "reconstructed_length": len(r.get("reconstructed_text", "")),
                                "num_blocks": len(r.get("blocks", [])),
                                "width": r.get("width", 0),
                                "height": r.get("height", 0),
                                "blocks": r.get("blocks", []),  # Include raw blocks data (with conf) sent to LLM
                                "ocr_method": "google_vision"
                            }
                            for r in ocr_results
                        ],
                        "message": f"OCR complete. PDF generated: {pdf_filename}"
                    })
                    continue
                        
                except Exception as roi_error:
                    logger.error(f"   ❌ ROI + OCR processing failed: {roi_error}")
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "failed",
                        "reason": f"ROI + OCR processing failed: {str(roi_error)}"
                    })
                    continue
            else:
                processed_files_summary.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"Unsupported file type: {file_ext}. Supported: PDF, TXT, JPG, PNG, GIF, BMP, TIFF"
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

            # Classify chunks with GPT-4o-mini and store in Pinecone
            if chunks:
                try:
                    # Print diagnostics for chunks before classification
                    logger.info(f"\n📊 Chunking Diagnostics:")
                    logger.info(f"   • Total chunks created: {len(chunks)}")
                    if chunks:
                        sample = chunks[0]
                        logger.info(f"   • Sample chunk metadata keys: {list(sample.get('metadata', {}).keys())}")
                        logger.info(f"   • Sample chunk size: {len(sample['content'].split())} words")
                        logger.info(f"   • Sample chapter: {sample.get('metadata', {}).get('chapter', 'N/A')}")
                        logger.info(f"   • Sample section: {sample.get('metadata', {}).get('section', 'N/A')}")
                    
                    # Step 1: Classify chunks with GPT-4o-mini (batch processing)
                    logger.info(f"\n🤖 Classifying {len(chunks)} chunks with GPT-4o-mini (batch processing)...")
                    from ..utils.metadata_enricher import classify_chunks_batch
                    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    
                    # Classify all chunks in batches
                    classified_chunks = classify_chunks_batch(chunks, openai_client)
                    
                    logger.info(f"✅ Classification complete for {len(classified_chunks)} chunks")
                    
                    # Show first 3 chunks with classification
                    logger.info(f"\n📝 First 3 chunks with classification:")
                    for i, chunk in enumerate(classified_chunks[:3], 1):
                        meta = chunk.get('metadata', {})
                        logger.info(f"\n   Chunk {i}:")
                        logger.info(f"      • Content preview: {chunk['content'][:150].replace(chr(10), ' ')}...")
                        logger.info(f"      • Word count: {len(chunk['content'].split())} words")
                        logger.info(f"      • Major Domain: {meta.get('major_domain', 'N/A')}")
                        logger.info(f"      • Sub Domain: {meta.get('sub_domain', 'N/A')}")
                        logger.info(f"      • Micro Topic: {meta.get('micro_topic', 'N/A')}")
                        if meta.get('sub_topics'):
                            logger.info(f"      • Sub Topics: {', '.join(meta.get('sub_topics', []))}")
                        logger.info(f"      • Full Metadata: {meta}")
                    
                    # Step 2: Store classified chunks in Pinecone (this will generate embeddings automatically)
                    logger.info(f"\n💾 Storing {len(classified_chunks)} chunks in Pinecone (generating embeddings)...")
                    vector_handler.add_documents(classified_chunks)
                    logger.info(f"✅ Successfully stored {len(classified_chunks)} chunks in Pinecone")
                    
                    # Prepare summary
                    summary_item = {
                        "filename": file.filename,
                        "status": "success",
                        "chunks_created": len(chunks),
                        "chunks_stored": len(chunks),
                        "message": "Chunks created and stored successfully in Pinecone"
                    }
                    
                    # Add ROI preview paths if available
                    if roi_info:
                        if "roi_preview_paths" in roi_info:
                            summary_item["roi_preview_paths"] = roi_info["roi_preview_paths"]
                        elif "roi_preview_path" in roi_info:
                            summary_item["roi_preview_path"] = roi_info["roi_preview_path"]
                        summary_item["roi_method"] = roi_info.get("roi_method")
                    
                    processed_files_summary.append(summary_item)
                    logger.info(f"✅ Successfully processed and stored {len(chunks)} chunks for {file.filename}")
                    
                except Exception as storage_error:
                    # Chunks were created but storage failed
                    logger.error(f"❌ Chunks created but storage failed for {file.filename}: {storage_error}")
                    processed_files_summary.append({
                        "filename": file.filename,
                        "status": "failed",
                        "reason": f"Storage failed: {str(storage_error)}",
                        "chunks_created": len(chunks),
                        "chunks_stored": 0
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