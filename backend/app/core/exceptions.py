"""
Custom exception classes for the application
"""

class AppException(Exception):
    """Base exception for application errors"""
    def __init__(
        self, 
        message: str, 
        status_code: int = 500, 
        details: dict = None,
        error_code: str = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.error_code = error_code or "INTERNAL_ERROR"
        super().__init__(self.message)


class ValidationException(AppException):
    """Raised when input validation fails"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            status_code=400,
            details=details,
            error_code="VALIDATION_ERROR"
        )


class NotFoundException(AppException):
    """Raised when a resource is not found"""
    def __init__(self, message: str, resource_type: str = None):
        details = {"resource_type": resource_type} if resource_type else {}
        super().__init__(
            message=message,
            status_code=404,
            details=details,
            error_code="NOT_FOUND"
        )


class AuthenticationException(AppException):
    """Raised when authentication fails"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationException(AppException):
    """Raised when user lacks permissions"""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR"
        )


class ExternalServiceException(AppException):
    """Raised when external service (LLM, vector store) fails"""
    def __init__(self, message: str, service_name: str = None):
        details = {"service": service_name} if service_name else {}
        super().__init__(
            message=message,
            status_code=503,
            details=details,
            error_code="EXTERNAL_SERVICE_ERROR"
        )


class RateLimitException(AppException):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = None):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(
            message=message,
            status_code=429,
            details=details,
            error_code="RATE_LIMIT_EXCEEDED"
        )
