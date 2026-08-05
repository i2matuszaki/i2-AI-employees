from datetime import UTC, datetime, timedelta, timezone
from importlib import import_module
from uuid import UUID

import pytest
from sqlalchemy import Engine, delete, event, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import User, UserSession
from app.security.password import hash_password


def make_user(**overrides: object) -> User:
    values: dict[str, object] = {
        "email": "user@example.test",
        "display_name": "テスト利用者",
        "role": "user",
        "password_hash": hash_password("fictional-password"),
    }
    values.update(overrides)
    return User(**values)


def test_user_gets_uuid_v4_and_normalized_email(db_session: Session) -> None:
    user = make_user(email="  User@Example.Test  ")
    db_session.add(user)
    db_session.commit()

    parsed_id = UUID(user.id)
    assert len(user.id) == 36
    assert parsed_id.version == 4
    assert str(parsed_id) == user.id
    assert user.email == "user@example.test"


def test_duplicate_email_is_rejected(db_session: Session) -> None:
    db_session.add_all(
        [
            make_user(email="same@example.test"),
            make_user(email=" SAME@EXAMPLE.TEST "),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    ("email", "display_name", "role"),
    [
        ("UPPER@example.test", "利用者", "user"),
        (f"{'a' * 243}@example.test", "利用者", "user"),
        ("direct@example.test", "   ", "user"),
        ("direct@example.test", "利用者", "owner"),
    ],
)
def test_database_check_constraints_reject_invalid_user_values(
    db_session: Session,
    email: str,
    display_name: str,
    role: str,
) -> None:
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    statement = text(
        """
        INSERT INTO users
            (id, email, display_name, role, password_hash, is_active, created_at, updated_at)
        VALUES
            (:id, :email, :display_name, :role, :password_hash, 1, :created_at, :updated_at)
        """
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            statement,
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "email": email,
                "display_name": display_name,
                "role": role,
                "password_hash": "stored-hash",
                "created_at": now,
                "updated_at": now,
            },
        )


def test_undefined_role_is_rejected_by_orm() -> None:
    with pytest.raises(ValueError):
        make_user(role="owner")


def test_sqlite_foreign_keys_are_enabled(test_engine: Engine) -> None:
    with test_engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


def test_nonexistent_session_user_is_rejected(db_session: Session) -> None:
    db_session.add(
        UserSession(
            user_id="00000000-0000-4000-8000-000000000099",
            token_hash="nonexistent-user-token-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_delete_is_restricted_when_session_exists(db_session: Session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash="delete-restrict-token-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(delete(User).where(User.id == user.id))
        db_session.commit()


def test_duplicate_token_hash_is_rejected(db_session: Session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    expires_at = datetime.now(UTC) + timedelta(hours=8)
    db_session.add_all(
        [
            UserSession(user_id=user.id, token_hash="same-token-hash", expires_at=expires_at),
            UserSession(user_id=user.id, token_hash="same-token-hash", expires_at=expires_at),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_utc_datetime_is_stored_as_iso_string_and_loaded_as_utc(
    db_session: Session,
) -> None:
    source_timezone = timezone(timedelta(hours=9))
    expires_at = datetime(2026, 8, 5, 21, 34, 56, 123456, tzinfo=source_timezone)
    user = make_user()
    db_session.add(user)
    db_session.flush()
    user_session = UserSession(
        user_id=user.id,
        token_hash="utc-token-hash",
        expires_at=expires_at,
    )
    db_session.add(user_session)
    db_session.commit()

    stored_value = db_session.execute(
        text("SELECT expires_at FROM user_sessions WHERE id = :id"),
        {"id": user_session.id},
    ).scalar_one()
    loaded_value = db_session.scalar(
        select(UserSession.expires_at).where(UserSession.id == user_session.id)
    )

    assert stored_value == "2026-08-05T12:34:56.123456+00:00"
    assert loaded_value == datetime(2026, 8, 5, 12, 34, 56, 123456, tzinfo=UTC)
    assert loaded_value is not None
    assert loaded_value.tzinfo is UTC


def test_naive_datetime_is_rejected(db_session: Session) -> None:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash="naive-datetime-token-hash",
            expires_at=datetime(2026, 8, 5, 12, 0),  # noqa: DTZ001
        )
    )

    with pytest.raises(StatementError):
        db_session.commit()


def test_non_sqlite_engine_does_not_register_sqlite_event(monkeypatch) -> None:
    engine_module = import_module("app.database.engine")

    sentinel_engine = object()
    listened_engines: list[object] = []
    monkeypatch.setattr(engine_module, "create_engine", lambda *args, **kwargs: sentinel_engine)
    monkeypatch.setattr(
        event,
        "listen",
        lambda target, *args, **kwargs: listened_engines.append(target),
    )

    result = engine_module.create_database_engine("postgresql://user:password@localhost/test")

    assert result is sentinel_engine
    assert listened_engines == []
