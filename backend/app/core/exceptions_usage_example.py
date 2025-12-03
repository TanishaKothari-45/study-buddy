"""
Example usage of custom exceptions in routes
"""
from fastapi import APIRouter, Depends
from app.core.exceptions import (
    AppException,
    ValidationException,
    NotFoundException,
    ExternalServiceException
)

router = APIRouter()

# Example 1: Validation error
@router.post("/example")
async def example_endpoint(data: dict):
    if not data.get("required_field"):
        raise ValidationException(
            message="Missing required field",
            details={"field": "required_field", "expected": "string"}
        )
    return {"status": "success"}


# Example 2: Not found error
@router.get("/resource/{resource_id}")
async def get_resource(resource_id: str):
    # Simulate database lookup
    resource = None  # db.get(resource_id)
    
    if not resource:
        raise NotFoundException(
            message=f"Resource with ID '{resource_id}' not found",
            resource_type="Resource"
        )
    
    return resource


# Example 3: External service error
@router.post("/generate")
async def generate_content(prompt: str):
    try:
        # Call external LLM service
        response = await call_llm_service(prompt)
        return response
    except Exception as e:
        raise ExternalServiceException(
            message=f"Failed to generate content: {str(e)}",
            service_name="OpenAI"
        )


# Example 4: Generic app error with custom details
@router.post("/process")
async def process_data(data: dict):
    try:
        result = complex_processing(data)
        return result
    except ValueError as e:
        raise AppException(
            message="Data processing failed",
            status_code=400,
            details={"reason": str(e), "data_keys": list(data.keys())},
            error_code="PROCESSING_ERROR"
        )


# Helper functions (examples)
async def call_llm_service(prompt: str):
    # Simulated LLM call
    pass

def complex_processing(data: dict):
    # Simulated processing
    pass
