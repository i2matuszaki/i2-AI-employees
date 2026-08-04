import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("APP_ENV", "local")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    database_url: str = os.getenv("DATABASE_URL") or "sqlite:///./data/meeting_ai.db"


settings = Settings()
