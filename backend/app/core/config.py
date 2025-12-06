"""
Application configuration with environment variable validation
"""
from pydantic_settings import BaseSettings
from pydantic import Field, validator, ValidationError
from pathlib import Path
from typing import Optional
import secrets
import sys
from .env import load_env_vars

# Load environment variables first
load_env_vars()

class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "Study Buddy AI"
    
    # Required API Keys (will fail if not set)
    OPENAI_API_KEY: str = Field(..., min_length=20)
    GEMINI_API_KEY: str = Field(..., min_length=20)
    PINECONE_API_KEY: str = Field(..., min_length=20)
    
    # JWT Authentication Settings (CRITICAL: Must be set in production)
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 2880  # 2 days (48 hours)
    
    # API Key Encryption (for user-specific Gemini keys)
    ENCRYPTION_KEY: Optional[str] = Field(None, min_length=32)
    
    @validator('JWT_SECRET_KEY')
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters for security")
        # Warn if using a weak/default secret
        if v in ["your-secret-key-here", "changeme", "secret"]:
            print("⚠️  WARNING: Using a weak JWT_SECRET_KEY. Generate a secure one!")
        return v
    
    # Optional API Keys
    GNEWS_API_KEY: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None
    THENEWSAPI_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
    # Directory Settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    DB_DIR: Path = BASE_DIR / "data" / "databases"
    
    # PDF Chunking Settings
    CHUNK_SIZE_WORDS: int = 500  # Standard chunk size in words
    CHUNK_OVERLAP_PERCENT: float = 0.15  # 15% overlap between chunks
    MIN_WORDS_PER_CHUNK: int = 20  # Minimum words to consider a chunk valid
    
    # Semantic Chunking Settings (fallback)
    USE_SEMANTIC_FALLBACK: bool = True  # Enable semantic chunking fallback
    SEMANTIC_THRESHOLD: float = 0.80  # Similarity threshold for semantic splitting
    EMBED_BATCH_SIZE: int = 200  # Words per embedding window for semantic fallback
    
    # Vector Store Settings
    COLLECTION_NAME: str = "geography_docs_enriched"  # Default to enriched collection (ChromaDB)
    DISTANCE_METRIC: str = "cosine"
    
    # Pinecone Settings
    PINECONE_INDEX_NAME: str = "study-buddy"  # Pinecone index name (from env or default)
    USE_PINECONE: bool = True  # Set to True to use Pinecone, False to use ChromaDB
    
    # OpenAI Settings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Model Selection Strategy: Use mini for 90% of tasks, large only for final question generation
    # OpenAI Models
    LLM_MODEL_SMALL: str = "gpt-4o-mini"  # For most tasks (embeddings, chunking, query, etc.)
    LLM_MODEL_LARGE: str = "gpt-4o"  # For final test/question generation only
    
    # Gemini Models
    GEMINI_MODEL_PRO: str = "gemini-2.5-pro"  # For mains answer & evaluation (superior reasoning)
    GEMINI_MODEL_FLASH: str = "gemini-2.0-flash-exp"  # For speed-critical tasks (if needed)
    
    # Default LLM (for backward compatibility)
    LLM_MODEL: str = "gpt-4o-mini"
    
    # Fallback Model
    FALLBACK_MODEL: str = "all-MiniLM-L6-v2"
    
    # RAG Settings
    TOP_K_CHUNKS: int = 8  # Increased to get more context
    
    def setup_directories(self):
        """Create necessary directories"""
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.DB_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.setup_directories()