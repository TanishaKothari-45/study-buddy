"""
Main FastAPI application
"""
import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables at startup (only for local development)
# Cloud Run provides env vars via Secret Manager, so skip .env loading there
if not os.getenv("K_SERVICE"):
    from .core.env import load_env_vars
    load_env_vars()

# Configure LangSmith tracing (must be before other imports)
from .core.langsmith_config import configure_langsmith
configure_langsmith()

from .core.config import settings
from .core.database import init_db
from .api.v1 import router as api_v1_router
from .utils.memory_manager import init_memory_db

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create database tables (with error handling for concurrent workers)
init_db()

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
    
    # Initialize Arq Redis pool
    from arq import create_pool
    from arq.connections import RedisSettings

    try:
        # Use Redis URL from settings (supports both local and Cloud Run)
        redis_host = settings.redis_host
        redis_port = settings.redis_port_from_url
        app.state.arq_pool = await create_pool(
            RedisSettings(host=redis_host, port=redis_port)
        )
        logger.info(f"✅ Arq Redis pool initialized: {redis_host}:{redis_port}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize Arq pool: {e}")
        app.state.arq_pool = None

    yield
    # Clean up on shutdown
    if hasattr(app.state, "arq_pool") and app.state.arq_pool:
        await app.state.arq_pool.close()

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

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local development
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Production frontend
        "https://study-buddy-upsc-coach.vercel.app",
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