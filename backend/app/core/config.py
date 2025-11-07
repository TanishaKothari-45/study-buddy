"""
Application configuration
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from .env import load_env_vars

# Load environment variables first
load_env_vars()

class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "Study Buddy AI"
    OPENAI_API_KEY: str = None  # Will be loaded from environment

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env that aren't in the model
    
    # Directory Settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    DB_DIR: Path = BASE_DIR / "data" / "chroma"
    
    # PDF Settings
    CHUNK_SIZE: int = 300  # words
    CHUNK_OVERLAP: int = 50  # words
    
    # Vector Store Settings
    COLLECTION_NAME: str = "geography_docs_enriched"  # Default to enriched collection
    DISTANCE_METRIC: str = "cosine"
    
    # OpenAI Settings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Model Selection Strategy: Use mini for 90% of tasks, large only for final question generation
    LLM_MODEL_SMALL: str = "gpt-4o-mini"  # For most tasks (embeddings, chunking, evaluation, etc.)
    LLM_MODEL_LARGE: str = "gpt-4o"  # For final test/question generation only
    
    # Legacy: defaults to small model for backward compatibility
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