"""
Main FastAPI application
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .core.env import load_env_vars

# Load environment variables at startup
load_env_vars()

from .core.config import settings
from .routes import upload, query, mock_test, mains_answer, evaluate_answer, upload_content_store, feedback, training_data
from .utils.memory_manager import init_memory_db

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    # Initialize memory database
    init_memory_db()
    
    # Initialize vector store handler (Pinecone or ChromaDB based on config)
    if settings.USE_PINECONE:
        from .utils.pinecone_handler import PineconeHandler
        app.state.vector_handler = PineconeHandler()
        logger.info("✅ Using Pinecone as vector store")
    else:
        from .utils.chroma_handler import ChromaHandler
        app.state.vector_handler = ChromaHandler()
        logger.info("✅ Using ChromaDB as vector store")
    
    # Keep backward compatibility
    app.state.chroma_handler = app.state.vector_handler
    
    yield
    # Clean up on shutdown
    app.state.vector_handler = None
    app.state.chroma_handler = None

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI-based RAG application for Geography PDFs",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(upload_content_store.router, prefix="/upload-content-store", tags=["Content Store Upload"])
app.include_router(query.router, prefix="/query", tags=["Query"])
app.include_router(mock_test.router, prefix="/mock-test", tags=["Mock Test"])
app.include_router(mains_answer.router, prefix="/mains-answer", tags=["Mains Answer"])
app.include_router(evaluate_answer.router, prefix="/evaluate-answer", tags=["Answer Evaluation"])
app.include_router(training_data.router, prefix="/training-data", tags=["Training Data"])
app.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Study Buddy AI backend is running"
    }