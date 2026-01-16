"""
Protected API Routes (Supabase Auth)

Sample protected endpoints demonstrating Supabase JWT authentication.
These endpoints require a valid Supabase access token in the Authorization header.
"""

from fastapi import APIRouter, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from jose import jwt
from ..core.supabase_auth import (
    verify_supabase_token,
    get_supabase_user,
    get_supabase_user_optional,
    SupabaseUser,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)


@router.get("/debug-token")
async def debug_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Debug endpoint to inspect JWT token structure.
    
    Use this to diagnose JWT verification issues.
    Returns the token header (algorithm, type) without verifying the signature.
    """
    if credentials is None:
        return {
            "status": "error",
            "message": "No Authorization header provided",
        }
    
    token = credentials.credentials
    
    try:
        # Get unverified header to see the algorithm
        header = jwt.get_unverified_header(token)
        
        # Get unverified claims (payload) to see the structure
        # This doesn't verify the signature, just decodes
        claims = jwt.get_unverified_claims(token)
        
        return {
            "status": "success",
            "header": header,
            "claims": {
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "aud": claims.get("aud"),
                "role": claims.get("role"),
                "exp": claims.get("exp"),
                "iat": claims.get("iat"),
            },
            "note": "This is unverified data - for debugging only"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to decode token: {str(e)}",
        }


@router.get("/protected-test")
async def protected_test(user_id: str = Depends(verify_supabase_token)):
    """
    Sample protected endpoint that requires authentication.
    
    This endpoint demonstrates basic Supabase token verification.
    It returns the authenticated user's ID.
    
    Headers Required:
        Authorization: Bearer <supabase_access_token>
        
    Returns:
        - 200: Success with user_id
        - 401: Invalid or missing token
    """
    return {
        "status": "success",
        "message": "You are authenticated!",
        "user_id": user_id,
    }


@router.get("/protected-user-info")
async def protected_user_info(user: SupabaseUser = Depends(get_supabase_user)):
    """
    Protected endpoint that returns full user info from the JWT.
    
    This demonstrates how to access additional claims from the Supabase token,
    such as email and role.
    
    Headers Required:
        Authorization: Bearer <supabase_access_token>
        
    Returns:
        - 200: Success with user info (id, email, role)
        - 401: Invalid or missing token
    """
    return {
        "status": "success",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        },
    }


@router.get("/optional-auth-test")
async def optional_auth_test(
    user_id: Optional[str] = Depends(get_supabase_user_optional)
):
    """
    Endpoint that works for both authenticated and unauthenticated users.
    
    Demonstrates optional authentication - enhanced features for logged-in users,
    basic access for anonymous users.
    
    Headers (Optional):
        Authorization: Bearer <supabase_access_token>
        
    Returns:
        - 200: Different response based on authentication status
    """
    if user_id:
        return {
            "status": "authenticated",
            "message": "Welcome back!",
            "user_id": user_id,
            "features": ["full_access", "personalization", "history"],
        }
    else:
        return {
            "status": "anonymous",
            "message": "Hello, guest! Log in for more features.",
            "features": ["basic_access"],
        }
