from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import verify_password, get_password_hash, create_access_token
from ..core.deps import get_current_user
from ..models.user import User
from ..schemas.user import UserCreate, UserLogin, Token, User as UserSchema, PasswordResetRequest, PasswordReset, PasswordResetResponse

router = APIRouter()

@router.post("/signup", response_model=UserSchema)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_credentials.email).first()
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Check if email exists for password reset"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email"
        )
    # In a production app, you would send an email with a reset token
    # For simplicity, we just confirm the email exists
    return {"message": "Email verified. You can now reset your password."}

@router.post("/reset-password", response_model=PasswordResetResponse)
def reset_password(request: PasswordReset, db: Session = Depends(get_db)):
    """Reset password for a user"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email"
        )
    
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    return {"message": "Password reset successfully. You can now login with your new password."}
