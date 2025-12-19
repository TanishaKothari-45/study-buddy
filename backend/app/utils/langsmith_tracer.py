"""
LangSmith tracing utilities for Study Buddy.

Provides decorators and context managers for tracing LLM calls
from both OpenAI and Gemini APIs.

Usage:
    from app.utils.langsmith_tracer import trace_llm, trace_gemini, traced_operation

    # For OpenAI calls (automatic via LangChain callbacks)
    @trace_llm("mock_test_generation")
    def generate_questions(...):
        ...

    # For Gemini calls (manual spans)
    @trace_gemini("mains_answer_generation")
    async def generate_answer(...):
        ...

    # For any operation (creates a parent span)
    with traced_operation("full_answer_pipeline"):
        ...
"""
import os
import time
import functools
import logging
import asyncio
from typing import Optional, Callable, Any, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Check if LangSmith is available
try:
    from langsmith import traceable as langsmith_traceable
    # Try to import Client to verify full installation
    from langsmith import Client 
    LANGSMITH_AVAILABLE = True
    logger.info("✅ LangSmith package found")
except ImportError as e:
    LANGSMITH_AVAILABLE = False
    langsmith_traceable = None
    logger.warning(f"ℹ️ langsmith package not fully installed or import failed: {e}")

def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled by environment variable."""
    if not LANGSMITH_AVAILABLE:
        return False
    enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    # Also check for LANGCHAIN_API_KEY
    has_api_key = bool(os.getenv("LANGCHAIN_API_KEY"))
    return enabled and has_api_key


def trace_llm(name: str, run_type: str = "llm", metadata: Optional[Dict] = None):
    """Decorator to trace OpenAI/LangChain LLM calls."""
    def decorator(func: Callable) -> Callable:
        if not LANGSMITH_AVAILABLE:
            return func
        
        logger.debug(f"🔗 Wrapping {func.__name__} with LLM trace: {name}")
        return langsmith_traceable(
            name=name,
            run_type=run_type,
            metadata=metadata or {}
        )(func)
    
    return decorator


def trace_gemini(name: str, metadata: Optional[Dict] = None):
    """Decorator to trace Gemini API calls (manual spans)."""
    def decorator(func: Callable) -> Callable:
        if not LANGSMITH_AVAILABLE:
            return func
        
        logger.debug(f"🔗 Wrapping {func.__name__} with Gemini trace: {name}")
        return langsmith_traceable(
            name=name,
            run_type="llm",
            metadata={
                "provider": "google-gemini",
                **(metadata or {})
            }
        )(func)
    
    return decorator


def trace_chain(name: str, metadata: Optional[Dict] = None):
    """Decorator to trace a chain of operations (parent span)."""
    def decorator(func: Callable) -> Callable:
        if not LANGSMITH_AVAILABLE:
            return func
        
        logger.debug(f"🔗 Wrapping {func.__name__} with Chain trace: {name}")
        return langsmith_traceable(
            name=name,
            run_type="chain",
            metadata=metadata or {}
        )(func)
    
    return decorator


def trace_retriever(name: str, metadata: Optional[Dict] = None):
    """Decorator to trace retrieval operations."""
    def decorator(func: Callable) -> Callable:
        if not LANGSMITH_AVAILABLE:
            return func
        
        logger.debug(f"🔗 Wrapping {func.__name__} with Retriever trace: {name}")
        return langsmith_traceable(
            name=name,
            run_type="retriever",
            metadata=metadata or {}
        )(func)
    
    return decorator


@contextmanager
def traced_operation(name: str, metadata: Optional[Dict] = None):
    """
    Context manager for tracing a block of code.
    
    Usage:
        with traced_operation("full_pipeline", {"question": question}):
            context = retrieve_context(question)
            answer = generate_answer(question, context)
    """
    if not is_tracing_enabled():
        yield
        return
    
    start_time = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.debug(f"⏱️ {name} completed in {elapsed:.2f}s")


def asyncio_iscoroutinefunction(func: Callable) -> bool:
    """Check if a function is an async coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(func)


# Convenience exports
__all__ = [
    "trace_llm",
    "trace_gemini", 
    "trace_chain",
    "trace_retriever",
    "traced_operation",
    "is_tracing_enabled",
]
