"""
Supabase Client for Backend

Provides a singleton Supabase client for database operations.
Uses the service role key for server-side operations.
"""

from supabase import create_client, Client
from typing import Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)

# Singleton Supabase client
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or create a Supabase client instance.
    
    Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for server-side operations.
    The service role key bypasses Row Level Security (RLS) for admin operations.
    
    Returns:
        Supabase client instance
    """
    global _supabase_client
    
    if _supabase_client is None:
        if not settings.SUPABASE_URL:
            raise ValueError("SUPABASE_URL is not configured")
        if not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured")
        
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        logger.info("✅ Supabase client initialized")
    
    return _supabase_client


def get_supabase_anon_client() -> Client:
    """
    Get a Supabase client with anon key (respects RLS).
    
    Use this for operations that should respect Row Level Security policies.
    
    Returns:
        Supabase client instance with anon key
    """
    if not settings.SUPABASE_URL:
        raise ValueError("SUPABASE_URL is not configured")
    if not settings.SUPABASE_ANON_KEY:
        raise ValueError("SUPABASE_ANON_KEY is not configured")
    
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY
    )
