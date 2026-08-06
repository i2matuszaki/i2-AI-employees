import pytest

from app.config import Settings


def test_session_settings_defaults_do_not_require_module_reload() -> None:
    settings = Settings.from_env({})

    assert settings.environment == "local"
    assert settings.session_lifetime_hours == 8
    assert settings.session_max_age_seconds == 28_800
    assert settings.session_cookie_secure is False


@pytest.mark.parametrize("hours", [1, 168])
def test_session_lifetime_accepts_boundary_values(hours: int) -> None:
    settings = Settings.from_env({"SESSION_LIFETIME_HOURS": str(hours)})

    assert settings.session_lifetime_hours == hours
    assert settings.session_max_age_seconds == hours * 60 * 60


@pytest.mark.parametrize("value", ["0", "169", "1.5", "eight", "-1"])
def test_session_lifetime_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"SESSION_LIFETIME_HOURS": value})


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("TRUE", True), ("false", False)])
def test_session_cookie_secure_accepts_boolean_strings(value: str, expected: bool) -> None:
    settings = Settings.from_env({"SESSION_COOKIE_SECURE": value})

    assert settings.session_cookie_secure is expected


def test_session_cookie_secure_rejects_invalid_boolean() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"SESSION_COOKIE_SECURE": "1"})


def test_production_rejects_insecure_cookie() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"APP_ENV": " production ", "SESSION_COOKIE_SECURE": "false"})


def test_production_accepts_secure_cookie_and_normalizes_environment() -> None:
    settings = Settings.from_env(
        {"APP_ENV": " Production ", "SESSION_COOKIE_SECURE": "TRUE"}
    )

    assert settings.environment == "production"
    assert settings.session_cookie_secure is True
