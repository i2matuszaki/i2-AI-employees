from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.database.session import create_session_factory, get_db_session
from app.main import app
from app.models import User, UserSession
from app.security.password import hash_password
from app.security.session import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.utilities.datetime import utc_now

TEST_PASSWORD = "fictional-login-password"


@pytest.fixture
def session_factory(test_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(test_engine)


@pytest.fixture
def local_settings() -> Settings:
    return Settings.from_env({"SESSION_LIFETIME_HOURS": "8"})


@pytest.fixture
def seeded_users(session_factory: sessionmaker[Session]) -> dict[str, str]:
    users = [
        User(
            email="user@demo.local",
            display_name="デモ一般利用者",
            role="user",
            password_hash=hash_password(TEST_PASSWORD),
        ),
        User(
            email="inactive@demo.local",
            display_name="無効利用者",
            role="user",
            password_hash=hash_password(TEST_PASSWORD),
            is_active=False,
        ),
    ]
    with session_factory() as session:
        session.add_all(users)
        session.commit()
        return {user.email: user.id for user in users}


@pytest.fixture
def api_client(
    session_factory: sessionmaker[Session],
    local_settings: Settings,
    seeded_users: dict[str, str],
) -> Iterator[TestClient]:
    del seeded_users

    def override_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: local_settings
    try:
        with TestClient(app) as client:
            yield client
            client.cookies.clear()
    finally:
        app.dependency_overrides.clear()


def login(client: TestClient, email: str = "user@demo.local"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )


def assert_no_secrets(payload: object) -> None:
    serialized = str(payload)
    for forbidden in (
        "password",
        "password_hash",
        "token_hash",
        "session_id",
        "csrf_token",
        TEST_PASSWORD,
    ):
        assert forbidden not in serialized


def test_login_succeeds_with_normalized_email_and_creates_hashed_session(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = login(api_client, "  USER@DEMO.LOCAL  ")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": response.json()["user"]["id"],
            "email": "user@demo.local",
            "display_name": "デモ一般利用者",
            "role": "user",
        }
    }
    assert_no_secrets(response.json())

    raw_token = api_client.cookies[SESSION_COOKIE_NAME]
    with session_factory() as session:
        stored_session = session.scalar(select(UserSession))
        assert session.scalar(select(func.count()).select_from(UserSession)) == 1
        assert stored_session is not None
        assert len(stored_session.token_hash) == 64
        assert stored_session.token_hash != raw_token
        assert raw_token not in stored_session.token_hash


def test_login_cookie_attributes(api_client: TestClient) -> None:
    response = login(api_client)
    cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookie_headers if value.startswith(SESSION_COOKIE_NAME))
    csrf_cookie = next(value for value in cookie_headers if value.startswith(CSRF_COOKIE_NAME))

    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    for cookie in cookie_headers:
        assert "Path=/" in cookie
        assert "SameSite=lax" in cookie
        assert "Max-Age=28800" in cookie
        assert "Secure" not in cookie


