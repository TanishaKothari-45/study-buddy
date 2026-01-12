"""
User Profile Service for Supabase

Handles all user profile operations using Supabase's user_profiles table.
Replaces the SQLAlchemy User model for profile data storage.
"""

from typing import Optional
from pydantic import BaseModel
import logging
from datetime import datetime
from .supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    """
    User profile data from Supabase user_profiles table.
    
    This replaces the SQLAlchemy User model for user-specific data storage.
    The id is the Supabase auth.users UUID.
    """
    id: str  # Supabase user UUID
    email: Optional[str] = None  # From JWT token, not stored in profile
    full_name: Optional[str] = None
    encrypted_gemini_api_key: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """
    Fetch user profile from Supabase by user ID.
    
    Args:
        user_id: Supabase user UUID
        
    Returns:
        UserProfile if found, None otherwise
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("user_profiles").select("*").eq("id", user_id).execute()
        
        if result.data and len(result.data) > 0:
            profile_data = result.data[0]
            return UserProfile(
                id=profile_data["id"],
                full_name=profile_data.get("full_name"),
                encrypted_gemini_api_key=profile_data.get("encrypted_gemini_api_key"),
                created_at=profile_data.get("created_at"),
                updated_at=profile_data.get("updated_at"),
            )
        return None
    except Exception as e:
        logger.error(f"Error fetching user profile for {user_id}: {e}")
        return None


def get_or_create_user_profile(
    user_id: str, 
    email: Optional[str] = None,
    full_name: Optional[str] = None
) -> UserProfile:
    """
    Get existing user profile or create a new one.
    
    Args:
        user_id: Supabase user UUID
        email: User's email (for logging purposes)
        full_name: User's full name from JWT user_metadata (used when creating new profile)
        
    Returns:
        UserProfile (existing or newly created)
    """
    # Try to get existing profile
    profile = get_user_profile(user_id)
    if profile:
        profile.email = email  # Add email from JWT
        return profile
    
    # Create new profile
    try:
        supabase = get_supabase_client()
        result = supabase.table("user_profiles").insert({
            "id": user_id,
            "full_name": full_name,
            "encrypted_gemini_api_key": None,
        }).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"✅ Created new user profile for {email or user_id} with name: {full_name}")
            profile_data = result.data[0]
            return UserProfile(
                id=profile_data["id"],
                email=email,
                full_name=profile_data.get("full_name"),
                encrypted_gemini_api_key=profile_data.get("encrypted_gemini_api_key"),
                created_at=profile_data.get("created_at"),
                updated_at=profile_data.get("updated_at"),
            )
    except Exception as e:
        logger.error(f"Error creating user profile for {user_id}: {e}")
    
    # Return a minimal profile even if creation fails
    return UserProfile(id=user_id, email=email, full_name=full_name)


def update_user_profile(
    user_id: str,
    full_name: Optional[str] = None,
    encrypted_gemini_api_key: Optional[str] = None,
) -> bool:
    """
    Update user profile fields.
    
    Args:
        user_id: Supabase user UUID
        full_name: New full name (or None to keep existing)
        encrypted_gemini_api_key: New encrypted API key (or None to keep existing)
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        supabase = get_supabase_client()
        
        # Build update data (only include non-None fields)
        update_data = {"updated_at": "now()"}
        if full_name is not None:
            update_data["full_name"] = full_name
        if encrypted_gemini_api_key is not None:
            update_data["encrypted_gemini_api_key"] = encrypted_gemini_api_key
        
        result = supabase.table("user_profiles").update(update_data).eq("id", user_id).execute()
        
        if result.data:
            logger.info(f"✅ Updated user profile for {user_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating user profile for {user_id}: {e}")
        return False


def set_user_gemini_api_key(user_id: str, encrypted_key: str) -> bool:
    """
    Set or update user's encrypted Gemini API key.
    
    Args:
        user_id: Supabase user UUID
        encrypted_key: Encrypted API key string
        
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("user_profiles").update({
            "encrypted_gemini_api_key": encrypted_key,
            "updated_at": "now()"
        }).eq("id", user_id).execute()
        
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error setting API key for {user_id}: {e}")
        return False


def delete_user_gemini_api_key(user_id: str) -> bool:
    """
    Delete user's Gemini API key.
    
    Args:
        user_id: Supabase user UUID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("user_profiles").update({
            "encrypted_gemini_api_key": None,
            "updated_at": "now()"
        }).eq("id", user_id).execute()
        
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error deleting API key for {user_id}: {e}")
        return False
