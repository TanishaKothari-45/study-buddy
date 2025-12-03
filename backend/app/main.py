"""
Main FastAPI application
"""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .core.env import load_env_vars

# Load environment variables at startup
load_env_vars()

from .core.config import settings
from .core.database import engine, Base
from .api.v1 import router as api_v1_router
from .utils.memory_manager import init_memory_db

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create database tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    # Initialize memory database
    init_memory_db()
    
    # Clean up stale jobs (jobs stuck in "processing" from previous server run)
    from .utils.job_tracker import get_job_store
    job_store = get_job_store()
    job_store.cleanup_stale_jobs()
    
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

# Attach limiter state to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup centralized error handling
from .middleware import setup_exception_handlers
setup_exception_handlers(app)

# Enable CORS (restricted to localhost for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include versioned API router
app.include_router(api_v1_router, prefix="/api/v1")

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Study Buddy AI backend is running"
    }

@app.get("/api/cache/stats")
async def cache_stats():
    """Get cache statistics (for monitoring)"""
    from .utils.cache_manager import get_cache_manager
    cache = get_cache_manager()
    return cache.get_cache_stats()