"""
FlexFlow FastAPI server. Health and readiness only; agent runs via app.agent.
No video or audio stored; all processing is in-memory.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(".env.local")
load_dotenv()

_POSE_MODEL_PATH = Path(__file__).parent / "app" / "models" / "pose_landmarker_lite.task"

app = FastAPI(
    title="FlexFlow",
    description="Real-time AI movement coach backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "FlexFlow backend is running!"}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", service="flexflow")


@app.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    """Readiness probe (e.g. after env/API keys loaded)."""
    required = ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL", "GOOGLE_API_KEY")
    livekit_url = os.getenv("LIVEKIT_URL", "")
    parsed_url = urlparse(livekit_url)
    if (
        not all(os.getenv(name) for name in required)
        or parsed_url.scheme not in {"ws", "wss"}
        or not parsed_url.netloc
        or not _POSE_MODEL_PATH.is_file()
    ):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="not_ready", service="flexflow")
    return HealthResponse(status="ok", service="flexflow")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
