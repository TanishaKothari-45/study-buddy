"""
FastAPI backend for Study Buddy
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Study Buddy API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "study-buddy-api"
    }

@app.get("/api/version")
async def get_version():
    """Get API version"""
    return {
        "version": "0.1.0",
        "name": "Study Buddy API"
    }