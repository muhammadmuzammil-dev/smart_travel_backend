"""
Simple script to run the FastAPI server.
Run this from the backend directory: python run_server.py
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

