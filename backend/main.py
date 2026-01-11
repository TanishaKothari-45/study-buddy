"""
FastAPI backend for Study Buddy
Re-exports the app from the app module for backward compatibility
"""

from app.main import app

__all__ = ["app"]