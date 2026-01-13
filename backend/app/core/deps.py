from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional
import redis.asyncio as redis_async
from .database import get_db
from .security import SECRET_KEY, ALGORITHM
from .config import settings
from ..models.user import User
from ..schemas.user import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency - returns None for unauthenticated requests
    instead of raising 401. Useful for endpoints that need to differentiate between
    authenticated and unauthenticated states.
    """
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        token_data = TokenData(email=email)
    except JWTError:
        return None
    
    user = db.query(User).filter(User.email == token_data.email).first()
    return user


# ===========================================
# Redis Client Helper (uses settings for host/port)
# ===========================================

def get_redis_client() -> redis_async.Redis:
    """
    Get async Redis client using settings.
    Uses REDIS_URL from environment (supports Docker and Cloud Run).
    
    Usage:
        client = get_redis_client()
        await client.set("key", "value")
    """
    return redis_async.Redis(
        host=settings.redis_host,
        port=settings.redis_port_from_url,
        decode_responses=True
    )
