"""
API v1 Router - Combines all v1 endpoints

This router aggregates all API v1 endpoints and provides
a single entry point for the versioned API.

Subject-aware routing:
- Most endpoints accept a `subject` parameter (default: "geography")
- This allows the same API structure to work across subjects
- Future subjects: history, polity, economy, etc.
"""
from fastapi import APIRouter

# Import existing routers from routes module
# This allows gradual migration without breaking changes
from ...routes import (
    upload,
    upload_content_store,
    query,
    mock_test,
    mains_answer,
    evaluate_answer,
    training_data,
    feedback,
    auth,
    api_key,
    jobs,
    protected,
)

router = APIRouter()

# Include all routers under v1
# Subject is passed as a path/query parameter in individual endpoints

router.include_router(
    upload.router,
    prefix="/upload",
    tags=["Upload"]
)

router.include_router(
    upload_content_store.router,
    prefix="/upload-content-store",
    tags=["Content Store Upload"]
)

router.include_router(
    query.router,
    prefix="/query",
    tags=["Query"]
)

router.include_router(
    mock_test.router,
    prefix="/mock-test",
    tags=["Mock Test"]
)

router.include_router(
    mains_answer.router,
    prefix="/mains-answer",
    tags=["Mains Answer"]
)

router.include_router(
    evaluate_answer.router,
    prefix="/evaluate-answer",
    tags=["Answer Evaluation"]
)

router.include_router(
    training_data.router,
    prefix="/training-data",
    tags=["Training Data"]
)

router.include_router(
    feedback.router,
    prefix="/feedback",
    tags=["Feedback"]
)

router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

router.include_router(
    api_key.router,
    prefix="/api-key",
    tags=["API Key Management"]
)

router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["Jobs"]
)

router.include_router(
    protected.router,
    tags=["Protected (Supabase Auth)"]
)
