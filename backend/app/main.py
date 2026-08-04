from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


app = FastAPI(title="AI会議秘書 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="meeting-ai-backend",
        version="0.1.0",
        environment=settings.environment,
    )
