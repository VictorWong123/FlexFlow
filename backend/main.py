"""
FlexFlow FastAPI server. Health and readiness only; agent runs via app.agent.
No video or audio stored; all processing is in-memory.
"""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

load_dotenv(".env.local")
load_dotenv()

app = FastAPI(
    title="FlexFlow",
    description="Real-time AI Physical Therapist backend",
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


class TokenRequest(BaseModel):
    room_name: str = "flexflow-room"
    participant_identity: str = "user"
    participant_name: str | None = None


class TokenResponse(BaseModel):
    server_url: str
    participant_token: str


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "FlexFlow backend is running!"}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", service="flexflow")


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Readiness probe (e.g. after env/API keys loaded)."""
    return HealthResponse(status="ok", service="flexflow")


@app.post("/api/token", response_model=TokenResponse)
async def get_token(request: TokenRequest) -> TokenResponse:
    """
    Generate LiveKit access token for frontend connection.
    Frontend calls this to get a token before connecting to LiveKit.
    """
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set",
        )

    if not livekit_url:
        raise HTTPException(
            status_code=500, detail="LIVEKIT_URL must be set"
        )

    token = api.AccessToken(api_key=api_key, api_secret=api_secret)
    token.with_identity(request.participant_identity)
    if request.participant_name:
        token.with_name(request.participant_name)

    grants = api.VideoGrants(
        room_join=True,
        room=request.room_name,
        can_publish=True,
        can_subscribe=True,
    )
    token.with_grants(grants)
    token.with_ttl(timedelta(hours=6))

    jwt_token = token.to_jwt()

    server_url = livekit_url.replace("wss://", "https://").replace(
        "ws://", "http://"
    )

    return TokenResponse(server_url=server_url, participant_token=jwt_token)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
