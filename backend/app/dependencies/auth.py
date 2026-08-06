from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.models import User, UserSession
from app.security.session import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    csrf_tokens_match,
    hash_session_token,
)
from app.utilities.datetime import utc_now


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証できませんでした。",
    )


def csrf_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF検証に失敗しました。",
    )


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: UserSession
    db_session: Session


def get_authenticated_session(
    db_session: Annotated[Session, Depends(get_db_session)],
    raw_session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthenticatedSession:
    if raw_session_token is None:
        raise authentication_error()

    now = utc_now()
    try:
        result = db_session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_session_token(raw_session_token))
        ).one_or_none()
        if result is None:
            raise authentication_error()

        user_session, user = result
        if (
            user_session.revoked_at is not None
            or user_session.expires_at <= now
            or not user.is_active
        ):
            raise authentication_error()

        user_session.last_seen_at = now
        db_session.commit()
        return AuthenticatedSession(
            user=user,
            session=user_session,
            db_session=db_session,
        )
    except HTTPException:
        db_session.rollback()
        raise
    except SQLAlchemyError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="認証処理に失敗しました。",
        ) from error


def require_csrf(
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> AuthenticatedSession:
    if (
        csrf_cookie is None
        or csrf_header is None
        or not csrf_tokens_match(csrf_cookie, csrf_header)
    ):
        raise csrf_error()
    return authenticated
