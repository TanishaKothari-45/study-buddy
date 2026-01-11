"""
Centralized error handling middleware for FastAPI
"""
import logging
import traceback
import sys
from datetime import datetime
from typing import Union
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.exceptions import AppException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/app.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handle custom application exceptions
    """
    logger.error(
        f"AppException: {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": str(request.url),
            "method": request.method
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "error_code": exc.error_code,
            "details": exc.details,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url.path)
        }
    )


async def validation_exception_handler(
    request: Request, 
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(
        f"Validation error: {len(errors)} field(s) failed",
        extra={
            "path": str(request.url),
            "errors": errors
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation failed",
            "error_code": "VALIDATION_ERROR",
            "details": {"errors": errors},
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url.path)
        }
    )


async def http_exception_handler(
    request: Request, 
    exc: StarletteHTTPException
) -> JSONResponse:
    """
    Handle standard HTTP exceptions
    """
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        extra={
            "path": str(request.url),
            "method": request.method,
            "status_code": exc.status_code
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url.path)
        }
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions
    """
    # Log full traceback for debugging
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "path": str(request.url),
            "method": request.method,
            "traceback": traceback.format_exc()
        }
    )
    
    # Don't expose internal errors to client in production
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected error occurred",
            "error_code": "INTERNAL_SERVER_ERROR",
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url.path),
            # Only include details in development
            "details": {"message": str(exc)} if __debug__ else {}
        }
    )


def setup_exception_handlers(app):
    """
    Register all exception handlers with the FastAPI app
    """
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    
    logger.info("✅ Exception handlers registered")
