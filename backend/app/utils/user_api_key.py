"""
User API Key Utilities

Helper functions to retrieve and use user-specific API keys.
"""
from typing import Optional
import logging
from ..models.user import User
from ..core.encryption import get_api_key_encryptor
from ..gemini_core import settings_gemini_key

logger = logging.getLogger(__name__)

def get_user_gemini_api_key(user: Optional[User]) -> Optional[str]:
    """
    Get user's decrypted Gemini API key, or None if not set
    
    Args:
        user: Current user object (can be None for public endpoints)
    
    Returns:
        Decrypted Gemini API key or None
    """
    if not user:
        return None
    
    if not user.encrypted_gemini_api_key:
        return None
    
    try:
        encryptor = get_api_key_encryptor()
        return encryptor.decrypt_api_key(user.encrypted_gemini_api_key)
    except Exception as e:
        logger.error(f"Failed to decrypt API key for user {user.email}: {e}")
        return None

def get_gemini_api_key_for_request(user: Optional[User]) -> str:
    """
    Get Gemini API key for a request:
    1. First try user's personal API key (if set)
    2. Fallback to system default API key
    
    Args:
        user: Current user object (can be None for public endpoints)
    
    Returns:
        Gemini API key to use (user's or system default)
    
    Raises:
        ValueError: If no API key is available
    """
    # Try user's personal API key first
    user_api_key = get_user_gemini_api_key(user)
    if user_api_key:
        logger.info(f"Using user {user.email}'s personal Gemini API key")
        return user_api_key
    
    # No personal API key available
    raise ValueError("Missing Gemini API key. Please add your personal API key in Settings to use this feature.")