def test_login_cookie_is_secure_with_production_settings(
    session_factory: sessionmaker[Session],
    seeded_users: dict[str, str],
) -> None:
    del seeded_users
    production_settings = Settings.from_env(
        {"APP_ENV": "production", "SESSION_COOKIE_SECURE": "true"}
    )

    def override_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: production_settings
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = login(client)
            assert all("Secure" in value for value in response.headers.get_list("set-cookie"))
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("user@demo.local", "incorrect-password"),
        ("missing@demo.local", TEST_PASSWORD),
        ("inactive@demo.local", TEST_PASSWORD),
    ],
)
def test_login_failures_use_common_unauthorized_response(
    api_client: TestClient,
    email: str,
    password: str,
) -> None:
    response = api_client.post("/api/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json() == {"detail": "認証できませんでした。"}
    assert response.headers.get_list("set-cookie") == []


def test_login_commit_failure_rolls_back_without_issuing_cookies(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit(_session: Session) -> None:
        raise SQLAlchemyError("fictional database failure")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = login(api_client)

    assert response.status_code == 500
    assert response.json() == {"detail": "認証処理に失敗しました。"}
    assert response.headers.get_list("set-cookie") == []
    assert SESSION_COOKIE_NAME not in api_client.cookies
    assert CSRF_COOKIE_NAME not in api_client.cookies
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_me_succeeds_and_updates_last_seen(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    assert login(api_client).status_code == 200
    with session_factory() as session:
        stored_session = session.scalar(select(UserSession))
        assert stored_session is not None
        previous_last_seen = stored_session.last_seen_at

    response = api_client.get("/api/auth/me")

    assert response.status_code == 200
    assert_no_secrets(response.json())
    with session_factory() as session:
        updated_session = session.scalar(select(UserSession))
        assert updated_session is not None
        assert updated_session.last_seen_at >= previous_last_seen


def test_me_rejects_missing_and_invalid_cookie(api_client: TestClient) -> None:
    missing_response = api_client.get("/api/auth/me")
    api_client.cookies.set(SESSION_COOKIE_NAME, "invalid-session-token")
    invalid_response = api_client.get("/api/auth/me")

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401
    assert missing_response.json() == invalid_response.json() == {"detail": "認証できませんでした。"}


@pytest.mark.parametrize("invalid_state", ["expired", "revoked", "inactive"])
def test_me_rejects_invalid_session_or_user(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    invalid_state: str,
) -> None:
    assert login(api_client).status_code == 200
    with session_factory() as session:
        stored_session = session.scalar(select(UserSession))
        assert stored_session is not None
        if invalid_state == "expired":
            stored_session.expires_at = utc_now() - timedelta(seconds=1)
        elif invalid_state == "revoked":
            stored_session.revoked_at = utc_now()
        else:
            user = session.get(User, stored_session.user_id)
            assert user is not None
            user.is_active = False
        session.commit()

    response = api_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "認証できませんでした。"}


@pytest.mark.parametrize("missing_part", ["cookie", "header", "mismatch"])
def test_logout_rejects_invalid_csrf(api_client: TestClient, missing_part: str) -> None:
    assert login(api_client).status_code == 200
    csrf_token = api_client.cookies[CSRF_COOKIE_NAME]
    headers = {CSRF_HEADER_NAME: csrf_token}
    if missing_part == "cookie":
        del api_client.cookies[CSRF_COOKIE_NAME]
    elif missing_part == "header":
        headers = {}
    else:
        headers[CSRF_HEADER_NAME] = "different-csrf-token"

    response = api_client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF検証に失敗しました。"}


def test_logout_revokes_only_current_session_deletes_cookies_and_returns_empty_204(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert login(api_client).status_code == 200
    current_token = api_client.cookies[SESSION_COOKIE_NAME]
    csrf_token = api_client.cookies[CSRF_COOKIE_NAME]
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "user@demo.local"))
        assert user is not None
        other_session = UserSession(
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=utc_now() + timedelta(hours=8),
        )
        session.add(other_session)
        session.commit()
        other_session_id = other_session.id

    dependency_session_ids: list[int] = []

    def tracked_db_session() -> Iterator[Session]:
        with session_factory() as session:
            dependency_session_ids.append(id(session))
            yield session

    commit_session_ids: list[int] = []
    original_commit = Session.commit

    def tracked_commit(session: Session) -> None:
        commit_session_ids.append(id(session))
        original_commit(session)

    app.dependency_overrides[get_db_session] = tracked_db_session
    monkeypatch.setattr(Session, "commit", tracked_commit)

    response = api_client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: csrf_token},
    )

    assert response.status_code == 204
    assert len(dependency_session_ids) == 1
    assert commit_session_ids == [dependency_session_ids[0], dependency_session_ids[0]]
    assert response.content == b""
    deletion_headers = response.headers.get_list("set-cookie")
    assert len(deletion_headers) == 2
    assert all("Path=/" in value and "Max-Age=0" in value for value in deletion_headers)
    assert SESSION_COOKIE_NAME not in api_client.cookies
    assert CSRF_COOKIE_NAME not in api_client.cookies
    with session_factory() as session:
        sessions = list(session.scalars(select(UserSession).order_by(UserSession.id)))
        current_session = next(item for item in sessions if item.id != other_session_id)
        other = next(item for item in sessions if item.id == other_session_id)
        assert current_session.revoked_at is not None
        assert other.revoked_at is None

    api_client.cookies.set(SESSION_COOKIE_NAME, current_token)
    assert api_client.get("/api/auth/me").status_code == 401


def test_logout_commit_failure_does_not_delete_cookies(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert login(api_client).status_code == 200
    csrf_token = api_client.cookies[CSRF_COOKIE_NAME]
    original_commit = Session.commit
    original_rollback = Session.rollback
    commit_calls = 0
    rollback_calls = 0

    def fail_second_commit(session: Session) -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise SQLAlchemyError("fictional database failure")
        original_commit(session)

    def track_rollback(session: Session) -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback(session)

    monkeypatch.setattr(Session, "commit", fail_second_commit)
    monkeypatch.setattr(Session, "rollback", track_rollback)

    response = api_client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == 500
    assert response.json() == {"detail": "ログアウト処理に失敗しました。"}
    assert rollback_calls == 1
    assert response.headers.get_list("set-cookie") == []
    assert SESSION_COOKIE_NAME in api_client.cookies
    assert CSRF_COOKIE_NAME in api_client.cookies
    with session_factory() as session:
        stored_session = session.scalar(select(UserSession))
        assert stored_session is not None
        assert stored_session.revoked_at is None
