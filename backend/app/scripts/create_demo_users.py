import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.security.password import hash_password, validate_password
from app.utilities.email import normalize_email


@dataclass(frozen=True)
class DemoUserDefinition:
    email: str
    display_name: str
    role: UserRole
    password_environment_variable: str


@dataclass(frozen=True)
class DemoUserCreationResult:
    created_count: int
    skipped_count: int


DEMO_USERS: tuple[DemoUserDefinition, ...] = (
    DemoUserDefinition(
        email="user@demo.local",
        display_name="デモ一般利用者",
        role=UserRole.USER,
        password_environment_variable="DEMO_USER_PASSWORD",
    ),
    DemoUserDefinition(
        email="approver@demo.local",
        display_name="デモ承認者",
        role=UserRole.APPROVER,
        password_environment_variable="DEMO_APPROVER_PASSWORD",
    ),
    DemoUserDefinition(
        email="admin@demo.local",
        display_name="デモ管理者",
        role=UserRole.ADMIN,
        password_environment_variable="DEMO_ADMIN_PASSWORD",
    ),
)


def read_and_validate_demo_passwords(
    environment: Mapping[str, str],
    definitions: Sequence[DemoUserDefinition] = DEMO_USERS,
) -> dict[str, str]:
    """DBへ接続する前に、必要なデモパスワードをすべて検証する。"""
    passwords: dict[str, str] = {}
    invalid_variables: list[str] = []

    for definition in definitions:
        variable_name = definition.password_environment_variable
        password = environment.get(variable_name, "")
        try:
            validate_password(password)
        except ValueError:
            invalid_variables.append(variable_name)
        else:
            passwords[variable_name] = password

    if invalid_variables:
        joined_names = ", ".join(invalid_variables)
        raise ValueError(f"デモ利用者用パスワードを正しく設定してください: {joined_names}")

    return passwords


def create_demo_users(
    session: Session,
    passwords: Mapping[str, str],
    definitions: Sequence[DemoUserDefinition] = DEMO_USERS,
) -> DemoUserCreationResult:
    """存在しないデモ利用者だけを一つのトランザクションで作成する。"""
    for definition in definitions:
        validate_password(passwords.get(definition.password_environment_variable, ""))

    created_count = 0
    skipped_count = 0

    try:
        for definition in definitions:
            email = normalize_email(definition.email)
            existing_user = session.scalar(select(User).where(User.email == email))
            if existing_user is not None:
                skipped_count += 1
                continue

            session.add(
                User(
                    email=email,
                    display_name=definition.display_name,
                    role=definition.role,
                    password_hash=hash_password(
                        passwords[definition.password_environment_variable]
                    ),
                )
            )
            created_count += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    return DemoUserCreationResult(
        created_count=created_count,
        skipped_count=skipped_count,
    )


def main() -> int:
    try:
        passwords = read_and_validate_demo_passwords(os.environ)
    except ValueError as error:
        print(f"エラー: {error}")
        return 1

    from app.database.session import SessionLocal

    with SessionLocal() as session:
        result = create_demo_users(session, passwords)

    print(f"作成件数: {result.created_count}, スキップ件数: {result.skipped_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
