from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.routers.auth import router as auth_router
from app.routers.meetings import router as meetings_router


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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(meetings_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="meeting-ai-backend",
        version="0.1.0",
        environment=settings.environment,
    )
