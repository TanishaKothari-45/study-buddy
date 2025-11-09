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
    st.info("💡 Upload PDF or image files (JPG, PNG, WEBP). Handwritten content will be processed with ROI detection and OCR. Upload a sample sheet first for better ROI detection accuracy.")
    
    # Initialize session state
    if "processed_files" not in st.session_state:
        st.session_state.processed_files = set()
    if "sample_sheet_path" not in st.session_state:
        st.session_state.sample_sheet_path = None
    
    # Sample Sheet Upload Section
    with st.container():
        st.subheader("📋 Sample Sheet (Optional)")
        st.caption("Upload a sample sheet (empty or with answers) to improve ROI detection accuracy. Format: WEBP, JPG, PNG, PDF")
        
        sample_sheet = st.file_uploader(
            "Upload sample sheet",
            type=["webp", "jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=False,
            disabled=not backend_status,
            key="sample_sheet_uploader",
            help="Upload a sample answer sheet to help the system detect ROI boundaries more accurately"
        )
        
        if sample_sheet:
            st.info(f"📄 Selected: {sample_sheet.name}")
        
        if sample_sheet and st.button("📤 Upload Sample Sheet", disabled=not backend_status, type="primary"):
            with st.spinner("Uploading sample sheet..."):
                try:
                    files = {"sample_sheet": sample_sheet}
                    response = requests.post(f"{BACKEND_URL}/upload/sample-sheet", files=files)
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.sample_sheet_path = data.get("path")
                        st.session_state.sample_sheet_preview_url = data.get("preview_url")
                        st.session_state.sample_sheet_roi_preview_url = data.get("roi_preview_url")
                        st.success(f"✅ Sample sheet uploaded: {data.get('filename')}")
                        st.rerun()  # Refresh to show previews
                    else:
                        st.error("Failed to upload sample sheet")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Show sample sheet status and previews
    if st.session_state.sample_sheet_path:
        st.success(f"✅ Sample sheet ready: {st.session_state.sample_sheet_path}")
        
        # Initialize preview state
        if "show_sample_previews" not in st.session_state:
            st.session_state.show_sample_previews = True
        
        # Preview toggle button
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("👁️ Show/Hide Previews", key="toggle_sample_previews"):
                st.session_state.show_sample_previews = not st.session_state.show_sample_previews
                st.rerun()
        
        with col_btn2:
            if st.button("🗑️ Remove Sample Sheet"):
                st.session_state.sample_sheet_path = None
                st.session_state.show_sample_previews = False
                if hasattr(st.session_state, 'sample_sheet_preview_url'):
                    delattr(st.session_state, 'sample_sheet_preview_url')
                if hasattr(st.session_state, 'sample_sheet_roi_preview_url'):
                    delattr(st.session_state, 'sample_sheet_roi_preview_url')
                st.rerun()
        
        # Show previews if toggled on
        if st.session_state.show_sample_previews:
            col_preview1, col_preview2 = st.columns(2)
            with col_preview1:
                st.markdown("**📄 Original Sample Sheet:**")
                if hasattr(st.session_state, 'sample_sheet_preview_url'):
                    preview_url = f"{BACKEND_URL}{st.session_state.sample_sheet_preview_url}"
                    try:
                        st.image(preview_url, caption="Original Sample Sheet")
                    except Exception as e:
                        st.error(f"Failed to load preview: {e}")
                        st.text(f"URL: {preview_url}")
                else:
                    st.warning("Preview URL not available")
            
            with col_preview2:
                st.markdown("**✂️ ROI Detection Preview:**")
                if hasattr(st.session_state, 'sample_sheet_roi_preview_url'):
                    roi_preview_url = f"{BACKEND_URL}{st.session_state.sample_sheet_roi_preview_url}"
                    try:
                        st.image(roi_preview_url, caption="Detected ROI (Preprocessed)")
                    except Exception as e:
                        st.error(f"Failed to load ROI preview: {e}")
                        st.text(f"URL: {roi_preview_url}")
                else:
                    st.warning("ROI Preview URL not available")
    
    st.divider()
    
    # Main File Upload Section
    st.subheader("📄 Upload Documents")
    
    # DPI Selection
    dpi = st.selectbox(
        "DPI for PDF conversion (higher = better quality, slower processing):",
        [300, 600],
        index=1,  # Default to 600
        disabled=not backend_status,
        help="600 DPI provides better clarity for handwritten text but takes longer to process"
    )
    
    uploaded_files = st.file_uploader(
        "Upload your PDFs or images (JPG, PNG, WEBP)",
        type=["pdf", "jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        disabled=not backend_status,
        key="file_uploader"
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
    if "last_roi_previews" not in st.session_state:
        st.session_state.last_roi_previews = {}
    
    # Process Files button with state
    process_button_label = "⏳ Processing..." if st.session_state.processing_files else "🚀 Process Files"
    
    if uploaded_files and st.button(process_button_label, disabled=(not backend_status or st.session_state.processing_files), type="primary"):
        # Set processing state
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
            st.info(f"🔄 Processing {file_type_summary} file(s) at {dpi} DPI...")
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        with st.spinner(f"Processing {file_type_summary} file(s) at {dpi} DPI..."):
            files = [("files", file) for file in uploaded_files]
            data = {
                "dpi": dpi
            }
            if st.session_state.sample_sheet_path:
                data["sample_sheet_path"] = st.session_state.sample_sheet_path
            
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
            min_value=1,
            max_value=20,
            value=5,
            disabled=not backend_status
        )
        
        difficulty = st.select_slider(
            "Difficulty level:",
            options=["easy", "medium", "hard"],
            value="medium",
            disabled=not backend_status
        )
    
    with col2:
        # Topic selection with both dropdown and text input
        st.markdown("**Select topics (optional):**")
        topic_options = [
            "Monsoon", "Climate", "Physical Geography",
            "Indian Geography", "World Geography",
            "Geomorphology", "Oceanography", "Climatology",
            "Agriculture", "Economic Geography", "Cultural Geography",
            "Natural Disasters", "Biogeography", "Oceanography"
        ]
        
        selected_topics = st.multiselect(
            "Choose from list:",
            topic_options,
            disabled=not backend_status,
            label_visibility="collapsed"
        )
        
        # Allow typing custom topics
        custom_topic = st.text_input(
            "Or type a custom topic:",
            placeholder="e.g., Cyclones, Monsoon Variability, etc.",
            disabled=not backend_status,
            key="custom_topic_input"
        )
        
        # Combine selected and custom topics
        topics = selected_topics.copy()
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
            st.rerun()

    # Generate test if button clicked
    if generate_clicked:
        with st.spinner("Generating mock test..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/mock-test/generate",
                    json={
                        "num_questions": num_questions,
                        "topics": topics,
                        "difficulty": difficulty
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.mock_test_data = data
                    st.session_state.show_explanations = {}  # Reset explanations
                    st.session_state.user_answers = {}  # Reset answers
                    st.session_state.scores = {}  # Reset scores
                    st.session_state.test_submitted = False  # Reset submission state
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
        
        # Progress indicator at top
        if not st.session_state.test_submitted:
            answered_count = len(st.session_state.user_answers)
            total_questions = len(data["questions"])
            progress = answered_count / total_questions if total_questions > 0 else 0
            st.progress(progress, text=f"📊 Progress: {answered_count} / {total_questions} questions answered")
        
        # Show questions
        for i, q in enumerate(data["questions"], 1):
            st.markdown("---")
            
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
                # Format question text - split statements and question on different lines
                question_text = q['question']
                # Replace common statement patterns with line breaks
                question_text = question_text.replace('\\n', '\n')  # Handle escaped newlines
                # Add line breaks before statements if they start with numbers
                # Split on numbered statements (1., 2., Statement-I, Statement-II, etc.)
                question_text = re.sub(r'(\d+\.)', r'\n\1', question_text)
                question_text = re.sub(r'(Statement-I)', r'\n\1', question_text)
                question_text = re.sub(r'(Statement-II)', r'\n\1', question_text)
                question_text = re.sub(r'(Consider the following)', r'\n\1', question_text)
                # Clean up multiple newlines
                question_text = re.sub(r'\n{3,}', '\n\n', question_text)
                question_text = question_text.strip()
                
                # Convert to HTML with line breaks
                question_html = question_text.replace('\n', '<br>')
                st.markdown(f"<div style='padding: 15px; background-color: #f0f2f6; border-radius: 5px; margin-bottom: 15px;'><p style='font-size: 16px; line-height: 1.8; color: #1f1f1f;'>{question_html}</p></div>", unsafe_allow_html=True)
            
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
                
                # Explanation with dark mode compatible text color
                explanation_text = q.get('explanation', 'No explanation provided')
                st.markdown(f"<div style='padding: 15px; background-color: #f0f2f6; border-radius: 5px; margin: 10px 0;'><p style='color: #1f1f1f; line-height: 1.8; font-size: 15px;'><strong>💡 Explanation:</strong><br>{explanation_text}</p></div>", unsafe_allow_html=True)
                
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
    st.info("Upload your written answer to get UPSC-style evaluation with marks, feedback, and improvement suggestions.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        question = st.text_area(
            "Enter the question you answered:",
            placeholder="e.g., Discuss the impact of climate change on Indian agriculture...",
            disabled=not backend_status,
            height=100
        )
    
    with col2:
        uploaded_file = st.file_uploader(
            "Upload your answer (PDF or text file):",
            type=["pdf", "txt"],
            disabled=not backend_status
        )
    
    # Alternative: Direct text input
    answer_text = st.text_area(
        "Or paste your answer directly here:",
        placeholder="Paste your written answer here...",
        disabled=not backend_status,
        height=200
    )
    
    if st.button("Evaluate Answer", disabled=not backend_status):
        if question and (uploaded_file or answer_text):
            with st.spinner("Evaluating your answer..."):
                try:
                    # Prepare evaluation request
                    if uploaded_file:
                        # Use regular text file processing (PDF or TXT only)
                        eval_data = {
                            "question": question,
                            "answer_text": answer_text if answer_text else None
                        }
                        files = {"answer_file": uploaded_file}
                        response = requests.post(
                            f"{BACKEND_URL}/evaluate-answer/",
                            json=eval_data,
                            files=files,
                            timeout=60
                        )
                    else:
                        # Direct text evaluation
                        eval_data = {
                            "question": question,
                            "answer_text": answer_text
                        }
                        response = requests.post(
                            f"{BACKEND_URL}/evaluate-answer/",
                            json=eval_data,
                            timeout=60
                        )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Display evaluation results
                        st.subheader("📊 Evaluation Results")
                        st.markdown("---")
                        
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
                        
                        # Strengths
                        if data.get("strengths"):
                            st.success("✅ **Strengths:**")
                            for strength in data["strengths"]:
                                st.markdown(f"- {strength}")
                        
                        # Areas for improvement
                        if data.get("improvements"):
                            st.warning("⚠️ **Areas for Improvement:**")
                            for improvement in data["improvements"]:
                                st.markdown(f"- {improvement}")
                        
                        # Specific suggestions
                        if data.get("suggestions"):
                            st.info("💡 **Specific Suggestions:**")
                            for suggestion in data["suggestions"]:
                                st.markdown(f"- {suggestion}")
                        
                        # Model answer excerpt
                        if data.get("model_answer_excerpt"):
                            st.subheader("📚 Model Answer Excerpt")
                            st.markdown(data["model_answer_excerpt"])
                    
                    else:
                        st.error("Failed to evaluate answer")
                
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Please try again.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        else:
            st.warning("Please provide both a question and an answer to evaluate")

# Footer
st.markdown("---")
st.markdown("Made with ❤️ by Study Buddy AI")