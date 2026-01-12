"""
Authentication Routes

Handles user authentication via Supabase.
User profile data is stored in Supabase's user_profiles table.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from ..core.deps import get_current_user
from ..core.supabase_auth import get_supabase_user, SupabaseUser
from ..core.user_profile import UserProfile, get_user_profile, update_user_profile

router = APIRouter()


class UserMeResponse(BaseModel):
    """Response schema for /me endpoint"""
    id: str  # Supabase UUID
    email: str
    full_name: Optional[str] = None
    has_gemini_api_key: bool = False


class UpdateProfileRequest(BaseModel):
    """Request to update user profile"""
    full_name: Optional[str] = None


class UpdateProfileResponse(BaseModel):
    """Response after updating profile"""
    success: bool
    message: str


@router.get("/me", response_model=UserMeResponse)
async def read_users_me(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Get current user profile.
    
    Verifies the Supabase JWT token and returns user info from the user_profiles table.
    """
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email or "",
        full_name=current_user.full_name,
        has_gemini_api_key=current_user.encrypted_gemini_api_key is not None,
    )


@router.put("/profile", response_model=UpdateProfileResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Update user profile information.
    """
    success = update_user_profile(
        user_id=current_user.id,
        full_name=request.full_name,
    )
    
    if success:
        return {
            "success": True,
            "message": "Profile updated successfully"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )
