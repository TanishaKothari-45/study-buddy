"""
Supabase JWT Token Verification for FastAPI

This module provides dependency functions to verify Supabase JWT tokens
for protecting API endpoints. Users authenticate via Supabase on the frontend,
and this backend verifies those tokens using Supabase's JWKS public keys (ES256)
or the JWT secret (HS256).

Usage:
    from app.core.supabase_auth import verify_supabase_token, get_supabase_user_optional
    
    @router.get("/protected")
    async def protected_route(user_id: str = Depends(verify_supabase_token)):
        return {"user_id": user_id}
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt, jwk
from typing import Optional, Dict, Any
import logging
import httpx
import time
from pydantic import BaseModel
from .config import settings

logger = logging.getLogger(__name__)

# Use HTTPBearer instead of OAuth2PasswordBearer for cleaner Supabase integration
security = HTTPBearer(auto_error=False)

# Cache for JWKS keys
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_expiry: float = 0
JWKS_CACHE_TTL = 3600


class SupabaseUser(BaseModel):
    """Supabase user info extracted from JWT token"""
    id: str  # Supabase user UUID (from 'sub' claim)
    email: Optional[str] = None
    role: Optional[str] = None


def _get_jwks_url() -> str:
    """Get the JWKS URL for the Supabase project."""
    supabase_url = settings.SUPABASE_URL
    if not supabase_url:
        raise ValueError("SUPABASE_URL is required for ES256 token verification")
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> Dict[str, Any]:
    """Fetch JWKS from Supabase with caching."""
    global _jwks_cache, _jwks_cache_expiry
    
    current_time = time.time()
    if _jwks_cache and current_time < _jwks_cache_expiry:
        return _jwks_cache
    
    try:
        jwks_url = _get_jwks_url()
        with httpx.Client(timeout=10.0) as client:
            response = client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_expiry = current_time + JWKS_CACHE_TTL
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            return _jwks_cache
        raise


def _get_signing_key_local(token: str) -> Any:
    """Get the signing key for the given token."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")
        
        if alg in ["HS256", "HS384", "HS512"]:
            return settings.SUPABASE_JWT_SECRET
        
        if alg in ["ES256", "RS256"]:
            jwks = _fetch_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    return jwk.construct(key)
            raise ValueError(f"No matching key found for kid: {kid}")
        
        raise ValueError(f"Unsupported algorithm: {alg}")
    except Exception as e:
        logger.error(f"Failed to get signing key: {e}")
        raise


def _decode_supabase_token(token: str) -> dict:
    """
    Decode and verify a Supabase JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        signing_key = _get_signing_key_local(token)
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg", "HS256")
        
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            options={"verify_aud": False}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError as e:
        logger.warning(f"JWT key error: {e}")
        raise credentials_exception
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise credentials_exception


async def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Dependency that verifies the Supabase JWT token and returns the user_id.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = _decode_supabase_token(token)
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id


async def get_supabase_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> SupabaseUser:
    """
    Dependency that verifies the token and returns full user info.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = _decode_supabase_token(token)
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return SupabaseUser(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role"),
    )


async def get_supabase_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Optional authentication - returns user_id if authenticated, None otherwise.
    """
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        payload = _decode_supabase_token(token)
        return payload.get("sub")
    except HTTPException:
        return None
