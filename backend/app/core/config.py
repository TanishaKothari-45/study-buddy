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