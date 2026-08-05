from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.scripts.create_demo_users import (
    create_demo_users,
    read_and_validate_demo_passwords,
)
from app.security.password import hash_password, verify_password


def demo_passwords() -> dict[str, str]:
    return {
        "DEMO_USER_PASSWORD": "fictional-user-password",
        "DEMO_APPROVER_PASSWORD": "fictional-approver-password",
        "DEMO_ADMIN_PASSWORD": "fictional-admin-password",
    }


def test_create_demo_users_creates_three_hashed_users(db_session: Session) -> None:
    passwords = demo_passwords()

    result = create_demo_users(db_session, passwords)
    users = list(db_session.scalars(select(User).order_by(User.email)))

    assert result.created_count == 3
    assert result.skipped_count == 0
    assert len(users) == 3
    assert {user.email for user in users} == {
        "user@demo.local",
        "approver@demo.local",
        "admin@demo.local",
    }
    for user in users:
        plain_password = passwords[f"DEMO_{user.role.upper()}_PASSWORD"]
        assert user.password_hash != plain_password
        assert verify_password(plain_password, user.password_hash)


def test_create_demo_users_is_idempotent(db_session: Session) -> None:
    passwords = demo_passwords()

    first_result = create_demo_users(db_session, passwords)
    second_result = create_demo_users(db_session, passwords)

    assert first_result.created_count == 3
    assert second_result.created_count == 0
    assert second_result.skipped_count == 3
    assert db_session.scalar(select(func.count()).select_from(User)) == 3


def test_existing_demo_user_is_not_modified(db_session: Session) -> None:
    original_hash = hash_password("original-fictional-password")
    existing_user = User(
        email="user@demo.local",
        display_name="既存表示名",
        role="admin",
        password_hash=original_hash,
        is_active=False,
    )
    db_session.add(existing_user)
    db_session.commit()

    result = create_demo_users(db_session, demo_passwords())
    db_session.refresh(existing_user)

    assert result.created_count == 2
    assert result.skipped_count == 1
    assert existing_user.display_name == "既存表示名"
    assert existing_user.role == "admin"
    assert existing_user.password_hash == original_hash
    assert existing_user.is_active is False


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"DEMO_USER_PASSWORD": "short"},
        {
            "DEMO_USER_PASSWORD": "fictional-user-password",
            "DEMO_APPROVER_PASSWORD": "fictional-approver-password",
        },
    ],
)
def test_invalid_environment_does_not_change_database(
    db_session: Session,
    environment: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        passwords = read_and_validate_demo_passwords(environment)
        create_demo_users(db_session, passwords)

    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_tests_do_not_use_development_database(test_engine) -> None:
    database_path = Path(test_engine.url.database or "").resolve()
    development_path = (Path(__file__).parents[1] / "data" / "meeting_ai.db").resolve()

    assert database_path != development_path
    assert "pytest-" in str(database_path)
