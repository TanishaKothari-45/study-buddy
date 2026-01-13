"""
Database configuration supporting both SQLite (local) and PostgreSQL (Cloud Run).
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings, IS_CLOUD_RUN

logger = logging.getLogger(__name__)

# ===========================================
# Database URL Selection
# ===========================================

if IS_CLOUD_RUN and settings.DATABASE_URL:
    # Cloud Run: Use PostgreSQL via Cloud SQL
    SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

    # Cloud SQL connection configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800,  # Recycle connections every 30 minutes
        pool_pre_ping=True,  # Enable connection health checks
    )
    logger.info("✅ Using PostgreSQL (Cloud SQL) for database")
else:
    # Local development: Use SQLite
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.DB_DIR}/sql_app.db"

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}  # SQLite-specific
    )
    logger.info("✅ Using SQLite for database (local development)")

# ===========================================
# Session Configuration
# ===========================================

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency to get database session.
    Use with FastAPI Depends() for request-scoped sessions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Called on application startup.
    Handles concurrent initialization from multiple workers gracefully.
    """
    from ..models import User  # Import models to register them
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables initialized")
    except Exception as e:
        # Handle case where tables already exist (e.g., from another worker)
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate" in error_msg:
            logger.info("✅ Database tables already exist (likely initialized by another worker)")
        else:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise


def check_db_connection() -> bool:
    """
    Check if database connection is healthy.
    Used for health checks.
    """
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
