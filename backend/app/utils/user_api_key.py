"""
User API Key Utilities

Helper functions to retrieve and use user-specific API keys.
Uses Supabase user_profiles for storage.
"""
from typing import Optional
import logging
from ..core.user_profile import UserProfile
from ..core.encryption import get_api_key_encryptor

logger = logging.getLogger(__name__)


def get_user_gemini_api_key(user: Optional[UserProfile]) -> Optional[str]:
    """
    Get user's decrypted Gemini API key, or None if not set
    
    Args:
        user: Current user profile (can be None for public endpoints)

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


def get_gemini_api_key_for_request(user: Optional[UserProfile], direct_key: Optional[str] = None) -> str:
    """
    Get Gemini API key for a request:
    1. First try direct key from X-Gemini-API-Key header (no-auth mode)
    2. Then try user's personal API key (if logged in)
    
    Args:
        user: Current user profile (can be None for public endpoints)
        direct_key: Raw API key passed directly via X-Gemini-API-Key header

    Returns:
        Gemini API key to use

    Raises:
        ValueError: If no API key is available
    """
    # TODO: REVERT FOR PROD (optional) — Priority 1 (X-Gemini-API-Key header) was added for no-auth India mode.
    # In production with auth enabled, this header will still work fine alongside Supabase keys.
    # Only remove it if you want to strictly enforce Supabase-stored keys with no header fallback.
    # Priority 1: Direct key from header (no-auth India mode)
    if direct_key and direct_key.strip():
        logger.info("Using API key from X-Gemini-API-Key header (no-auth mode)")
        return direct_key.strip()


    # Priority 2: User's personal stored API key
    user_api_key = get_user_gemini_api_key(user)
    if user_api_key:
        logger.info(f"Using user {user.email}'s personal Gemini API key")
        return user_api_key

    # No personal API key available
    raise ValueError("Missing Gemini API key. Please add your API key via the Settings icon to use this feature.")


def get_direct_api_key_from_request(request) -> Optional[str]:
    """
    Extract the Gemini API key from the X-Gemini-API-Key header.
    Returns None if header is absent or empty.
    """
    key = request.headers.get("X-Gemini-API-Key", "").strip()
    return key if key else None
