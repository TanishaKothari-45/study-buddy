import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(layout="wide", page_title="Study Buddy AI - Geography Q&A Bot")

# Backend URL (ensure this matches your FastAPI server's address)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

def check_backend_status():
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, {"error": f"Backend returned status code: {response.status_code}"}
    except requests.exceptions.ConnectionError as e:
        return False, {"error": f"Connection error: {e}"}
    except requests.exceptions.Timeout as e:
        return False, {"error": f"Timeout error: {e}"}
    except Exception as e:
        return False, {"error": f"Unexpected error: {e}"}

# Check backend status and get model info
backend_status, backend_info = check_backend_status()

st.title("📚 Study Buddy AI - Geography Q&A Bot")
st.markdown("Your personal AI assistant for UPSC Geography preparation.")

# Show backend status prominently
if not backend_status:
    st.error("⚠️ Backend server is not running. Please start the backend server first!")
    st.code("cd backend && python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001", language="bash")

# --- Tabs ---
tab_upload, tab_query = st.tabs(["⬆️ Upload Materials", "❓ Ask Questions"])

with tab_upload:
    st.header("Upload Your Geography Study Materials")
    st.markdown("Upload multiple PDF files (NCERTs, Vision IAS notes, PYQs, etc.) related to Geography. "
                "The AI will process them to answer your questions.")

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type="pdf",
        accept_multiple_files=True,
        help="Select one or more PDF files to upload.",
        disabled=not backend_status
    )

    if uploaded_files:
        # Show uploaded files before processing
        st.subheader(f"📄 Ready to Process ({len(uploaded_files)} files)")

        # Calculate total size
        total_size = sum(len(file.getvalue()) for file in uploaded_files)
        total_size_mb = total_size / (1024 * 1024)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Files Selected", len(uploaded_files))
        with col2:
            st.metric("Total Size", f"{total_size_mb:.1f} MB")
        with col3:
            estimated_time = max(2, int(total_size_mb * 0.5))  # Rough estimate: 30s per MB
            st.metric("Est. Time", f"{estimated_time} min")

        # Show file list with details
        st.markdown("**Files to process:**")
        for i, file in enumerate(uploaded_files, 1):
            file_size_mb = len(file.getvalue()) / (1024 * 1024)
            st.write(f"{i}. 📄 **{file.name}** ({file_size_mb:.1f} MB)")

        if st.button("🚀 Process and Store PDFs", disabled=not backend_status):
            # Show processing status
            status_container = st.container()
            with status_container:
                st.info("📊 Processing files... This may take several minutes for large files.")
                st.info("🔄 The AI is extracting text, creating chunks, and generating embeddings...")

            try:
                files = [("files", (file.name, file.getvalue(), "application/pdf")) for file in uploaded_files]
                response = requests.post(f"{BACKEND_URL}/upload/", files=files, timeout=900)  # 15 min timeout for large files

                if response.status_code == 200:
                    result = response.json()

                    # Clear the progress info
                    status_container.empty()

                    # Show success message with file count
                    st.success(f"✅ All {len(uploaded_files)} PDFs processed successfully!")

                    # Show detailed results
                    summary = result.get("summary", [])

                    if summary:
                        st.subheader("📋 Processing Results")

                        # Create columns for better layout
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Files Processed", len([s for s in summary if s.get("status") == "success"]))
                        with col2:
                            total_chunks = sum(s.get("chunks_added", 0) for s in summary if s.get("status") == "success")
                            st.metric("Total Chunks", total_chunks)
                        with col3:
                            failed_files = len([s for s in summary if s.get("status") == "failed"])
                            st.metric("Failed Files", failed_files)

                        # Show detailed breakdown
                        st.subheader("📁 File-by-File Results")

                        for file_info in summary:
                            filename = file_info.get("filename", "Unknown")
                            status = file_info.get("status", "unknown")
                            chunks = file_info.get("chunks_added", 0)

                            if status == "success":
                                st.success(f"✅ **{filename}**\n📊 {chunks} chunks extracted and embedded")
                            else:
                                reason = file_info.get("reason", "Unknown error")
                                st.error(f"❌ **{filename}**\n⚠️ Error: {reason}")

                        # Show total summary
                        st.info(f"🎯 **Summary**: Successfully processed {len([s for s in summary if s.get('status') == 'success'])} out of {len(summary)} files, creating {total_chunks} searchable chunks from your Geography materials!")

                    else:
                        st.warning("No file processing details available.")

                else:
                    status_container.empty()
                    st.error(f"❌ Upload failed with status {response.status_code}")
                    st.text(response.text)

            except requests.exceptions.ConnectionError:
                status_container.empty()
                st.error("❌ Could not connect to the backend server. Please ensure the backend is running.")
            except requests.exceptions.Timeout:
                status_container.empty()
                st.error("⏰ Request timed out. Large PDF files can take 10-15 minutes to process.")
            except Exception as e:
                status_container.empty()
                st.error(f"❌ Unexpected error: {e}")
    else:
        st.info("📂 No files selected. Please upload PDFs to get started.")

