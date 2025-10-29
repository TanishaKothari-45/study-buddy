"""
Main FastAPI application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .core.env import load_env_vars

# Load environment variables at startup
load_env_vars()

from .core.config import settings
from .routes import upload, query
from .routes import mock_test
from .utils.chroma_handler import ChromaHandler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    # Initialize ChromaDB handler
    app.state.chroma_handler = ChromaHandler()
    yield
    # Clean up on shutdown
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
app.include_router(query.router, prefix="/query", tags=["Query"])
app.include_router(mock_test.router, prefix="/mock-test", tags=["Mock Test"])

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Study Buddy AI backend is running"
    }