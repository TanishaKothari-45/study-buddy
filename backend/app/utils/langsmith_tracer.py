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
from typing import Optional, Callable, Any, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Check if LangSmith is available
try:
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree, traceable as traceable_sync
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    traceable = None
    logger.info("ℹ️ langsmith not installed, tracing disabled")


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    if not LANGSMITH_AVAILABLE:
        return False
    return os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"


def trace_llm(name: str, run_type: str = "llm", metadata: Optional[Dict] = None):
    """
    Decorator to trace OpenAI/LangChain LLM calls.
    
    Args:
        name: Name for this trace (e.g., "mock_test_generation")
        run_type: Type of run ("llm", "chain", "tool", "retriever")
        metadata: Optional metadata to attach to the trace
    
    Example:
        @trace_llm("question_generation", metadata={"difficulty": "medium"})
        def generate_questions(num: int):
            ...
    """
    def decorator(func: Callable) -> Callable:
        if not is_tracing_enabled():
            return func
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Use LangSmith's traceable decorator
            traced_func = traceable(
                name=name,
                run_type=run_type,
                metadata=metadata or {}
            )(func)
            return traced_func(*args, **kwargs)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            traced_func = traceable(
                name=name,
                run_type=run_type,
                metadata=metadata or {}
            )(func)
            return await traced_func(*args, **kwargs)
        
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


def trace_gemini(name: str, metadata: Optional[Dict] = None):
    """
    Decorator to trace Gemini API calls.
    
    Since Gemini doesn't have native LangSmith integration,
    this creates manual spans with input/output capture.
    
    Args:
        name: Name for this trace (e.g., "mains_answer_generation")
        metadata: Optional metadata to attach
    
    Example:
        @trace_gemini("answer_generation")
        async def generate_answer(question: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        if not is_tracing_enabled():
            return func
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Create traceable wrapper
            traced_func = traceable(
                name=name,
                run_type="llm",
                metadata={
                    "provider": "google-gemini",
                    **(metadata or {})
                }
            )(func)
            
            try:
                result = await traced_func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"❌ Gemini call failed in {name}: {e}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            
            traced_func = traceable(
                name=name,
                run_type="llm",
                metadata={
                    "provider": "google-gemini",
                    **(metadata or {})
                }
            )(func)
            
            try:
                result = traced_func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"❌ Gemini call failed in {name}: {e}")
                raise
        
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def trace_chain(name: str, metadata: Optional[Dict] = None):
    """
    Decorator to trace a chain of operations (parent span).
    
    Use this for endpoint handlers that orchestrate multiple LLM calls.
    
    Args:
        name: Name for this trace (e.g., "mains_answer_endpoint")
        metadata: Optional metadata to attach
    
    Example:
        @trace_chain("evaluate_answer_endpoint")
        async def evaluate_answer(request):
            # This creates a parent span that groups:
            # - OCR extraction
            # - Context retrieval
            # - Answer evaluation
            ...
    """
    def decorator(func: Callable) -> Callable:
        if not is_tracing_enabled():
            return func
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            traced_func = traceable(
                name=name,
                run_type="chain",
                metadata=metadata or {}
            )(func)
            return await traced_func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            traced_func = traceable(
                name=name,
                run_type="chain",
                metadata=metadata or {}
            )(func)
            return traced_func(*args, **kwargs)
        
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def trace_retriever(name: str, metadata: Optional[Dict] = None):
    """
    Decorator to trace retrieval operations (Pinecone queries, etc.).
    
    Args:
        name: Name for this trace (e.g., "pinecone_search")
        metadata: Optional metadata
    """
    def decorator(func: Callable) -> Callable:
        if not is_tracing_enabled():
            return func
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            traced_func = traceable(
                name=name,
                run_type="retriever",
                metadata=metadata or {}
            )(func)
            return await traced_func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            traced_func = traceable(
                name=name,
                run_type="retriever",
                metadata=metadata or {}
            )(func)
            return traced_func(*args, **kwargs)
        
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
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