with tab_query:
    st.header("Ask Questions about Your Study Materials")
    st.markdown("Enter your questions below, and the AI will provide answers based on the uploaded PDFs and its general knowledge.")

    question = st.text_area(
        "Your Question:",
        placeholder="e.g., What are the main types of landforms in geomorphology?",
        height=100,
        disabled=not backend_status
    )

    if st.button("Get Answer", disabled=not backend_status):
        if question:
            with st.spinner("Fetching answer..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/query/", json={"question": question}, timeout=120)  # 2 min timeout
                    if response.status_code == 200:
                        answer_data = response.json()
                        answer = answer_data.get("answer", "No answer found.")
                        
                        # Store the answer in session state
                        st.session_state.last_answer = answer
                        
                        st.subheader("Answer:")
                        
                        # Show model info
                        if "OpenAI unavailable" in answer or "OpenAI API error" in answer:
                            st.warning("⚠️ Using Sentence Transformers (direct context from materials)")
                        else:
                            st.success("✨ Using OpenAI to generate answer")
                        
                        st.write(answer)
                        if answer_data.get("sources"):
                            st.subheader("Sources:")
                            for source in answer_data["sources"]:
                                st.markdown(f"- **File:** `{source['filename']}`, **Page:** `{source['page_number']}`")
                    else:
                        st.error(f"Failed to get answer: {response.status_code} - {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error("Could not connect to the backend server. Please ensure the backend is running.")
                except requests.exceptions.Timeout:
                    st.error("The request timed out. The server might be busy.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
        else:
            st.warning("Please enter a question.")

st.sidebar.header("About Study Buddy AI")
st.sidebar.info(
    "This is an AI-powered Q&A bot designed to help you with UPSC Geography preparation. "
    "Upload your study materials, and ask questions to get instant, relevant answers."
)

# Initialize session state for storing last answer
if 'last_answer' not in st.session_state:
    st.session_state.last_answer = None

# Show backend status in sidebar
if backend_status:
    st.sidebar.success("✅ Backend server is running")
    
    # Check if we're using OpenAI or sentence-transformers based on last answer
    if st.session_state.last_answer and ("OpenAI unavailable" in st.session_state.last_answer or "OpenAI API error" in st.session_state.last_answer):
        st.sidebar.warning("🤖 Using Sentence Transformers (Fallback Mode)")
        st.sidebar.info("OpenAI API is not available. Using direct context from your materials.")
    else:
        st.sidebar.success("🤖 Using OpenAI GPT Model")
        st.sidebar.info("Answers are generated using OpenAI with context from your materials.")
    
    # Show total chunks
    st.sidebar.info("📚 Using chunks from your uploaded Geography materials")
else:
    st.sidebar.error("❌ Backend server is not running")

# Show API details
st.sidebar.markdown("---")
st.sidebar.markdown("### Technical Details")
st.sidebar.markdown(f"**Backend URL:** `{BACKEND_URL}`")
if isinstance(backend_info, dict):
    for key, value in backend_info.items():
        st.sidebar.markdown(f"**{key}:** {value}")