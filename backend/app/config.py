import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str
    frontend_url: str
    database_url: str
    session_lifetime_hours: int
    session_cookie_secure: bool

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_lifetime_hours * 60 * 60

    @classmethod
    def from_env(cls, environment: Mapping[str, str]) -> "Settings":
        app_environment = environment.get("APP_ENV", "local").strip().lower() or "local"
        lifetime_hours = _parse_session_lifetime_hours(
            environment.get("SESSION_LIFETIME_HOURS")
        )
        cookie_secure = _parse_session_cookie_secure(
            environment.get("SESSION_COOKIE_SECURE")
        )
        if app_environment == "production" and not cookie_secure:
            raise ValueError("production環境ではSESSION_COOKIE_SECURE=trueが必要です。")

        return cls(
            environment=app_environment,
            frontend_url=environment.get("FRONTEND_URL", "http://localhost:3000")
            or "http://localhost:3000",
            database_url=environment.get("DATABASE_URL") or "sqlite:///./data/meeting_ai.db",
            session_lifetime_hours=lifetime_hours,
            session_cookie_secure=cookie_secure,
        )


def _parse_session_lifetime_hours(value: str | None) -> int:
    if value is None or value.strip() == "":
        return 8
    normalized = value.strip()
    if not normalized.isdecimal():
        raise ValueError("SESSION_LIFETIME_HOURSには整数を指定してください。")
    lifetime_hours = int(normalized)
    if not 1 <= lifetime_hours <= 168:
        raise ValueError("SESSION_LIFETIME_HOURSは1以上168以下で指定してください。")
    return lifetime_hours


def _parse_session_cookie_secure(value: str | None) -> bool:
    if value is None or value.strip() == "":
        return False
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("SESSION_COOKIE_SECUREにはtrueまたはfalseを指定してください。")


def get_settings() -> Settings:
    return settings


settings = Settings.from_env(os.environ)
