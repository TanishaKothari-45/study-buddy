"""
LangSmith configuration for tracing and monitoring LLM calls.

Setup:
1. Create account at https://smith.langchain.com
2. Generate API key from Settings → API Keys
3. Add to .env:
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=your-api-key
   LANGCHAIN_PROJECT=study-buddy
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# LangSmith environment variable names
LANGCHAIN_TRACING_V2 = "LANGCHAIN_TRACING_V2"
LANGCHAIN_API_KEY = "LANGCHAIN_API_KEY"
LANGCHAIN_PROJECT = "LANGCHAIN_PROJECT"
LANGCHAIN_ENDPOINT = "LANGCHAIN_ENDPOINT"


def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    tracing_enabled = os.getenv(LANGCHAIN_TRACING_V2, "false").lower() == "true"
    api_key_set = bool(os.getenv(LANGCHAIN_API_KEY))
    return tracing_enabled and api_key_set


def get_langsmith_project() -> str:
    """Get the LangSmith project name."""
    return os.getenv(LANGCHAIN_PROJECT, "study-buddy")


def configure_langsmith():
    """
    Configure LangSmith environment variables.
    Call this at application startup.
    """
    # Set default endpoint if not set
    if not os.getenv(LANGCHAIN_ENDPOINT):
        os.environ[LANGCHAIN_ENDPOINT] = "https://api.smith.langchain.com"
    
    # Log status
    if is_langsmith_enabled():
        project = get_langsmith_project()
        logger.info(f"✅ LangSmith tracing enabled for project: {project}")
    else:
        logger.info("ℹ️ LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY to enable)")


def get_langsmith_client():
    """
    Get LangSmith client for manual tracing operations.
    Returns None if LangSmith is not configured.
    """
    if not is_langsmith_enabled():
        return None
    
    try:
        from langsmith import Client
        return Client()
    except ImportError:
        logger.warning("⚠️ langsmith package not installed")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Failed to create LangSmith client: {e}")
        return None
