"""
API Key Management Routes

Handles user-specific Gemini API key CRUD operations with encryption.
Users can set, check, and delete their own API keys.

Uses Supabase user_profiles table for storage.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import logging

# TODO: REVERT FOR PROD — get_current_user_optional is used by validate-no-auth endpoint (~line 65).
# Change that endpoint back to require get_current_user if unauthenticated access should be blocked.
from ..core.deps import get_current_user, get_current_user_optional

from ..core.encryption import get_api_key_encryptor
from ..core.user_profile import (
    UserProfile,
    set_user_gemini_api_key,
    delete_user_gemini_api_key,
)
from ..gemini_core.gemini_client import GeminiClient

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================
# Pydantic Models
# ============================================================

class ApiKeySetRequest(BaseModel):
    """Request to set/update Gemini API key"""
    api_key: str = Field(..., min_length=20, max_length=200, description="Gemini API key")

class ApiKeyStatusResponse(BaseModel):
    """Response showing API key status"""
    has_api_key: bool
    is_authenticated: bool
    masked_key: Optional[str] = None

class ApiKeySetResponse(BaseModel):
    """Response after setting API key"""
    success: bool
    message: str
    masked_key: str

class ApiKeyDeleteResponse(BaseModel):
    """Response after deleting API key"""
    success: bool
    message: str

# ============================================================
# Helpers
# ============================================================

def validate_gemini_key(api_key: str) -> bool:
    """Validate API key via GeminiClient"""
    return GeminiClient.validate_api_key(api_key)

# ============================================================
# Routes
# ============================================================

@router.get("/status", response_model=ApiKeyStatusResponse)
def get_api_key_status(
    current_user: Optional[UserProfile] = Depends(get_current_user_optional),
):
    """
    Check if user has set their Gemini API key (without exposing the actual key)
    Works for both authenticated and unauthenticated requests.
    """
    # If user is not authenticated, return early
    if current_user is None:
        return {
            "has_api_key": False,
            "is_authenticated": False,
            "masked_key": None
        }
    
    has_key = current_user.encrypted_gemini_api_key is not None
    masked_key = None
    
    if has_key:
        # Decrypt and mask the key for display
        encryptor = get_api_key_encryptor()
        decrypted_key = encryptor.decrypt_api_key(current_user.encrypted_gemini_api_key)
        if decrypted_key:
            masked_key = encryptor.mask_api_key(decrypted_key, visible_chars=4)
    
    return {
        "has_api_key": has_key,
        "is_authenticated": True,
        "masked_key": masked_key
    }

@router.post("/set", response_model=ApiKeySetResponse)
def set_api_key(
    request: ApiKeySetRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Set or update user's Gemini API key (encrypted before storage)
    
    Security:
    - API key is encrypted using Fernet before database storage
    - Original key is never stored in plain text
    - Only the user can decrypt and use their own key
    """
    try:
        # Validate API key format (basic check)
        api_key = request.api_key.strip()
        if not api_key.startswith("AI"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid API key format. Gemini API keys typically start with 'AI'"
            )
        
        # LIVE VALIDATION
        if not validate_gemini_key(api_key):
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The API key is invalid or unauthorized. Please check your key at https://aistudio.google.com/app/apikey"
            )
        
        # Encrypt the API key
        encryptor = get_api_key_encryptor()
        encrypted_key = encryptor.encrypt_api_key(api_key)
        
        # Store encrypted key in Supabase
        success = set_user_gemini_api_key(current_user.id, encrypted_key)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save API key. Please try again."
            )

        # Generate masked version for response
        masked_key = encryptor.mask_api_key(api_key, visible_chars=4)
        
        logger.info(f"✅ User {current_user.email} set their Gemini API key")
        
        return {
            "success": True,
            "message": "API key saved successfully and encrypted",
            "masked_key": masked_key
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Encryption error for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt API key. Please try again."
        )
    except Exception as e:
        logger.error(f"Error setting API key for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save API key: {str(e)}"
        )

@router.delete("/delete", response_model=ApiKeyDeleteResponse)
def delete_api_key(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Delete user's Gemini API key
    """
    try:
        if not current_user.encrypted_gemini_api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No API key found to delete"
            )
        
        # Remove encrypted key from Supabase
        success = delete_user_gemini_api_key(current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete API key. Please try again."
            )

        logger.info(f"✅ User {current_user.email} deleted their Gemini API key")
        
        return {
            "success": True,
            "message": "API key deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )

@router.post("/validate", response_model=ApiKeySetResponse)
def validate_key_only(
    request: ApiKeySetRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Validate a Gemini API key without saving it.
    """
    api_key = request.api_key.strip()
    if not api_key.startswith("AI"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API key format."
        )
    
    if validate_gemini_key(api_key):
        return {
            "success": True,
            "message": "API key is valid",
            "masked_key": "********"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API key."
        )


@router.post("/validate-no-auth")
def validate_key_no_auth(request: ApiKeySetRequest):
    """
    Validate a Gemini API key WITHOUT requiring authentication.
    Used in no-auth India mode where Supabase is inaccessible.
    The key is validated against Gemini but NOT stored server-side;
    the frontend stores it in localStorage.
    """
    api_key = request.api_key.strip()
    if not api_key.startswith("AI"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API key format. Gemini API keys typically start with 'AI'"
        )

    if validate_gemini_key(api_key):
        encryptor = get_api_key_encryptor()
        masked = encryptor.mask_api_key(api_key, visible_chars=4)
        return {
            "success": True,
            "message": "API key is valid",
            "masked_key": masked
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The API key is invalid or unauthorized. Please check your key at https://aistudio.google.com/app/apikey"
        )


@router.get("/verify", response_model=ApiKeySetResponse)
def verify_current_key(
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Verify the user's currently stored Gemini API key.
    
    This endpoint:
    1. Decrypts the stored API key
    2. Validates it against Google's Gemini API (with retry logic)
    3. Returns success if valid, error if invalid
    """
    logger.debug(f"Verifying API key for user {current_user.email}")
    
    if not current_user.encrypted_gemini_api_key:
        logger.warning(f"User {current_user.email} has no encrypted API key stored")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No API key configured."
        )
    
    # Decrypt the key
    encryptor = get_api_key_encryptor()
    decrypted_key = encryptor.decrypt_api_key(current_user.encrypted_gemini_api_key)
    
    if not decrypted_key:
        logger.error(f"Failed to decrypt API key for user {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt stored API key."
        )

    logger.debug(f"Decrypted API key for user {current_user.email}, validating with Gemini...")
    
    if validate_gemini_key(decrypted_key):
        logger.info(f"✅ API key verified successfully for user {current_user.email}")
        return {
            "success": True,
            "message": "API key is valid",
            "masked_key": encryptor.mask_api_key(decrypted_key, visible_chars=4)
        }
    else:
        logger.warning(f"❌ API key validation failed for user {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stored API key is invalid or unauthorized."
        )
