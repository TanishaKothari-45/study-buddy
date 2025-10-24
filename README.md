# Study Buddy AI - Geography Q&A Bot

A FastAPI-based RAG (Retrieval-Augmented Generation) application for answering questions about Geography using your study materials.

## Features

- Upload multiple PDFs (NCERTs, Vision IAS notes, PYQs)
- Automatic text extraction and chunking
- Vector embeddings using OpenAI or sentence-transformers
- Local vector storage with ChromaDB
- Question answering using GPT-4 with RAG

## Project Structure

```
backend/
├── app/
│   ├── core/
│   │   └── config.py         # Configuration settings
│   ├── routes/
│   │   ├── upload.py         # PDF upload endpoint
│   │   └── query.py          # Q&A endpoint
│   ├── utils/
│   │   ├── pdf_reader.py     # PDF processing
│   │   ├── embedder.py       # Text embeddings
│   │   └── chroma_handler.py # Vector store
│   └── main.py              # FastAPI application
├── uploads/                 # PDF storage
└── data/
    └── chroma/             # ChromaDB files
```

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   .\venv\Scripts\activate  # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file:
   ```env
   OPENAI_API_KEY=your_api_key_here
   ```

## Running the Application

1. Start the FastAPI server:
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```

2. The API will be available at:
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs

## API Endpoints

### Upload PDFs
```http
POST /api/v1/documents/upload/
```
- Upload multiple PDF files
- Returns summary of processed files and chunks

### Query
```http
POST /api/v1/qa/query/
```
- Ask questions about the uploaded content
- Returns answer with source information

## Example Usage

1. Upload PDFs:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/documents/upload/" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "files=@NCERT_Geography_Class11.pdf" \
     -F "files=@Vision_IAS_Geography.pdf"
   ```

2. Ask questions:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/qa/query/" \
     -H "accept: application/json" \
     -H "Content-Type: application/json" \
     -d '{"question": "What are the major types of plate boundaries?"}'
   ```

## Configuration

Key settings in `config.py`:
- `CHUNK_SIZE`: 300 words
- `CHUNK_OVERLAP`: 50 words
- `TOP_K_CHUNKS`: 5 chunks for context
- `EMBEDDING_MODEL`: OpenAI's text-embedding-3-small
- `FALLBACK_EMBEDDING_MODEL`: sentence-transformers' all-MiniLM-L6-v2
- `LLM_MODEL`: GPT-4 Turbo preview