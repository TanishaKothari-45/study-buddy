from sqlalchemy import Boolean, Column, Integer, String, Text
from ..core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    supabase_user_id = Column(String, unique=True, index=True, nullable=True)  # Supabase UUID
    email = Column(String, unique=True, index=True)
    full_name = Column(String, index=True)
    hashed_password = Column(String, nullable=True)  # Nullable for Supabase-only users
    is_active = Column(Boolean, default=True)
    encrypted_gemini_api_key = Column(Text, nullable=True)  # Encrypted user Gemini API key
