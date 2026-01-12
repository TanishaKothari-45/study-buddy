"""
Authentication Dependencies for FastAPI

Provides dependency functions for authenticating users via Supabase JWT tokens.
User profile data is stored in Supabase's user_profiles table.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt, jwk
from typing import Optional, Dict, Any
import logging
import httpx
import time
from .config import settings
from .user_profile import UserProfile, get_or_create_user_profile

logger = logging.getLogger(__name__)

# Use HTTPBearer for Supabase token authentication
security = HTTPBearer(auto_error=False)

# Supabase JWT verification - supports both HS256 and ES256
# ES256 requires fetching public keys from JWKS endpoint
SUPABASE_ALGORITHMS = ["ES256", "HS256", "HS384", "HS512", "RS256"]

# Cache for JWKS keys (to avoid fetching on every request)
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_expiry: float = 0
JWKS_CACHE_TTL = 3600  # Cache JWKS for 1 hour


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
    
    # Return cached keys if still valid
    if _jwks_cache and current_time < _jwks_cache_expiry:
        return _jwks_cache
    
    try:
        jwks_url = _get_jwks_url()
        logger.info(f"Fetching JWKS from: {jwks_url}")
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_expiry = current_time + JWKS_CACHE_TTL
            logger.info(f"JWKS fetched successfully, {len(_jwks_cache.get('keys', []))} keys found")
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            logger.warning("Using expired JWKS cache as fallback")
            return _jwks_cache
        raise


def _get_signing_key(token: str) -> Any:
    """Get the signing key for the given token from JWKS."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")
        
        logger.debug(f"Token algorithm: {alg}, kid: {kid}")
        
        # For HS256/HS384/HS512, use the shared secret
        if alg in ["HS256", "HS384", "HS512"]:
            return settings.SUPABASE_JWT_SECRET
        
        # For ES256/RS256, fetch from JWKS
        if alg in ["ES256", "RS256"]:
            jwks = _fetch_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    return jwk.construct(key)
            
            logger.error(f"No matching key found for kid: {kid}")
            raise ValueError(f"No matching key found for kid: {kid}")
        
        raise ValueError(f"Unsupported algorithm: {alg}")
        
    except Exception as e:
        logger.error(f"Failed to get signing key: {e}")
        raise


def _verify_token(token: str) -> tuple[str, Optional[str], Optional[str]]:
    """
    Verify a Supabase JWT token and extract user info.
    
    Returns:
        Tuple of (user_id, email, full_name)
        
    Raises:
        HTTPException: If token is invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Get the appropriate signing key based on token algorithm
        signing_key = _get_signing_key(token)
        
        # Get the algorithm from the token header
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg", "HS256")
        
        logger.debug(f"Verifying token with algorithm: {algorithm}")
        
        # Verify the token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            options={
                "verify_aud": False,  # Don't require audience claim
            }
        )
        
        # Supabase uses 'sub' for user UUID
        user_id: str = payload.get("sub")
        email: Optional[str] = payload.get("email")
        
        # Extract full_name from user_metadata (set during signup)
        user_metadata = payload.get("user_metadata", {})
        full_name: Optional[str] = user_metadata.get("full_name") if user_metadata else None
        
        if user_id is None:
            logger.warning("JWT missing 'sub' claim")
            raise credentials_exception
        
        return user_id, email, full_name
            
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserProfile:
    """
    Authenticate user via Supabase JWT token.
    
    Verifies the token and returns the user's profile from Supabase.
    Creates a profile record if one doesn't exist.
    
    Returns:
        UserProfile: User profile from Supabase user_profiles table
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id, email, full_name = _verify_token(credentials.credentials)
    
    # Get or create user profile in Supabase
    profile = get_or_create_user_profile(user_id, email, full_name)
    return profile


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserProfile]:
    """
    Optional authentication dependency - returns None for unauthenticated requests.
    
    Use this for endpoints that work for both authenticated and unauthenticated users.
    """
    if credentials is None:
        return None
    
    try:
        user_id, email, full_name = _verify_token(credentials.credentials)
        profile = get_or_create_user_profile(user_id, email, full_name)
        return profile
    except HTTPException:
        return None
