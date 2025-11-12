"""
Streamlit frontend for Study Buddy AI
"""
import streamlit as st
import requests
import time
import re
from typing import List, Dict, Any
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8003")

def check_backend_status() -> bool:
    """Check if backend is running"""
    try:
        response = requests.get(f"{BACKEND_URL}/")
        return response.status_code == 200
    except:
        return False

# Page config
st.set_page_config(
    page_title="Study Buddy AI",
    page_icon="📚",
    layout="wide"
)

# Title
st.title("📚 Study Buddy AI - Geography Q&A")

# Check backend status
backend_status = check_backend_status()

# Sidebar
with st.sidebar:
    st.title("Navigation")
    tab_choice = st.radio(
        "Choose a feature:",
        ["Upload PDFs", "Ask Questions", "Generate Mock Test", "UPSC Mains Answer", "Evaluate Answer"]
    )

    if backend_status:
        st.success("✅ Backend server is running")
    else:
        st.error("❌ Backend server is not running")
        st.info("Please start the backend server first")

# Main content based on tab selection
if tab_choice == "Upload PDFs":
    st.header("📤 Upload Your Study Materials")
    
    # Initialize session state
    if "processed_files" not in st.session_state:
        st.session_state.processed_files = set()
    if "upload_type" not in st.session_state:
        st.session_state.upload_type = "PDF"
    
    # Document Type Selection
    st.subheader("📋 Select Document Type")
    upload_type = st.radio(
        "Choose document type:",
        ["PDF", "Handwritten"],
        index=0 if st.session_state.upload_type == "PDF" else 1,
        disabled=not backend_status,
        key="upload_type_radio",
        help="PDF: Regular text-based PDFs or TXT files. Handwritten: Scanned handwritten answers (PDF/images) that will be processed with OCR."
    )
    st.session_state.upload_type = upload_type
    
    if upload_type == "PDF":
        st.info("💡 Upload regular PDF or TXT files. They will be chunked, enriched, and embedded for use in Q&A and answer generation.")
    else:
        st.info("💡 Upload handwritten answer sheets (PDF or images). They will be processed with ROI detection, OCR, and LLM reconstruction, then chunked and embedded to strengthen answer generation.")
    
    st.divider()
    
    # Main File Upload Section
    st.subheader("📄 Upload Documents")
    
    # File upload based on type
    dpi = None
    if upload_type == "PDF":
        uploaded_files = st.file_uploader(
            "Upload PDF or TXT files:",
            type=["pdf", "txt"],
            accept_multiple_files=True,
            disabled=not backend_status,
            key="pdf_uploader"
        )
    else:
        # Handwritten: Show DPI selection and accept PDF/images
        dpi = st.selectbox(
            "DPI for PDF conversion (higher = better quality, slower processing):",
            [300, 600],
            index=1,  # Default to 600
            disabled=not backend_status,
            help="600 DPI provides better clarity for handwritten text but takes longer to process"
        )
        uploaded_files = st.file_uploader(
            "Upload handwritten answer sheets (PDF or images):",
            type=["pdf", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            disabled=not backend_status,
            key="handwritten_uploader"
        )
    
    # Filter out already processed files
    if uploaded_files:
        new_files = []
        already_processed = []
        
        for file in uploaded_files:
            if file.name in st.session_state.processed_files:
                already_processed.append(file.name)
            else:
                new_files.append(file)
        
        if already_processed:
            st.warning(f"⚠️ The following files have already been processed and will be skipped: {', '.join(already_processed)}")
        
        uploaded_files = new_files  # Only process new files
    
    # Show list of already processed files
    if st.session_state.processed_files:
        with st.expander("📋 Already Processed Files", expanded=False):
            processed_list = sorted(list(st.session_state.processed_files))
            for filename in processed_list:
                st.text(f"✅ {filename}")
            if st.button("🗑️ Clear Processed Files List", help="Clear the list to allow re-uploading these files"):
                st.session_state.processed_files = set()
                st.rerun()

    # Initialize processing state
    if "processing_files" not in st.session_state:
        st.session_state.processing_files = False
    if "processing_content_store" not in st.session_state:
        st.session_state.processing_content_store = False
    if "last_roi_previews" not in st.session_state:
        st.session_state.last_roi_previews = {}
    
    # Upload Type Selection (Pinecone vs Content Store)
    st.divider()
    st.subheader("🎯 Upload Destination")
    upload_destination = st.radio(
        "Choose where to upload:",
        ["Pinecone (Normal Upload)", "Content Store (Full Text Storage)"],
        disabled=not backend_status,
        help="Pinecone: Normal upload with embeddings. Content Store: Store full text for RetrievalQA (no embeddings, faster)."
    )
    
    # Process Files button with state
    if upload_destination == "Pinecone (Normal Upload)":
        process_button_label = "⏳ Processing..." if st.session_state.processing_files else "🚀 Process Files to Pinecone"
        process_button_disabled = (not backend_status or st.session_state.processing_files or st.session_state.processing_content_store)
    else:
        process_button_label = "⏳ Processing..." if st.session_state.processing_content_store else "💾 Store Full Text in Content Store"
        process_button_disabled = (not backend_status or st.session_state.processing_files or st.session_state.processing_content_store)
    
    if uploaded_files and st.button(process_button_label, disabled=process_button_disabled, type="primary"):
        # Route to appropriate endpoint based on selection
        if upload_destination == "Content Store (Full Text Storage)":
            # Content Store Upload (no embeddings, just full text storage)
            st.session_state.processing_content_store = True
            
            # Show file types being processed
            file_types = {}
            for file in uploaded_files:
                ext = file.name.split('.')[-1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
            
            file_type_summary = ", ".join([f"{count} {ext.upper()}" for ext, count in file_types.items()])
            
            # Create status container
            status_container = st.container()
            with status_container:
                st.info(f"💾 Storing full text in Content Store: {file_type_summary} file(s)...")
                progress_bar = st.progress(0)
                status_text = st.empty()
            
            with st.spinner(f"Storing full text for {file_type_summary} file(s)..."):
                files = [("files", file) for file in uploaded_files]
                
                try:
                    status_text.text("📤 Uploading files to content store...")
                    progress_bar.progress(20)
                    
                    # Call content store upload endpoint
                    # Route: POST /upload-content-store/ (prefix + route)
                    response = requests.post(f"{BACKEND_URL}/upload-content-store/", files=files, timeout=300)
                    
                    status_text.text("📥 Receiving response...")
                    progress_bar.progress(80)
                    
                    if response.status_code == 200:
                        result = response.json()
                        progress_bar.progress(100)
                        status_text.text("✅ Content store upload complete!")
                        
                        # Show results
                        st.success(f"✅ Successfully stored chunks in content store!")
                        st.info(f"📊 **Summary:** {result.get('message', '')}")
                        
                        # Show processed files
                        processed_files_list = result.get('processed_files', [])
                        for pf in processed_files_list:
                            if 'error' in pf:
                                st.error(f"❌ {pf['filename']}: {pf['error']}")
                            else:
                                st.success(f"✅ {pf['filename']}: {pf.get('chunks_stored', 0)} chunks stored")
                        
                        # Show content store stats
                        stats = result.get('content_store_stats', {})
                        if stats:
                            with st.expander("📊 Content Store Statistics", expanded=False):
                                st.json(stats)
                        
                        # Show matching results (for first 5 uploads)
                        matching = result.get('matching_results')
                        if matching and result.get('sample_check'):
                            st.divider()
                            st.subheader("🔍 Sample Matching Results (First 5 Uploads)")
                            st.info(f"**Match Rate:** {matching.get('match_rate', 0):.1%} ({matching.get('samples_checked', 0)} samples checked)")
                            
                            if matching.get('matches'):
                                st.success(f"✅ **Matches:** {len(matching['matches'])}")
                                with st.expander("View Sample Matches", expanded=False):
                                    for match in matching['matches'][:5]:
                                        st.text(f"• {match['content_chunk_id']} (score: {match['match']['score']})")
                            
                            if matching.get('no_matches'):
                                st.warning(f"⚠️ **No Matches:** {len(matching['no_matches'])}")
                                with st.expander("View Non-Matches", expanded=False):
                                    for no_match in matching['no_matches'][:5]:
                                        st.text(f"• {no_match['chunk_id']} (best score: {no_match.get('best_score', 0)})")
                        
                        st.session_state.processing_content_store = False
                        st.rerun()
                    else:
                        error_msg = response.text
                        st.error(f"❌ Content store upload failed: {error_msg}")
                        st.session_state.processing_content_store = False
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.session_state.processing_content_store = False
        
        else:
            # Normal Pinecone Upload (existing code)
            st.session_state.processing_files = True
            
            # Show file types being processed
            file_types = {}
            for file in uploaded_files:
                ext = file.name.split('.')[-1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
            
            file_type_summary = ", ".join([f"{count} {ext.upper()}" for ext, count in file_types.items()])
            
            # Create status container
            status_container = st.container()
            with status_container:
                if upload_type == "Handwritten":
                    st.info(f"🔄 Processing {file_type_summary} file(s) at {dpi} DPI...")
                else:
                    st.info(f"🔄 Processing {file_type_summary} file(s)...")
                progress_bar = st.progress(0)
                status_text = st.empty()
            
            spinner_text = f"Processing {file_type_summary} file(s)..." if upload_type == "PDF" else f"Processing {file_type_summary} file(s) at {dpi} DPI..."
            with st.spinner(spinner_text):
                files = [("files", file) for file in uploaded_files]
                data = {}
                
                # Add DPI only for handwritten documents
                if upload_type == "Handwritten":
                    data["dpi"] = dpi
                # Note: No sample_sheet_path for Upload PDFs tab (moved to Evaluate Answer tab)
                
                try:
                    status_text.text("📤 Uploading files to server...")
                    progress_bar.progress(10)
                    
                    # Timeout set to 300 seconds (5 minutes) to allow OCR processing time
                    # OCR can take 12-25 seconds per page on CPU, so longer timeout is needed
                    response = requests.post(f"{BACKEND_URL}/upload/", files=files, data=data, timeout=300)
                    
                    status_text.text("📥 Receiving response...")
                    progress_bar.progress(50)
                    
                    if response.status_code == 200:
                        results = response.json()["summary"]
                        
                        status_text.text("✅ Processing complete!")
                        progress_bar.progress(100)
                        
                        # Track successfully processed files
                        successfully_processed = []
                        failed_files = []
                        roi_previews = {}  # Store ROI preview info
                        
                        for result in results:
                            if result["status"] == "success":
                                filename = result['filename']
                                successfully_processed.append(filename)
                                
                                # Display success info
                                chunks_added = result.get('chunks_added', 0)
                                pdf_download_url = result.get('pdf_download_url')
                                ocr_results = result.get('ocr_results', [])
                                
                                # Debug: Show what we received
                                if st.session_state.get('debug_mode', False):
                                    with st.expander("🔍 Debug: Response Data", expanded=False):
                                        st.json(result)
                                
                                if chunks_added > 0:
                                    st.session_state.processed_files.add(filename)
                                    st.info(f"📄 {filename}: Added {chunks_added} chunks")
                                
                                # Show OCR results if we have pdf_download_url OR ocr_results
                                if pdf_download_url or ocr_results:
                                    # OCR complete - show download button and OCR results
                                    st.success(f"✅ {filename}: OCR complete! PDF generated.")
                                    
                                    # Show OCR results summary
                                    if ocr_results:
                                        avg_confidence = sum(r.get('confidence', 0) for r in ocr_results) / len(ocr_results) if ocr_results else 0
                                        ocr_methods = [r.get('ocr_method', 'unknown') for r in ocr_results]
                                        unique_methods = list(set(ocr_methods))
                                        
                                        col_info1, col_info2, col_info3 = st.columns(3)
                                        with col_info1:
                                            st.metric("Pages", len(ocr_results))
                                        with col_info2:
                                            st.metric("Avg Confidence", f"{avg_confidence:.1%}")
                                        with col_info3:
                                            st.metric("OCR Method", ", ".join(unique_methods).upper() if unique_methods else "N/A")
                                        
                                        # Show per-page confidence if multiple pages
                                        if len(ocr_results) > 1:
                                            with st.expander("📊 Per-Page Confidence Scores", expanded=False):
                                                for ocr_result in ocr_results:
                                                    page_num = ocr_result.get('page_number', '?')
                                                    conf = ocr_result.get('confidence', 0)
                                                    method = ocr_result.get('ocr_method', 'unknown')
                                                    text_len = ocr_result.get('text_length', 0)
                                                    
                                                    # Color code confidence
                                                    if conf >= 0.7:
                                                        conf_color = "🟢"
                                                    elif conf >= 0.5:
                                                        conf_color = "🟡"
                                                    else:
                                                        conf_color = "🔴"
                                                    
                                                    st.markdown(
                                                        f"**Page {page_num}:** {conf_color} {conf:.1%} "
                                                        f"({method.upper()}, {text_len} chars)"
                                                    )
                                        
                                        # Show OCR text preview with reconstructed text
                                        with st.expander("📝 OCR Results Preview", expanded=True):
                                            for idx, ocr_result in enumerate(ocr_results):
                                                page_num = ocr_result.get('page_number', idx + 1)
                                                original_text = ocr_result.get('text', '')
                                                reconstructed_text = ocr_result.get('reconstructed_text', '')
                                                text_length = ocr_result.get('text_length', len(original_text))
                                                reconstructed_length = ocr_result.get('reconstructed_length', len(reconstructed_text))
                                                num_blocks = ocr_result.get('num_blocks', 0)
                                                blocks = ocr_result.get('blocks', [])  # Raw blocks sent to LLM
                                                
                                                if len(ocr_results) > 1:
                                                    st.markdown(f"### Page {page_num}")
                                                
                                                # Show block count
                                                if num_blocks > 0:
                                                    st.info(f"📊 Extracted {num_blocks} text blocks from OCR")
                                                
                                                # Show OCR blocks sent to LLM (BEFORE reconstruction)
                                                if blocks:
                                                    with st.expander("🔍 OCR Blocks Sent to LLM (Before Reconstruction)", expanded=False):
                                                        st.markdown("**These are the raw OCR blocks with bounding boxes that were sent to the LLM:**")
                                                        st.json(blocks)
                                                        st.caption(f"💡 This is the exact data sent to LLM for reconstruction. {len(blocks)} blocks with text and bbox coordinates.")
                                                
                                                # Show reconstructed text (primary display)
                                                if reconstructed_text:
                                                    st.markdown("#### 🤖 LLM Reconstructed Text (Clean Prose)")
                                                    st.markdown("**This is the reconstructed answer in clean, readable prose:**")
                                                    st.text_area(
                                                        f"Reconstructed text ({reconstructed_length} chars)",
                                                        reconstructed_text,
                                                        height=300,
                                                        key=f"reconstructed_text_{filename}_{page_num}",
                                                        disabled=True
                                                    )
                                                    st.caption("💡 This text was reconstructed by LLM from OCR blocks, preserving meaning and structure.")
                                                
                                                # Show original OCR text (for comparison)
                                                if original_text:
                                                    with st.expander("📄 Original OCR Text (Raw)", expanded=False):
                                                        st.markdown("**Original merged OCR text (for reference):**")
                                                        text_preview = original_text[:1000] if len(original_text) > 1000 else original_text
                                                        st.text_area(
                                                            f"Original OCR text (showing first 1000 chars of {text_length} total)",
                                                            text_preview,
                                                            height=200,
                                                            key=f"ocr_text_{filename}_{page_num}",
                                                            disabled=True
                                                        )
                                                        if text_length > 1000:
                                                            st.caption(f"💡 Showing first 1000 characters. Full text available in PDF download.")
                                                
                                                if idx < len(ocr_results) - 1:
                                                    st.divider()
                                    
                                    # Download button
                                    if pdf_download_url:
                                        pdf_filename = result.get('pdf_filename', f"{filename}_ocr.pdf")
                                        download_url = f"{BACKEND_URL}{pdf_download_url}"
                                        
                                        st.markdown("---")
                                        col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
                                        with col_dl2:
                                            st.markdown(f"### 📥 Download OCR PDF")
                                            st.markdown(f"**File:** `{pdf_filename}`")
                                            st.markdown(f"[⬇️ Download PDF]({download_url})")
                                            st.caption("💡 Click the link above to download the PDF with extracted OCR text")
                                    else:
                                        st.warning("⚠️ PDF download URL not available. Check backend logs.")
                                elif not chunks_added:
                                    # ROI extracted but OCR pending or failed
                                    message = result.get('message', 'ROI extracted, OCR pending')
                                    st.warning(f"📄 {filename}: {message}")
                                
                                    # Check for ROI preview paths
                                    if "roi_preview_paths" in result:
                                        roi_previews[filename] = {
                                            "paths": result["roi_preview_paths"],
                                            "method": result.get("roi_method", "unknown"),
                                            "chunks_added": chunks_added,
                                            "pdf_download_url": pdf_download_url,
                                            "ocr_results": ocr_results
                                        }
                                    elif "roi_preview_path" in result:
                                        roi_previews[filename] = {
                                            "paths": [result["roi_preview_path"]],
                                            "method": result.get("roi_method", "unknown"),
                                            "chunks_added": chunks_added,
                                            "pdf_download_url": pdf_download_url,
                                            "ocr_results": ocr_results
                                        }
                            else:
                                failed_files.append(result['filename'])
                                # Show detailed error information
                                with st.expander(f"❌ {result['filename']}: {result['reason']}", expanded=True):
                                    st.error(f"**Status:** {result['status']}")
                                    st.error(f"**Reason:** {result['reason']}")
                                    
                                    # Show quality score if available
                                    if 'quality_score' in result:
                                        st.warning(f"**Quality Score:** {result['quality_score']}/100")
                                    
                                    # Show issues if available
                                    if 'issues' in result and result['issues']:
                                        st.write("**Issues Found:**")
                                        for issue in result['issues']:
                                            st.write(f"  - {issue}")
                                    
                                    # Show recommendation if available
                                    if 'recommendation' in result and result['recommendation']:
                                        st.info(f"**💡 Recommendation:** {result['recommendation']}")
                        
                        # Store ROI previews in session state for later viewing
                        if roi_previews:
                            st.session_state.last_roi_previews = roi_previews
                        
                        # Show summary
                        if successfully_processed:
                            st.success(f"✅ Successfully processed {len(successfully_processed)} file(s)!")
                            st.info(f"📝 Processed files: {', '.join(successfully_processed)}")
                        elif failed_files:
                            st.error(f"❌ Failed to process {len(failed_files)} file(s)")
                        
                        # Clear processing state
                        st.session_state.processing_files = False
                        
                        # Clear status container
                        status_container.empty()
                        progress_bar.empty()
                        status_text.empty()
                        
                        # Clear the file uploader by rerunning
                        st.rerun()
                    else:
                        st.error("Failed to process files")
                        st.session_state.processing_files = False
                        status_container.empty()
                        progress_bar.empty()
                        status_text.empty()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.session_state.processing_files = False
                    if 'status_container' in locals():
                        status_container.empty()
                if 'progress_bar' in locals():
                    progress_bar.empty()
                if 'status_text' in locals():
                    status_text.empty()
    
    # Show ROI previews button (always available if we have previews)
    if st.session_state.last_roi_previews:
        st.divider()
        if "show_roi_previews" not in st.session_state:
            st.session_state.show_roi_previews = False
        
        col_prev1, col_prev2 = st.columns([1, 3])
        with col_prev1:
            if st.button("👁️ View ROI Previews", type="secondary"):
                st.session_state.show_roi_previews = not st.session_state.show_roi_previews
                st.rerun()
        
        if st.session_state.show_roi_previews:
            st.subheader("🔍 ROI Previews")
            st.info("💡 These are the preprocessed ROI images that will be used for OCR. Review to ensure ROI detection is correct.")
            
            for filename, roi_info in st.session_state.last_roi_previews.items():
                chunks_info = f" ({roi_info.get('chunks_added', 0)} chunks)" if roi_info.get('chunks_added', 0) > 0 else " (OCR pending)"
                with st.expander(f"📷 ROI Previews for {filename} (Method: {roi_info['method']}){chunks_info}", expanded=True):
                    preview_paths = roi_info["paths"]
                    for i, preview_path in enumerate(preview_paths):
                        if preview_path:
                            # Extract relative path for URL
                            relative_path = preview_path.replace("data/roi_previews/", "")
                            preview_url = f"{BACKEND_URL}/upload/roi-preview/{relative_path}"
                            
                            st.markdown(f"**Page {i+1} - Detected ROI Area:**")
                            try:
                                st.image(preview_url, caption=f"ROI Preview - Page {i+1} (Shows detected answer area before preprocessing)")
                            except Exception as e:
                                st.error(f"Failed to load preview: {e}")
                                st.text(f"URL: {preview_url}")
                            
                            # Show what preprocessing will be done
                            st.caption(f"💡 This ROI area will be preprocessed for OCR: Grayscale → Median Blur → Bilateral Filter → CLAHE → Deskew → Morphological Operations → Adaptive Threshold")

elif tab_choice == "Ask Questions":
    st.header("❓ Ask Questions")
    
    question = st.text_area(
        "Enter your Geography question:",
        disabled=not backend_status
    )

    if st.button("Get Answer", disabled=not backend_status):
        if question:
            with st.spinner("Finding answer..."):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/query/",
                        json={"question": question},
                        timeout=30
                    )
                    if response.status_code == 200:
                        data = response.json()
                        st.subheader("Answer:")
                        st.write(data["answer"])
                        
                        if data.get("sources"):
                            st.subheader("Sources:")
                            for source in data["sources"]:
                                source_info = f"- **File:** `{source.get('filename', 'Unknown')}`"
                                if source.get('chapter') and source.get('chapter') != 'Unknown':
                                    source_info += f", **Chapter:** `{source['chapter']}`"
                                if source.get('section') and source.get('section') != 'Unknown':
                                    source_info += f", **Section:** `{source['section']}`"
                                if source.get('page_number'):
                                    source_info += f", **Page:** `{source['page_number']}`"
                                st.markdown(source_info)
                    else:
                        st.error("Failed to get answer")
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Please try again.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            st.warning("Please enter a question")

elif tab_choice == "Generate Mock Test":
    st.header("📝 Generate Mock Test")
    
    # Initialize session state for test data and explanations
    if "mock_test_data" not in st.session_state:
        st.session_state.mock_test_data = None
    if "show_explanations" not in st.session_state:
        st.session_state.show_explanations = {}
    
    col1, col2 = st.columns(2)
    
    with col1:
        num_questions = st.number_input(
            "Number of questions:",
            min_value=5,
            max_value=20,
            value=5,
            disabled=not backend_status,
            help="Minimum 5 questions required"
        )
        
        difficulty = st.select_slider(
            "Difficulty level:",
            options=["easy", "medium", "hard"],
            value="medium",
            disabled=not backend_status
        )
    
    with col2:
        # Domain and Sub-domain selection
        st.markdown("**Select domain and sub-domain (optional):**")
        
        # Fetch geography domains from backend
        geography_domains = {}
        try:
            if backend_status:
                response = requests.get(f"{BACKEND_URL}/mock-test/domains", timeout=5)
                if response.status_code == 200:
                    geography_domains = response.json().get("domains", {})
        except Exception as e:
            st.warning(f"Could not load domains: {e}")
            # Fallback to hardcoded domains
            geography_domains = {
                "Physical Geography": [
                    "Geomorphology", "Climatology", "Oceanography",
                    "Biogeography", "Natural Disasters"
                ],
                "Human Geography": [
                    "Economic Geography", "Cultural Geography", "Models and Theories",
                    "Population Geography", "Settlements", "Migration"
                ],
                "Indian Geography": [
                    "Indian Physiography", "Indian Drainage System", "Indian Climate",
                    "Indian Soils", "Indian Agriculture", "Indian Natural Resources",
                    "Indian Industries", "Transport and Communication", "Regional Planning"
                ],
                "World Geography": [
                    "Continents and Countries", "Major Physical Features",
                    "Environmental Challenges", "Political and Physical Features",
                    "Mapping and Cartography"
                ]
            }
        
        # Domain dropdown
        domain_options = [""] + list(geography_domains.keys())
        selected_domain = st.selectbox(
            "Domain:",
            options=domain_options,
            index=0,
            disabled=not backend_status,
            key="domain_select"
        )
        
        # Sub-domain dropdown (populated based on selected domain)
        topics = []
        if selected_domain and selected_domain in geography_domains:
            sub_domain_options = [""] + geography_domains[selected_domain]
            selected_sub_domain = st.selectbox(
                "Sub-domain:",
                options=sub_domain_options,
                index=0,
                disabled=not backend_status,
                key="sub_domain_select"
            )
            
            if selected_sub_domain:
                topics.append(selected_sub_domain)
            
            # Allow typing custom sub-domain
            custom_sub_domain = st.text_input(
                "Or type a custom sub-domain:",
                placeholder="e.g., Cyclones, Monsoon Variability, etc.",
                disabled=not backend_status,
                key="custom_sub_domain_input"
            )
            
            if custom_sub_domain and custom_sub_domain.strip():
                topics.append(custom_sub_domain.strip())
        else:
            # If no domain selected, allow free-form topic input
            custom_topic = st.text_input(
                "Or type a custom topic:",
                placeholder="e.g., Cyclones, Monsoon Variability, etc.",
                disabled=not backend_status,
                key="custom_topic_input"
            )
            
            if custom_topic and custom_topic.strip():
                topics.append(custom_topic.strip())
    
    # Generate new test button
    col_gen, col_clear = st.columns([1, 1])
    with col_gen:
        generate_clicked = st.button("Generate Test", disabled=not backend_status)
    with col_clear:
        if st.button("Clear Test", disabled=not backend_status):
            st.session_state.mock_test_data = None
            st.session_state.show_explanations = {}
            st.session_state.user_answers = {}
            st.session_state.scores = {}
            st.session_state.test_submitted = False
            st.session_state.question_feedback = {}
            st.session_state.test_topics = []
            st.session_state.test_difficulty = "medium"
            st.rerun()

    # Generate test if button clicked
    if generate_clicked:
        with st.spinner("Generating mock test..."):
            try:
                # Increased timeout to account for multiple processing steps:
                # - MMR retrieval (fetch_k up to 54 candidates)
                # - Content store enrichment (concept + PYQ)
                # - Recency filtering
                # - Source diversity
                # - Final MMR re-ranking
                response = requests.post(
                    f"{BACKEND_URL}/mock-test/generate",
                    json={
                        "num_questions": num_questions,
                        "topics": topics,
                        "difficulty": difficulty
                    },
                    timeout=180  # Increased from 60 to 180 seconds (3 minutes) for complex processing
                )
                
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.mock_test_data = data
                    st.session_state.show_explanations = {}  # Reset explanations
                    st.session_state.user_answers = {}  # Reset answers
                    st.session_state.scores = {}  # Reset scores
                    st.session_state.test_submitted = False  # Reset submission state
                    st.session_state.test_topics = topics  # Store topics for feedback
                    st.session_state.test_difficulty = difficulty  # Store difficulty for feedback
                    st.session_state.question_feedback = {}  # Reset feedback tracking
                    st.rerun()
                else:
                    st.error("Failed to generate mock test")
            
            except requests.exceptions.Timeout:
                st.error("Request timed out. Please try again.")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Display test if data exists in session state
    if st.session_state.mock_test_data:
        data = st.session_state.mock_test_data
        
        # Show test instructions
        st.info("📋 Test Instructions:")
        for instruction in data["instructions"]:
            st.markdown(f"- {instruction}")
        
        st.info(f"⏱️ Time allowed: {data['time_allowed']}")
        st.info(f"📊 Total marks: {len(data['questions']) * 2} (2 marks per question, -0.67 for wrong answer)")
        
        # Initialize score tracking and submission state
        if "user_answers" not in st.session_state:
            st.session_state.user_answers = {}
        if "scores" not in st.session_state:
            st.session_state.scores = {}
        if "test_submitted" not in st.session_state:
            st.session_state.test_submitted = False
        if "question_feedback" not in st.session_state:
            st.session_state.question_feedback = {}
        if "test_topics" not in st.session_state:
            st.session_state.test_topics = []
        if "test_difficulty" not in st.session_state:
            st.session_state.test_difficulty = "medium"
        
        # Progress indicator at top
        if not st.session_state.test_submitted:
            answered_count = len(st.session_state.user_answers)
            total_questions = len(data["questions"])
            progress = answered_count / total_questions if total_questions > 0 else 0
            st.progress(progress, text=f"📊 Progress: {answered_count} / {total_questions} questions answered")
        
        # Show questions
        for i, q in enumerate(data["questions"], 1):
            st.markdown("---")
            
            # Create two columns: left for question, right for rating buttons
            question_col, rating_col = st.columns([4, 1])
            
            with question_col:
                # Question number and text in a styled container (dark mode compatible)
                with st.container():
                    # Show question status indicator if submitted
                    status_indicator = ""
                    if st.session_state.test_submitted:
                        user_answer = st.session_state.user_answers.get(i)
                        correct_answer = q.get('correct_answer', '').upper()
                        if user_answer == correct_answer:
                            status_indicator = " ✅"
                        elif user_answer:
                            status_indicator = " ❌"
                        else:
                            status_indicator = " ⚠️"
                    
                    st.markdown(f"### Question {i} of {len(data['questions'])}{status_indicator}")
            
            with rating_col:
                # Rating buttons (High, Medium, Low) - positioned on the right
                st.markdown("<br>", unsafe_allow_html=True)  # Spacing
                st.markdown("**Rate Question:**")
                
                # Get question text for feedback (use the raw question text)
                question_text_for_feedback = q['question']
                current_feedback = st.session_state.question_feedback.get(i)
                
                # Get topic and difficulty for feedback
                topic = st.session_state.test_topics[0] if st.session_state.test_topics else "Geography"
                difficulty = st.session_state.test_difficulty
                
                # High button
                high_key = f"rate_high_{i}"
                high_clicked = st.button("⭐ High", key=high_key, use_container_width=True, 
                                        type="primary" if current_feedback == "high" else "secondary")
                
                # Medium button
                med_key = f"rate_med_{i}"
                med_clicked = st.button("✓ Medium", key=med_key, use_container_width=True,
                                       type="primary" if current_feedback == "medium" else "secondary")
                
                # Low button
                low_key = f"rate_low_{i}"
                low_clicked = st.button("○ Low", key=low_key, use_container_width=True,
                                       type="primary" if current_feedback == "low" else "secondary")
                
                # Handle button clicks
                if high_clicked:
                    try:
                        feedback_response = requests.post(
                            f"{BACKEND_URL}/feedback/",
                            json={
                                "question_text": question_text_for_feedback,
                                "topic": topic,
                                "difficulty": difficulty,
                                "quality": "high",
                                "reason": None
                            },
                            timeout=5
                        )
                        if feedback_response.status_code == 200:
                            st.session_state.question_feedback[i] = "high"
                            st.success("✅ Rated as High quality!")
                            st.rerun()
                        else:
                            st.error("Failed to submit feedback")
                    except Exception as e:
                        st.error(f"Error submitting feedback: {str(e)}")
                
                elif med_clicked:
                    try:
                        feedback_response = requests.post(
                            f"{BACKEND_URL}/feedback/",
                            json={
                                "question_text": question_text_for_feedback,
                                "topic": topic,
                                "difficulty": difficulty,
                                "quality": "medium",
                                "reason": None
                            },
                            timeout=5
                        )
                        if feedback_response.status_code == 200:
                            st.session_state.question_feedback[i] = "medium"
                            st.success("✅ Rated as Medium quality!")
                            st.rerun()
                        else:
                            st.error("Failed to submit feedback")
                    except Exception as e:
                        st.error(f"Error submitting feedback: {str(e)}")
                
                elif low_clicked:
                    try:
                        feedback_response = requests.post(
                            f"{BACKEND_URL}/feedback/",
                            json={
                                "question_text": question_text_for_feedback,
                                "topic": topic,
                                "difficulty": difficulty,
                                "quality": "low",
                                "reason": None
                            },
                            timeout=5
                        )
                        if feedback_response.status_code == 200:
                            st.session_state.question_feedback[i] = "low"
                            st.success("✅ Rated as Low quality!")
                            st.rerun()
                        else:
                            st.error("Failed to submit feedback")
                    except Exception as e:
                        st.error(f"Error submitting feedback: {str(e)}")
                
                # Show current rating if exists
                if current_feedback:
                    st.caption(f"Current: {current_feedback.title()}")
            
            # Continue with question display in the left column
            with question_col:
                
                # Format question text with enhanced formatting for different question types
                question_text = q['question']
                question_text = question_text.replace('\\n', '\n')  # Handle escaped newlines
                
                # Detect question type and format accordingly
                is_assertion_reason = 'Assertion' in question_text and 'Reason' in question_text
                is_match_pair = 'List I' in question_text and 'List II' in question_text
                # Statement questions: "Consider the following statements" + numbered items (1., 2., 3.) + question
                is_statements_question = (
                    'Consider the following' in question_text and 
                    ('statement' in question_text.lower() or 'statements' in question_text.lower()) and
                    re.search(r'\d+\.', question_text)  # Has numbered statements
                )
                
                if is_statements_question:
                    # Format Statement questions: "Consider the following statements regarding..."
                    # Pattern: "Consider the following statements..." + numbered statements + question
                    statements_match = re.search(
                        r'(Consider the following.*?statements.*?:)(.*?)(Which of the following.*?statements.*?\?|Select.*?\?|Choose.*?\?)',
                        question_text,
                        re.IGNORECASE | re.DOTALL
                    )
                    
                    if statements_match:
                        intro_text = statements_match.group(1).strip()
                        statements_text = statements_match.group(2).strip()
                        question_part = statements_match.group(3).strip() if statements_match.lastindex >= 3 else ""
                        
                        # Extract numbered statements (handle multi-line statements)
                        statements = []
                        # First try: match numbered items that may span multiple lines
                        statement_pattern = r'(\d+\.\s*[^\n]+(?:\n(?!\d+\.)[^\n]+)*)'
                        matches = re.finditer(statement_pattern, statements_text)
                        for match in matches:
                            stmt = match.group(1).strip()
                            if stmt:
                                statements.append(stmt)
                        
                        # Fallback: if no matches, split by numbered items
                        if not statements:
                            parts = re.split(r'(\d+\.)', statements_text)
                            current_stmt = ""
                            for part in parts:
                                if re.match(r'^\d+\.$', part.strip()):
                                    if current_stmt:
                                        statements.append(current_stmt.strip())
                                    current_stmt = part + " "
                                else:
                                    current_stmt += part
                            if current_stmt:
                                statements.append(current_stmt.strip())
                        
                        # Build formatted HTML with proper alignment
                        statements_html = "<div style='padding: 20px; background-color: rgba(255, 253, 250, 1); border-left: 4px solid #d4a574; border-radius: 5px; margin: 15px 0; line-height: 1.8;'>"
                        statements_html += f"<div style='font-weight: bold; margin-bottom: 12px; color: #8b6f47; font-size: 16px;'>{intro_text}</div>"
                        
                        # Display statements in a clean, aligned list with minimal spacing
                        statements_html += "<div style='margin-left: 10px; margin-bottom: 12px;'>"
                        for stmt in statements[:10]:  # Limit to 10 statements
                            stmt_clean = stmt.strip()
                            if stmt_clean:
                                # Use a flex-like layout for proper number-text alignment
                                # Extract number and text separately for better alignment
                                number_match = re.match(r'^(\d+\.)\s*(.*)$', stmt_clean, re.DOTALL)
                                if number_match:
                                    number = number_match.group(1)
                                    text = number_match.group(2).strip()
                                    statements_html += f"<div style='display: flex; align-items: flex-start; margin-bottom: 6px; line-height: 1.6; padding: 4px 0;'>"
                                    statements_html += f"<span style='font-weight: bold; margin-right: 8px; min-width: 30px; flex-shrink: 0; color: #2c2c2c;'>{number}</span>"
                                    statements_html += f"<span style='flex: 1; color: #2c2c2c;'>{text}</span>"
                                    statements_html += "</div>"
                                else:
                                    # Fallback if pattern doesn't match
                                    statements_html += f"<div style='margin-bottom: 6px; line-height: 1.6; padding: 4px 0; color: #2c2c2c;'>{stmt_clean}</div>"
                        statements_html += "</div>"
                        
                        # Add the question part if present
                        if question_part:
                            statements_html += f"<div style='font-weight: bold; margin-top: 15px; padding-top: 15px; border-top: 2px solid rgba(212, 165, 116, 0.4); color: #8b6f47; font-size: 15px;'>{question_part}</div>"
                        
                        statements_html += "</div>"
                        
                        st.markdown(statements_html, unsafe_allow_html=True)
                    else:
                        # Fallback: format with better line breaks and alignment
                        # Extract intro
                        intro_match = re.search(r'(Consider the following.*?statements.*?:)', question_text, re.IGNORECASE | re.DOTALL)
                        intro_text = intro_match.group(1).strip() if intro_match else ""
                        
                        # Extract statements part
                        if intro_match:
                            statements_part = question_text[intro_match.end():].strip()
                            # Find question part
                            question_match = re.search(r'(Which of the following.*?statements.*?\?|Select.*?\?|Choose.*?\?)', statements_part, re.IGNORECASE)
                            if question_match:
                                statements_text = statements_part[:question_match.start()].strip()
                                question_part = question_match.group(1).strip()
                            else:
                                statements_text = statements_part
                                question_part = ""
                        else:
                            statements_text = question_text
                            question_part = ""
                        
                        # Extract numbered statements
                        statements = re.findall(r'(\d+\.\s*[^\n]+(?:\n(?!\d+\.)[^\n]+)*)', statements_text)
                        if not statements:
                            # Split by numbered items
                            parts = re.split(r'(\d+\.)', statements_text)
                            statements = []
                            current_stmt = ""
                            for part in parts:
                                if re.match(r'^\d+\.$', part.strip()):
                                    if current_stmt:
                                        statements.append(current_stmt.strip())
                                    current_stmt = part + " "
                                else:
                                    current_stmt += part
                            if current_stmt:
                                statements.append(current_stmt.strip())
                        
                        # Build formatted HTML
                        statements_html = "<div style='padding: 20px; background-color: rgba(255, 253, 250, 1); border-left: 4px solid #d4a574; border-radius: 5px; margin: 15px 0; line-height: 1.8;'>"
                        if intro_text:
                            statements_html += f"<div style='font-weight: bold; margin-bottom: 12px; color: #8b6f47; font-size: 16px;'>{intro_text}</div>"
                        
                        statements_html += "<div style='margin-left: 10px; margin-bottom: 12px;'>"
                        for stmt in statements[:10]:
                            stmt_clean = stmt.strip()
                            if stmt_clean:
                                number_match = re.match(r'^(\d+\.)\s*(.*)$', stmt_clean, re.DOTALL)
                                if number_match:
                                    number = number_match.group(1)
                                    text = number_match.group(2).strip()
                                    statements_html += f"<div style='display: flex; align-items: flex-start; margin-bottom: 6px; line-height: 1.6; padding: 4px 0;'>"
                                    statements_html += f"<span style='font-weight: bold; margin-right: 8px; min-width: 30px; flex-shrink: 0; color: #2c2c2c;'>{number}</span>"
                                    statements_html += f"<span style='flex: 1; color: #2c2c2c;'>{text}</span>"
                                    statements_html += "</div>"
                                else:
                                    statements_html += f"<div style='margin-bottom: 6px; line-height: 1.6; padding: 4px 0; color: #2c2c2c;'>{stmt_clean}</div>"
                        statements_html += "</div>"
                        
                        if question_part:
                            statements_html += f"<div style='font-weight: bold; margin-top: 12px; padding-top: 12px; border-top: 2px solid rgba(212, 165, 116, 0.4); color: #8b6f47; font-size: 15px;'>{question_part}</div>"
                        
                        statements_html += "</div>"
                        
                        st.markdown(statements_html, unsafe_allow_html=True)
                
                elif is_assertion_reason:
                    # Format Assertion-Reason: ensure they're on separate lines
                    question_text = re.sub(r'(Assertion\s*\(A\):)', r'\n\n**\1**', question_text, flags=re.IGNORECASE)
                    question_text = re.sub(r'(Reason\s*\(R\):)', r'\n\n**\1**', question_text, flags=re.IGNORECASE)
                    # Clean up extra newlines
                    question_text = re.sub(r'\n{3,}', '\n\n', question_text)
                    question_text = question_text.strip()
                    
                    # Display with styled container
                    st.markdown(f"""
                    <div style='
                        padding: 20px; 
                        background-color: rgba(255, 253, 250, 1); 
                        border-left: 4px solid #d4a574;
                        border-radius: 5px; 
                        margin: 15px 0;
                        line-height: 1.8;
                    '>
                        <div style='white-space: pre-wrap; color: #2c2c2c;'>{question_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                elif is_match_pair:
                    # Format Match-the-Pair: create table-like structure
                    # Pattern: List I + List II + Question statement
                    # Better regex to capture everything including the question
                    # Find List I and List II positions
                    list_i_match = re.search(r'List I\s*\n', question_text, re.IGNORECASE)
                    list_ii_match = re.search(r'List II\s*', question_text, re.IGNORECASE)
                    
                    if list_i_match and list_ii_match:
                        # Extract List I content (between List I and List II)
                        list_i_start = list_i_match.end()
                        list_i_end = list_ii_match.start()
                        list_i_content = question_text[list_i_start:list_i_end].strip()
                        
                        # Extract List II content (from List II until question starts)
                        # Find where List II content ends (look for question keywords)
                        list_ii_start = list_ii_match.end()
                        # Find question start (Select, Choose, Match, Which, etc.)
                        question_start_match = re.search(r'(Select|Choose|Match|Which)', question_text[list_ii_start:], re.IGNORECASE)
                        
                        if question_start_match:
                            # List II content ends where question starts
                            list_ii_end = list_ii_start + question_start_match.start()
                            list_ii_content = question_text[list_ii_start:list_ii_end].strip()
                            # Question statement starts from the keyword
                            question_statement = question_text[list_ii_start + question_start_match.start():].strip()
                        else:
                            # No question keyword found, take everything after List II
                            list_ii_content = question_text[list_ii_start:].strip()
                            question_statement = ""
                        
                        # Extract items from List I (numbered items)
                        list_i_items = re.findall(r'(\d+\.\s*[^\n]+(?:\n(?!\d+\.)[^\n]+)*)', list_i_content)
                        if not list_i_items:
                            # Fallback: split by numbered items
                            parts = re.split(r'(\d+\.)', list_i_content)
                            list_i_items = []
                            current_item = ""
                            for part in parts:
                                if re.match(r'^\d+\.$', part.strip()):
                                    if current_item:
                                        list_i_items.append(current_item.strip())
                                    current_item = part + " "
                                else:
                                    current_item += part
                            if current_item:
                                list_i_items.append(current_item.strip())
                        
                        # Extract items from List II (lettered items)
                        list_ii_pattern = r'\([a-d]\)\s*([^(]+?)(?=\s*\([a-d]\)|$)'
                        list_ii_matches = re.finditer(list_ii_pattern, list_ii_content, re.IGNORECASE)
                        
                        list_ii_items = []
                        for match in list_ii_matches:
                            full_match_text = match.group(0)  # Includes (a) prefix
                            list_ii_items.append(full_match_text.strip())
                        
                        if not list_ii_items:
                            # Fallback: try simpler pattern
                            list_ii_items = re.findall(r'\([a-d]\)\s*[^\n()]+', list_ii_content, re.IGNORECASE)
                            if not list_ii_items:
                                # Try splitting by newlines
                                list_ii_lines = [line.strip() for line in list_ii_content.split('\n') if line.strip()]
                                for line in list_ii_lines:
                                    matches = re.findall(r'\([a-d]\)\s*[^\n()]+', line, re.IGNORECASE)
                                    if matches:
                                        list_ii_items.extend(matches)
                                    elif line and not line.startswith('List'):
                                        list_ii_items.append(line)
                        
                        # Create table-like HTML structure (side by side)
                        match_table_html = "<div style='padding: 20px; background-color: rgba(255, 253, 250, 1); border-left: 4px solid #d4a574; border-radius: 5px; margin: 15px 0; line-height: 1.8;'>"
                        match_table_html += "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 15px;'>"
                        
                        # List I column
                        match_table_html += "<div><strong style='font-size: 16px; color: #8b6f47;'>List I</strong><br><br>"
                        for item in list_i_items:
                            item_clean = item.strip()
                            if item_clean:
                                match_table_html += f"<div style='padding: 10px 0; border-bottom: 1px solid rgba(212, 165, 116, 0.3); line-height: 1.6; color: #2c2c2c;'>{item_clean}</div>"
                        match_table_html += "</div>"
                        
                        # List II column
                        match_table_html += "<div><strong style='font-size: 16px; color: #8b6f47;'>List II</strong><br><br>"
                        for item in list_ii_items:
                            item_clean = item.strip()
                            if item_clean:
                                match_table_html += f"<div style='padding: 10px 0; border-bottom: 1px solid rgba(212, 165, 116, 0.3); line-height: 1.6; color: #2c2c2c;'>{item_clean}</div>"
                        match_table_html += "</div>"
                        
                        match_table_html += "</div>"
                        
                        # Add question statement prominently
                        if question_statement:
                            match_table_html += f"<div style='margin-top: 20px; font-weight: bold; padding-top: 15px; border-top: 2px solid rgba(212, 165, 116, 0.4); color: #8b6f47; font-size: 16px; line-height: 1.8;'>{question_statement}</div>"
                        else:
                            # Fallback: try to find question statement elsewhere
                            question_match = re.search(r'(Select.*?|Choose.*?|Match.*?|Which.*?)(?:\n|$)', question_text, re.IGNORECASE | re.MULTILINE)
                            if question_match:
                                match_table_html += f"<div style='margin-top: 20px; font-weight: bold; padding-top: 15px; border-top: 2px solid rgba(212, 165, 116, 0.4); color: #8b6f47; font-size: 16px; line-height: 1.8;'>{question_match.group(1).strip()}</div>"
                        
                        match_table_html += "</div>"
                        
                        st.markdown(match_table_html, unsafe_allow_html=True)
                    else:
                        # Fallback: format with better line breaks
                        question_text = re.sub(r'(List I)', r'\n\n**\1**\n', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'(List II)', r'\n\n**\1**\n', question_text, flags=re.IGNORECASE)
                        # Split List II items if they're on same line: (a) item (b) item -> separate lines
                        question_text = re.sub(r'(\([a-d]\)\s*[^\n()]+)\s*(?=\([a-d]\))', r'\1\n', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'\n{3,}', '\n\n', question_text)
                        question_text = question_text.strip()
                        
                        st.markdown(f"""
                        <div style='
                            padding: 20px; 
                            background-color: rgba(255, 253, 250, 1); 
                            border-left: 4px solid #d4a574;
                            border-radius: 5px; 
                            margin: 15px 0;
                            line-height: 1.8;
                        '>
                            <div style='white-space: pre-wrap; color: #2c2c2c;'>{question_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Regular question formatting
                    # Check if this is a multiple-choice question with numbered options (1., 2., 3., 4.)
                    numbered_options_pattern = r'(\d+\.\s*[^\n]+)'
                    numbered_options = re.findall(numbered_options_pattern, question_text)
                    
                    # If we have numbered options (typically 4 options), format them properly
                    if len(numbered_options) >= 2 and len(numbered_options) <= 6:
                        # Extract question part (everything before the first numbered option)
                        first_option_match = re.search(r'(\d+\.)', question_text)
                        if first_option_match:
                            question_part = question_text[:first_option_match.start()].strip()
                            options_part = question_text[first_option_match.start():].strip()
                            
                            # Extract numbered options
                            options = []
                            option_pattern = r'(\d+\.\s*[^\n]+(?:\n(?!\d+\.)[^\n]+)*)'
                            option_matches = re.finditer(option_pattern, options_part)
                            for match in option_matches:
                                opt = match.group(1).strip()
                                if opt:
                                    options.append(opt)
                            
                            # Build formatted HTML with proper alignment
                            regular_html = "<div style='padding: 20px; background-color: rgba(255, 253, 250, 1); border-left: 4px solid #d4a574; border-radius: 5px; margin: 15px 0; line-height: 1.8;'>"
                            
                            # Question text
                            if question_part:
                                regular_html += f"<div style='margin-bottom: 12px; color: #2c2c2c; font-size: 15px; line-height: 1.6;'>{question_part}</div>"
                            
                            # Options with proper alignment
                            regular_html += "<div style='margin-left: 10px;'>"
                            for opt in options:
                                opt_clean = opt.strip()
                                if opt_clean:
                                    # Extract number and text
                                    number_match = re.match(r'^(\d+\.)\s*(.*)$', opt_clean, re.DOTALL)
                                    if number_match:
                                        number = number_match.group(1)
                                        text = number_match.group(2).strip()
                                        regular_html += f"<div style='display: flex; align-items: flex-start; margin-bottom: 6px; line-height: 1.6; padding: 4px 0;'>"
                                        regular_html += f"<span style='font-weight: bold; margin-right: 8px; min-width: 30px; flex-shrink: 0; color: #2c2c2c;'>{number}</span>"
                                        regular_html += f"<span style='flex: 1; color: #2c2c2c;'>{text}</span>"
                                        regular_html += "</div>"
                                    else:
                                        regular_html += f"<div style='margin-bottom: 6px; line-height: 1.6; padding: 4px 0; color: #2c2c2c;'>{opt_clean}</div>"
                            regular_html += "</div>"
                            
                            # Check for "Select the correct answer" or similar instruction
                            instruction_match = re.search(r'(Select.*?answer.*?|Choose.*?answer.*?)', question_text, re.IGNORECASE)
                            if instruction_match:
                                instruction_text = instruction_match.group(1).strip()
                                regular_html += f"<div style='margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(212, 165, 116, 0.3); color: #8b6f47; font-weight: bold; font-size: 14px;'>{instruction_text}</div>"
                            
                            regular_html += "</div>"
                            
                            st.markdown(regular_html, unsafe_allow_html=True)
                        else:
                            # Fallback: regular formatting
                            question_text = re.sub(r'(Statement-I)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                            question_text = re.sub(r'(Statement-II)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                            question_text = re.sub(r'(Consider the following)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                            question_text = re.sub(r'\n{3,}', '\n\n', question_text)
                            question_text = question_text.strip()
                            
                            st.markdown(f"""
                            <div style='
                                padding: 20px; 
                                background-color: rgba(255, 253, 250, 1); 
                                border-left: 4px solid #d4a574;
                                border-radius: 5px; 
                                margin: 15px 0;
                                line-height: 1.8;
                            '>
                                <div style='white-space: pre-wrap; color: #2c2c2c;'>{question_text}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        # Not a numbered options format - use regular formatting
                        question_text = re.sub(r'(Statement-I)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'(Statement-II)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'(Consider the following)', r'\n**\1**', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'\n{3,}', '\n\n', question_text)
                        question_text = question_text.strip()
                        
                        st.markdown(f"""
                        <div style='
                            padding: 20px; 
                            background-color: rgba(255, 253, 250, 1); 
                            border-left: 4px solid #d4a574;
                            border-radius: 5px; 
                            margin: 15px 0;
                            line-height: 1.8;
                        '>
                            <div style='white-space: pre-wrap; color: #2c2c2c;'>{question_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Options displayed separately for better readability
                st.markdown("**Select your answer:**")
                
                # Calculate index for previously selected answer
                selected_index = None
                if i in st.session_state.user_answers:
                    selected_letter = st.session_state.user_answers[i]
                    letter_index = ord(selected_letter) - 65  # Convert A=0, B=1, C=2, D=3
                    if 0 <= letter_index < len(q["options"]):
                        selected_index = letter_index
                
                # Radio buttons - disabled if test is submitted
                answer = st.radio(
                    "Select your answer",
                    q["options"],
                    key=f"q_{i}",
                    index=selected_index,  # Show previously selected answer
                    disabled=st.session_state.test_submitted,  # Disable after submission
                    label_visibility="hidden"
                )
                
                # Store user answer if not submitted yet
                if answer is not None and not st.session_state.test_submitted:
                    answer_index = q["options"].index(answer)
                    option_letter = chr(65 + answer_index)  # A, B, C, D
                    st.session_state.user_answers[i] = option_letter
                    st.info(f"📌 **You selected: {option_letter}**")
                
                # Show correct/wrong immediately after submission (for all questions)
                if st.session_state.test_submitted:
                    correct_answer = q.get('correct_answer', '').upper()
                    user_answer = st.session_state.user_answers.get(i)
                    
                    if user_answer:
                        is_correct = user_answer == correct_answer
                        if is_correct:
                            st.success(f"✅ **Correct!** You selected **{user_answer}** and it's the right answer. (+2 marks)")
                        else:
                            st.error(f"❌ **Incorrect!** You selected **{user_answer}**, but the correct answer is **{correct_answer}**. (-0.67 marks)")
                    else:
                        st.warning(f"⚠️ **Not answered.** The correct answer is **{correct_answer}**. (0 marks)")
                
                # Toggle explanation button (only enabled after submission)
                explanation_key = f"explanation_{i}"
                explanation_disabled = not st.session_state.test_submitted
                
                # Only show explanation button after submission
                if st.session_state.test_submitted:
                    if st.button(
                        f"{'🔽 Hide' if explanation_key in st.session_state.show_explanations else '▶️ Show'} Explanation for Question {i}", 
                        key=f"btn_{i}",
                        use_container_width=False
                    ):
                        # Toggle explanation state
                        if explanation_key in st.session_state.show_explanations:
                            del st.session_state.show_explanations[explanation_key]
                        else:
                            st.session_state.show_explanations[explanation_key] = True
                        st.rerun()
                
                # Show explanation if toggled (only after submission)
                if explanation_key in st.session_state.show_explanations and st.session_state.test_submitted:
                    st.markdown("---")
                    st.markdown("#### 📖 Explanation")
                    
                    correct_answer = q.get('correct_answer', 'N/A')
                    user_answer = st.session_state.user_answers.get(i, None)
                    
                    # Show answer summary
                    if user_answer:
                        if user_answer == correct_answer.upper():
                            st.success(f"✅ **Correct Answer:** {correct_answer}")
                        else:
                            st.error(f"❌ **Correct Answer:** {correct_answer} (You selected: {user_answer})")
                    else:
                        st.info(f"📝 **Correct Answer:** {correct_answer} (You did not answer this question)")
                    
                    # Explanation - use Streamlit's native markdown for dark mode compatibility
                    explanation_text = q.get('explanation', 'No explanation provided')
                    st.markdown(f"**💡 Explanation:**")
                    st.markdown(explanation_text)
                    
                    # Show source information
                    source = q.get('source', {})
                    if source:
                        source_info = f"**Source:** File: `{source.get('filename', 'Unknown')}`"
                        if source.get('chapter') and source.get('chapter') != 'Unknown':
                            source_info += f", Chapter: `{source['chapter']}`"
                        if source.get('section') and source.get('section') != 'Unknown':
                            source_info += f", Section: `{source['section']}`"
                        if source.get('page_number'):
                            source_info += f", Page: `{source['page_number']}`"
                        st.markdown(source_info)
        
        # Submit Test button at the bottom (before score display)
        st.markdown("---")
        if not st.session_state.test_submitted:
            submit_col1, submit_col2, submit_col3 = st.columns([1, 2, 1])
            with submit_col2:
                if st.button("📝 Submit Test", type="primary", use_container_width=True):
                    # Calculate scores for all answered questions
                    for i, q in enumerate(data["questions"], 1):
                        user_answer = st.session_state.user_answers.get(i)
                        if user_answer:
                            correct_answer = q.get('correct_answer', '').upper()
                            if user_answer == correct_answer:
                                st.session_state.scores[i] = 2.0  # 2 marks for correct
                            else:
                                st.session_state.scores[i] = -0.67  # -1/3 of 2 marks for wrong
                        else:
                            st.session_state.scores[i] = 0  # Not answered
                    st.session_state.test_submitted = True
                    st.rerun()
        else:
            # Quick summary card after submission
            answered_count = len([a for a in st.session_state.user_answers.values() if a])
            correct_count = sum(1 for score in st.session_state.scores.values() if score > 0)
            wrong_count = sum(1 for score in st.session_state.scores.values() if score < 0)
            not_answered = len(data["questions"]) - answered_count
            
            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
            with summary_col1:
                st.metric("✅ Correct", correct_count)
            with summary_col2:
                st.metric("❌ Incorrect", wrong_count)
            with summary_col3:
                st.metric("⚠️ Not Answered", not_answered)
            with summary_col4:
                total_score = sum(st.session_state.scores.values())
                max_score = len(data["questions"]) * 2
                percentage = (total_score / max_score * 100) if max_score > 0 else 0
                st.metric("📊 Score", f"{percentage:.1f}%")
        
        # Calculate and display final score (only after submission)
        if st.session_state.test_submitted and st.session_state.scores:
            total_score = sum(st.session_state.scores.values())
            max_score = len(data["questions"]) * 2
            percentage = (total_score / max_score * 100) if max_score > 0 else 0
            
            st.markdown("---")
            st.markdown("## 📊 Final Score")
            
            final_col1, final_col2, final_col3 = st.columns(3)
            with final_col1:
                st.metric("Total Score", f"{total_score:.2f} / {max_score}")
            with final_col2:
                st.metric("Percentage", f"{percentage:.1f}%")
            with final_col3:
                correct_count = sum(1 for score in st.session_state.scores.values() if score > 0)
                wrong_count = sum(1 for score in st.session_state.scores.values() if score < 0)
                st.metric("Correct Answers", f"{correct_count} / {len(data['questions'])}")
            
            # Score breakdown
            st.markdown("### Score Breakdown:")
            for i, q in enumerate(data["questions"], 1):
                score = st.session_state.scores.get(i, 0)
                user_answer = st.session_state.user_answers.get(i, "Not answered")
                correct_answer = q.get('correct_answer', 'N/A')
                if score > 0:
                    status = "✅"
                    color = "green"
                elif score < 0:
                    status = "❌"
                    color = "red"
                else:
                    status = "⏸️"
                    color = "gray"
                st.markdown(f"<span style='color: {color};'>{status} Question {i}: {user_answer} (Correct: {correct_answer}) - Score: {score:+.2f}</span>", unsafe_allow_html=True)

elif tab_choice == "UPSC Mains Answer":
    st.header("📝 Generate UPSC Mains Answer")
    st.info("Get a comprehensive 500-word answer in UPSC Mains style with proper structure and analysis.")
    
    question = st.text_area(
        "Enter your Geography question for UPSC Mains:",
        placeholder="e.g., Discuss the impact of climate change on Indian agriculture and suggest adaptation strategies.",
        disabled=not backend_status,
        height=100
    )
    
    word_count = st.selectbox(
        "Target word count:",
        [150, 250, 350, 400, 500],
        index=1,
        disabled=not backend_status
    )
    

    if st.button("Generate Mains Answer", disabled=not backend_status):
        if question:
            with st.spinner("Generating UPSC Mains answer..."):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/mains-answer/generate",
                        json={
                            "question": question,
                            "word_count": word_count
                        },
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        st.subheader("📝 UPSC Mains Answer")
                        st.markdown("---")
                        
                        # Display the answer with proper formatting
                        st.markdown(data["answer"])
                        
                        # Show word count
                        word_count_actual = len(data["answer"].split())
                        st.info(f"📊 Word count: {word_count_actual} words")
                        
                        # Show sources
                        if data.get("sources"):
                            st.subheader("📚 Sources:")
                            for source in data["sources"]:
                                source_info = f"- **File:** `{source.get('filename', 'Unknown')}`"
                                if source.get('chapter') and source.get('chapter') != 'Unknown':
                                    source_info += f", **Chapter:** `{source['chapter']}`"
                                if source.get('section') and source.get('section') != 'Unknown':
                                    source_info += f", **Section:** `{source['section']}`"
                                st.markdown(source_info)
                    
                    else:
                        st.error("Failed to generate mains answer")
                
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Please try again.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            st.warning("Please enter a question")

elif tab_choice == "Evaluate Answer":
    st.header("📊 Evaluate Your Answer")
    st.info("Upload handwritten answer sheets or paste text to get UPSC-style evaluation with marks, feedback, and improvement suggestions.")
    
    # Initialize session state for sample sheet
    if "eval_sample_sheet_path" not in st.session_state:
        st.session_state.eval_sample_sheet_path = None
    
    # Sample Sheet Upload Section (moved from Upload PDFs)
    with st.container():
        st.subheader("📋 Sample Sheet (Optional)")
        st.caption("Upload a sample sheet (empty or with answers) to improve ROI detection accuracy. Format: WEBP, JPG, PNG, PDF")
        
        sample_sheet = st.file_uploader(
            "Upload sample sheet",
            type=["webp", "jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=False,
            disabled=not backend_status,
            key="eval_sample_sheet_uploader",
            help="Upload a sample answer sheet to help the system detect ROI boundaries more accurately"
        )
        
        if sample_sheet:
            st.info(f"📄 Selected: {sample_sheet.name}")
        
        if sample_sheet and st.button("📤 Upload Sample Sheet", disabled=not backend_status, type="primary", key="eval_upload_sample"):
            with st.spinner("Uploading sample sheet..."):
                try:
                    files = {"sample_sheet": sample_sheet}
                    response = requests.post(f"{BACKEND_URL}/upload/sample-sheet", files=files)
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.eval_sample_sheet_path = data.get("path")
                        st.session_state.eval_sample_sheet_preview_url = data.get("preview_url")
                        st.session_state.eval_sample_sheet_roi_preview_url = data.get("roi_preview_url")
                        st.success(f"✅ Sample sheet uploaded: {data.get('filename')}")
                        st.rerun()  # Refresh to show previews
                    else:
                        st.error("Failed to upload sample sheet")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Show sample sheet status and previews
    if st.session_state.eval_sample_sheet_path:
        st.success(f"✅ Sample sheet ready: {st.session_state.eval_sample_sheet_path}")
        
        # Initialize preview state
        if "eval_show_sample_previews" not in st.session_state:
            st.session_state.eval_show_sample_previews = False
        
        # Preview toggle button
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("👁️ Show/Hide Previews", key="eval_toggle_sample_previews"):
                st.session_state.eval_show_sample_previews = not st.session_state.eval_show_sample_previews
                st.rerun()
        
        with col_btn2:
            if st.button("🗑️ Remove Sample Sheet", key="eval_remove_sample"):
                st.session_state.eval_sample_sheet_path = None
                st.session_state.eval_show_sample_previews = False
                if hasattr(st.session_state, 'eval_sample_sheet_preview_url'):
                    delattr(st.session_state, 'eval_sample_sheet_preview_url')
                if hasattr(st.session_state, 'eval_sample_sheet_roi_preview_url'):
                    delattr(st.session_state, 'eval_sample_sheet_roi_preview_url')
                st.rerun()
        
        # Show previews if toggled on
        if st.session_state.eval_show_sample_previews:
            col_preview1, col_preview2 = st.columns(2)
            with col_preview1:
                st.markdown("**📄 Original Sample Sheet:**")
                if hasattr(st.session_state, 'eval_sample_sheet_preview_url'):
                    preview_url = f"{BACKEND_URL}{st.session_state.eval_sample_sheet_preview_url}"
                    try:
                        st.image(preview_url, caption="Original Sample Sheet")
                    except Exception as e:
                        st.error(f"Failed to load preview: {e}")
                        st.text(f"URL: {preview_url}")
                else:
                    st.warning("Preview URL not available")
            
            with col_preview2:
                st.markdown("**✂️ ROI Detection Preview:**")
                if hasattr(st.session_state, 'eval_sample_sheet_roi_preview_url'):
                    roi_preview_url = f"{BACKEND_URL}{st.session_state.eval_sample_sheet_roi_preview_url}"
                    try:
                        st.image(roi_preview_url, caption="Detected ROI")
                    except Exception as e:
                        st.error(f"Failed to load ROI preview: {e}")
                        st.text(f"URL: {roi_preview_url}")
                else:
                    st.warning("ROI Preview URL not available")
    
    st.divider()
    
    # Answer Input Section
    st.subheader("📝 Enter Question and Answer")
    
    # Question is optional when uploading files (will be identified from OCR), required when pasting text
    question_label = "Enter the question you answered (optional if uploading files - will be identified from OCR):"
    question_placeholder = "e.g., Discuss the impact of climate change on Indian agriculture... (Optional if uploading handwritten files)"
    
    question = st.text_area(
        question_label,
        placeholder=question_placeholder,
        disabled=not backend_status,
        height=100,
        key="eval_question"
    )
    
    # Answer input method selection
    answer_input_method = st.radio(
        "Answer input method:",
        ["Upload File (Handwritten)", "Paste Text"],
        disabled=not backend_status,
        key="answer_input_method"
    )
    
    # File upload for handwritten answers (multiple files supported)
    uploaded_files = None
    dpi = None
    if answer_input_method == "Upload File (Handwritten)":
        uploaded_files = st.file_uploader(
            "Upload your handwritten answer (PDF or images) - Multiple files supported:",
            type=["pdf", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            disabled=not backend_status,
            key="eval_handwritten_uploader",
            help="You can upload multiple images or PDFs. All pages will be processed together."
        )
        
        # Show uploaded files count
        if uploaded_files:
            st.info(f"📎 {len(uploaded_files)} file(s) selected: {', '.join([f.name for f in uploaded_files])}")
        
        # DPI selection for handwritten
        if uploaded_files:
            dpi = st.selectbox(
                "DPI for PDF conversion:",
                [300, 600],
                index=1,
                disabled=not backend_status,
                key="eval_dpi"
            )
    
    # Alternative: Direct text input
    answer_text = None
    if answer_input_method == "Paste Text":
        answer_text = st.text_area(
            "Paste your answer directly here:",
            placeholder="Paste your written answer here...",
            disabled=not backend_status,
            height=200,
            key="eval_answer_text"
        )
    
    if st.button("Evaluate Answer", disabled=not backend_status, type="primary"):
        # Validation: 
        # - If uploading files: question is optional (will be identified from OCR blocks)
        # - If pasting text: both question and answer_text are required
        if uploaded_files or (question and answer_text):
            with st.spinner("Processing and evaluating your answer..."):
                try:
                    response = None
                    
                    # Handle handwritten file upload (PDF/images) - ROI -> OCR -> LLM -> Evaluate
                    if uploaded_files and answer_input_method == "Upload File (Handwritten)":
                        # Process handwritten answer: upload -> ROI -> OCR -> LLM -> download PDF -> evaluate
                        status_container = st.container()
                        with status_container:
                            st.info(f"🔄 Processing {len(uploaded_files)} file(s): ROI detection → OCR → LLM reconstruction...")
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            # Step 1: Upload and process handwritten answer(s)
                            status_text.text(f"📤 Uploading {len(uploaded_files)} file(s)...")
                            progress_bar.progress(10)
                            
                            # Prepare multiple files for upload
                            files = [("files", f) for f in uploaded_files]
                            upload_data = {
                                "dpi": dpi
                            }
                            if st.session_state.eval_sample_sheet_path:
                                upload_data["sample_sheet_path"] = st.session_state.eval_sample_sheet_path
                            
                            # Upload and process (ROI -> OCR -> LLM -> PDF generation)
                            upload_response = requests.post(
                                f"{BACKEND_URL}/upload/",
                                files=files,
                                data=upload_data,
                                timeout=600  # Longer timeout for multiple files
                            )
                            
                            if upload_response.status_code == 200:
                                upload_results = upload_response.json()["summary"]
                                
                                # Extract OCR data and reconstructed text from OCR results
                                # Combine results from all uploaded files
                                ocr_data_for_eval = None
                                reconstructed_answer = ""
                                identified_question = ""
                                pdf_download_urls = []
                                
                                # Combine OCR results from all files
                                all_ocr_results = []
                                for file_result in upload_results:
                                    file_ocr_results = file_result.get("ocr_results", [])
                                    all_ocr_results.extend(file_ocr_results)
                                    pdf_url = file_result.get("pdf_download_url")
                                    if pdf_url:
                                        pdf_download_urls.append(pdf_url)
                                
                                if all_ocr_results:
                                    # Combine OCR blocks from all pages and all files for evaluation
                                    combined_blocks = []
                                    combined_full_texts = []
                                    total_width = 0
                                    total_height = 0
                                    
                                    for r in all_ocr_results:
                                        blocks = r.get("blocks", [])
                                        full_text = r.get("full_text", "")
                                        width = r.get("width", 0)
                                        height = r.get("height", 0)
                                        
                                        combined_blocks.extend(blocks)
                                        if full_text:
                                            combined_full_texts.append(full_text)
                                        total_width = max(total_width, width)
                                        total_height += height
                                    
                                    combined_full_text = "\n\n".join(combined_full_texts) if combined_full_texts else ""
                                    
                                    # Prepare OCR data for evaluation (all 3 tasks)
                                    ocr_data_for_eval = {
                                        "blocks": combined_blocks,
                                        "full_text": combined_full_text,
                                        "width": total_width,
                                        "height": total_height
                                    }
                                    
                                    # Also extract reconstructed text for display
                                    reconstructed_answer = "\n\n".join([
                                        r.get("reconstructed_text", "") or r.get("text", "")
                                        for r in all_ocr_results
                                    ])
                                    
                                    # Extract identified question if available (from first result)
                                    identified_question = all_ocr_results[0].get("identified_question", "")
                                
                                status_text.text(f"✅ OCR and reconstruction complete! Processed {len(all_ocr_results)} page(s) from {len(upload_results)} file(s)")
                                progress_bar.progress(50)
                                
                                # Show download links for PDFs (one per file)
                                if pdf_download_urls:
                                    if len(pdf_download_urls) == 1:
                                        st.success(f"📥 [Download Reconstructed PDF]({BACKEND_URL}{pdf_download_urls[0]})")
                                    else:
                                        st.success(f"📥 Download reconstructed PDFs ({len(pdf_download_urls)} files):")
                                        for i, pdf_url in enumerate(pdf_download_urls, 1):
                                            filename = upload_results[i-1].get("pdf_filename", f"file_{i}.pdf")
                                            st.markdown(f"   • [{filename}]({BACKEND_URL}{pdf_url})")
                                
                                # Step 2: Reconstruct + Evaluate using OCR blocks (ONE LLM CALL - all 3 tasks)
                                status_text.text("📊 Reconstructing and evaluating answer (ONE LLM call: identify question + reconstruct + evaluate)...")
                                progress_bar.progress(70)
                                
                                import json
                                
                                # Use OCR blocks for reconstruction + evaluation (ONE LLM call)
                                # This does: Identify question + Reconstruct answer + Evaluate (all in one call)
                                if ocr_data_for_eval:
                                    eval_data = {
                                        "ocr_data_json": json.dumps(ocr_data_for_eval)
                                    }
                                    # Question is optional hint (LLM will identify from OCR blocks anyway)
                                    if question:
                                        eval_data["question"] = question
                                    
                                    response = requests.post(
                                        f"{BACKEND_URL}/evaluate-answer/",
                                        data=eval_data,
                                        timeout=120
                                    )
                                else:
                                    st.error("No OCR data available for evaluation")
                                    response = None
                                
                                progress_bar.progress(100)
                                status_text.text("✅ Evaluation complete!")
                            else:
                                st.error("Failed to process handwritten answer")
                                
                    elif answer_text:
                        # Direct text evaluation (legacy mode - no OCR)
                        eval_data = {
                            "question": question,
                            "answer_text": answer_text
                        }
                        response = requests.post(
                            f"{BACKEND_URL}/evaluate-answer/",
                            data=eval_data,  # Use data for Form data
                            timeout=60
                        )
                    else:
                        st.warning("Please provide either a file upload or paste your answer text")
                    
                    if response and response.status_code == 200:
                        data = response.json()
                        
                        # Display evaluation results
                        st.subheader("📊 Evaluation Results")
                        st.markdown("---")
                        
                        # Show question
                        identified_q = data.get("question", question)
                        st.info(f"📋 **Question:** {identified_q}")
                        
                        # Show reconstructed answer
                        if data.get("reconstructed_answer"):
                            with st.expander("📝 View Reconstructed Answer", expanded=False):
                                st.markdown(data["reconstructed_answer"])
                        
                        # Overall score
                        score = data.get("score", 0)
                        max_score = data.get("max_score", 20)
                        percentage = (score / max_score) * 100 if max_score > 0 else 0
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Score", f"{score}/{max_score}")
                        with col2:
                            st.metric("Percentage", f"{percentage:.1f}%")
                        with col3:
                            grade = "A+" if percentage >= 90 else "A" if percentage >= 80 else "B+" if percentage >= 70 else "B" if percentage >= 60 else "C"
                            st.metric("Grade", grade)
                        
                        # Detailed feedback
                        st.subheader("📝 Detailed Feedback")
                        
                        # Strengths (What was done well)
                        if data.get("strengths"):
                            st.success("✅ **What Was Done Well:**")
                            for strength in data["strengths"]:
                                st.markdown(f"- {strength}")
                        
                        # Areas for improvement (What was missing)
                        if data.get("improvements"):
                            st.warning("⚠️ **What Was Missing / Can Be Improved:**")
                            for improvement in data["improvements"]:
                                st.markdown(f"- {improvement}")
                        
                        # Specific suggestions (High return improvements)
                        if data.get("suggestions"):
                            st.info("💡 **High Return Improvements:**")
                            for suggestion in data["suggestions"]:
                                st.markdown(f"- {suggestion}")
                        
                        # Evaluation details (structured data)
                        eval_details = data.get("evaluation_details")
                        if eval_details:
                            with st.expander("📊 View Structured Evaluation Details", expanded=False):
                                st.json(eval_details)
                    
                    else:
                        st.error("Failed to evaluate answer")
                
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Please try again.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            if not uploaded_files and not answer_text:
                st.warning("Please provide either a file upload or paste your answer text")
            elif answer_text and not question:
                st.warning("Please provide both a question and an answer to evaluate")
            else:
                st.warning("Please provide either a file upload or paste your answer text")

# Footer
st.markdown("---")
st.markdown("Made with ❤️ by Study Buddy AI")