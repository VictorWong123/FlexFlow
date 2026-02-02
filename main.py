"""
FlexFlow FastAPI server. Health and readiness only; agent runs via app.agent.
No video or audio stored; all processing in-memory.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="FlexFlow",
    description="Real-time AI Physical Therapist backend",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", service="flexflow")


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Readiness probe (e.g. after env/API keys loaded)."""
    return HealthResponse(status="ok", service="flexflow")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
