"""
ChromaDB settings configuration
"""
from chromadb.config import Settings

def get_chroma_settings():
    """
    Return ChromaDB settings with telemetry disabled
    """
    return Settings(
        anonymized_telemetry=False,
        allow_reset=True,
        is_persistent=True
    )
