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
        ["Upload PDFs", "Ask Questions", "Generate Mock Test"]
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

else:  # Mock Test tab
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

# Footer
st.markdown("---")
st.markdown("Made with ❤️ by Study Buddy AI")