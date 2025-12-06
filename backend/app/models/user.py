from sqlalchemy import Boolean, Column, Integer, String, Text
from ..core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    encrypted_gemini_api_key = Column(Text, nullable=True)  # Encrypted user Gemini API key
