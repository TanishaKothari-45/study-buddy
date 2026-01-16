"""
API Key Encryption Utilities using Fernet (symmetric encryption)

Security:
- Uses Fernet (AES-128 with HMAC) for symmetric encryption
- Encryption key stored in environment variable (NEVER commit to git)
- Each encrypted value includes timestamp and HMAC for integrity
"""
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional
import os
import base64
import logging

logger = logging.getLogger(__name__)

class APIKeyEncryption:
    """Handles encryption/decryption of user API keys"""
    
    def __init__(self):
        # Get encryption key from settings (Single Source of Truth)
        from .config import settings
        encryption_key = settings.ENCRYPTION_KEY
        
        if not encryption_key:
            # Generate a new key for development (NEVER use this in production)
            logger.warning("⚠️  ENCRYPTION_KEY not set in .env - generating temporary key")
            logger.warning("⚠️  This key will be lost on restart - set ENCRYPTION_KEY in .env for production")
            encryption_key = Fernet.generate_key().decode()
            logger.info(f"Generated temporary encryption key: {encryption_key}")
            logger.info("Add this to your .env file: ENCRYPTION_KEY={encryption_key}")
        
        # Ensure key is properly formatted (bytes)
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        
        try:
            self.cipher = Fernet(encryption_key)
        except Exception as e:
            raise ValueError(f"Invalid ENCRYPTION_KEY format. Generate a new key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' - Error: {e}")
    
    def encrypt_api_key(self, api_key: str) -> str:
        """
        Encrypt an API key for secure storage
        
        Args:
            api_key: Plain text API key
        
        Returns:
            Base64-encoded encrypted API key
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        
        try:
            # Encrypt the API key (returns bytes)
            encrypted_bytes = self.cipher.encrypt(api_key.encode())
            # Convert to string for database storage
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError("Failed to encrypt API key")
    
    def decrypt_api_key(self, encrypted_api_key: str) -> Optional[str]:
        """
        Decrypt an encrypted API key
        
        Args:
            encrypted_api_key: Base64-encoded encrypted API key
        
        Returns:
            Plain text API key or None if decryption fails
        """
        if not encrypted_api_key:
            return None
        
        try:
            # Decrypt the API key
            decrypted_bytes = self.cipher.decrypt(encrypted_api_key.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            logger.error("Invalid token - API key may have been tampered with or encryption key changed")
            return None
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def mask_api_key(self, api_key: str, visible_chars: int = 4) -> str:
        """
        Mask an API key for display (show only last N characters)
        
        Args:
            api_key: Plain text API key
            visible_chars: Number of characters to show at the end
        
        Returns:
            Masked API key (e.g., "**********xyz123")
        """
        if not api_key or len(api_key) <= visible_chars:
            return "*" * 12
        
        return "*" * (len(api_key) - visible_chars) + api_key[-visible_chars:]


# Singleton instance
_encryption_instance = None

def get_api_key_encryptor() -> APIKeyEncryption:
    """Get singleton encryption instance"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = APIKeyEncryption()
    return _encryption_instance
