"""
Script to run the FastAPI backend
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        timeout_keep_alive=300  # Keep connections alive for 5 minutes (for long-running requests)
    )
