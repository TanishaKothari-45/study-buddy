"""
Script to run the FastAPI backend
"""
import os
import uvicorn

if __name__ == "__main__":
    # Watch the root .env file specifically so changes trigger a reload
    env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[".", env_file],
        timeout_keep_alive=300  # Keep connections alive for 5 minutes (for long-running requests)
    )
