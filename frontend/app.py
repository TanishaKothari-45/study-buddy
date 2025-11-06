"""
Streamlit frontend for Study Buddy AI
"""
import streamlit as st
import requests
import time
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

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
    
    uploaded_files = st.file_uploader(
        "Upload your Geography PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        disabled=not backend_status
    )

    if uploaded_files and st.button("Process Files", disabled=not backend_status):
        with st.spinner("Processing PDFs..."):
            files = [("files", file) for file in uploaded_files]
            try:
                response = requests.post(f"{BACKEND_URL}/upload/", files=files)
                if response.status_code == 200:
                    results = response.json()["summary"]
                    st.success("✅ Files processed successfully!")
                    
                    # Show processing results
                    for result in results:
                        if result["status"] == "success":
                            st.info(f"📄 {result['filename']}: Added {result['chunks_added']} chunks")
                        else:
                            st.error(f"❌ {result['filename']}: {result['reason']}")
                else:
                    st.error("Failed to process files")
            except Exception as e:
                st.error(f"Error: {str(e)}")

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
        topics = st.multiselect(
            "Select topics (optional):",
            [
                "Monsoon", "Climate", "Physical Geography",
                "Indian Geography", "World Geography",
                "Geomorphology", "Oceanography"
            ],
            disabled=not backend_status
        )

    if st.button("Generate Test", disabled=not backend_status):
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
                    
                    # Show test instructions
                    st.info("📋 Test Instructions:")
                    for instruction in data["instructions"]:
                        st.markdown(f"- {instruction}")
                    
                    st.info(f"⏱️ Time allowed: {data['time_allowed']}")
                    st.info(f"📊 Total marks: {data['total_marks']}")
                    
                    # Show questions
                    for i, q in enumerate(data["questions"], 1):
                        st.markdown("---")
                        st.subheader(f"Question {i}:")
                        st.write(q["question"])
                        
                        # Options with radio buttons
                        answer = st.radio(
                            "Select your answer:",
                            q["options"],
                            key=f"q_{i}"
                        )
                        
                        # Show/Hide explanation button
                        if st.button(f"Show Explanation {i}"):
                            st.success(f"✅ Correct answer: {q['correct_answer']}")
                            st.markdown(f"**Explanation:** {q['explanation']}")
                            source_info = f"**Source:** File: `{q['source'].get('filename', 'Unknown')}`"
                            if q['source'].get('chapter') and q['source'].get('chapter') != 'Unknown':
                                source_info += f", Chapter: `{q['source']['chapter']}`"
                            if q['source'].get('section') and q['source'].get('section') != 'Unknown':
                                source_info += f", Section: `{q['source']['section']}`"
                            if q['source'].get('page_number'):
                                source_info += f", Page: `{q['source']['page_number']}`"
                            st.markdown(source_info)
                
                else:
                    st.error("Failed to generate mock test")
            
            except requests.exceptions.Timeout:
                st.error("Request timed out. Please try again.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

elif tab_choice == "UPSC Mains Answer":
    st.header("📝 Generate UPSC Mains Answer")
    st.info("Get a comprehensive 500-word answer in UPSC Mains style with proper structure and analysis.")
    
    question = st.text_area(
        "Enter your Geography question for UPSC Mains:",
        placeholder="e.g., Discuss the impact of climate change on Indian agriculture and suggest adaptation strategies.",
        disabled=not backend_status,
        height=100
    )
    
    col1, col2 = st.columns(2)
    with col1:
        word_count = st.selectbox(
            "Target word count:",
            [400, 500, 600, 700],
            index=1,
            disabled=not backend_status
        )
    
    with col2:
        include_diagrams = st.checkbox(
            "Include diagram suggestions",
            value=True,
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
                            "word_count": word_count,
                            "include_diagrams": include_diagrams
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
                        
                        # Show diagram suggestions if requested
                        if data.get("diagram_suggestions"):
                            st.subheader("📐 Diagram Suggestions:")
                            for diagram in data["diagram_suggestions"]:
                                st.markdown(f"- {diagram}")
                    
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
    
    # Add info about handwritten answer support
    st.success("✨ **New Feature**: Upload handwritten answers! The system now supports OCR processing of handwritten text using DeepSeek-OCR for accurate text extraction and evaluation.")
    
    # OCR Preview section
    st.subheader("🔍 OCR Preview (Optional)")
    st.info("Upload an image/PDF to preview what text will be extracted before evaluation.")
    
    preview_file = st.file_uploader(
        "Upload image/PDF for OCR preview:",
        type=["png", "jpg", "jpeg", "pdf"],
        key="preview_upload",
        disabled=not backend_status
    )
    
    if preview_file and st.button("Preview OCR Extraction", disabled=not backend_status):
        with st.spinner("Processing image with OCR..."):
            try:
                files = {"answer_file": preview_file}
                response = requests.post(
                    f"{BACKEND_URL}/evaluate-answer/preview-ocr/",
                    files=files,
                    timeout=120
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data["success"]:
                        st.success("✅ OCR extraction successful!")
                        
                        # Show preprocessing info
                        if data.get("preprocessing_info"):
                            with st.expander("🔧 OCR Processing Details"):
                                info = data["preprocessing_info"]
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    if info.get("image_size"):
                                        st.metric("Image Size", f"{info['image_size']}")
                                    if info.get("avg_confidence"):
                                        st.metric("Avg Confidence", f"{info['avg_confidence']:.2%}")
                                with col2:
                                    st.metric("Word Count", f"{info.get('word_count', 0)}")
                                    st.metric("Confidence Level", data["confidence"].title())
                                with col3:
                                    if info.get("detections"):
                                        st.metric("Text Detections", f"{info['detections']}")
                                    if info.get("confidences") and len(info["confidences"]) > 1:
                                        st.metric("Pages Processed", f"{len(info['confidences'])}")
                        
                        # Show extracted text prominently
                        st.subheader("📝 Extracted Text (via EasyOCR):")
                        st.info("💡 **Review the extracted text below to verify OCR accuracy before evaluation.**")
                        
                        # Make the text area editable so users can correct OCR mistakes
                        extracted_text_display = st.text_area(
                            "OCR Result (you can edit if needed):",
                            value=data["extracted_text"],
                            height=400,
                            key="extracted_text_display",
                            help="Review and edit the extracted text if the OCR made any mistakes"
                        )
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.info(f"📊 **Word count:** {data['word_count']} words")
                        with col2:
                            st.info(f"🎯 **Confidence:** {data['confidence'].title()}")
                        
                        # Update session state with potentially edited text
                        if st.button("✅ Use This Text for Evaluation", key="use_previewed_text"):
                            st.session_state.previewed_text = extracted_text_display
                            st.success("✅ Text saved! You can now use it in the evaluation form below.")
                            st.rerun()
                    else:
                        st.error(f"❌ OCR extraction failed: {data.get('error', 'Unknown error')}")
                else:
                    st.error("Failed to process OCR preview")
            except requests.exceptions.Timeout:
                st.error("OCR processing timed out. Please try again.")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Show previewed text in the main form if available
    if hasattr(st.session_state, 'previewed_text'):
        st.info("📋 **Previewed text available below**")
        st.text_area(
            "Previewed OCR Text:",
            value=st.session_state.previewed_text,
            height=200,
            disabled=True
        )
        if st.button("Clear Previewed Text"):
            del st.session_state.previewed_text
            st.rerun()
    
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
            "Upload your answer (PDF, image, or text file):",
            type=["pdf", "txt", "png", "jpg", "jpeg"],
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
                    # Determine which endpoint to use based on file type
                    if uploaded_file:
                        # Check if it's an image or PDF (handwritten)
                        file_extension = uploaded_file.filename.split('.')[-1].lower()
                        if file_extension in ['png', 'jpg', 'jpeg', 'pdf']:
                            # Use handwritten OCR endpoint
                            files = {"answer_file": uploaded_file}
                            data = {"question": question}
                            response = requests.post(
                                f"{BACKEND_URL}/evaluate-answer/upload-handwritten/",
                                data=data,
                                files=files,
                                timeout=120  # Longer timeout for OCR processing
                            )
                        else:
                            # Use regular text file processing
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