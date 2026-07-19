"""Entry point — run with: uvicorn main:app --reload

Or via the Docker Compose setup (recommended for development).
"""

from api.app import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
