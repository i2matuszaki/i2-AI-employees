from datetime import timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.session import get_db_session
from app.dependencies.auth import (
    AuthenticatedSession,
    authentication_error,
    get_authenticated_session,
    require_csrf,
)
from app.models import User, UserSession
from app.schemas.auth import AuthenticatedUserResponse, CurrentUserResponse, LoginRequest
from app.security.password import verify_password, verify_password_against_dummy
from app.security.session import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    generate_csrf_token,
    generate_session_token,
    hash_session_token,
)
from app.utilities.datetime import utc_now

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_response(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user=AuthenticatedUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=cast(Literal["user", "approver", "admin"], user.role),
        )
    )


def _set_auth_cookies(
    response: Response,
    raw_session_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    common = {
        "max_age": settings.session_max_age_seconds,
        "path": "/",
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_token,
        httponly=True,
        **common,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        **common,
    )


def _delete_auth_cookies(response: Response, settings: Settings) -> None:
    common = {
        "path": "/",
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
    }
    response.delete_cookie(key=SESSION_COOKIE_NAME, httponly=True, **common)
    response.delete_cookie(key=CSRF_COOKIE_NAME, httponly=False, **common)


@router.post("/login", response_model=CurrentUserResponse)
def login(
    request: LoginRequest,
    response: Response,
    db_session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUserResponse:
    try:
        user = db_session.scalar(select(User).where(User.email == request.email))
    except SQLAlchemyError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="認証処理に失敗しました。",
        ) from error
    if user is None:
        verify_password_against_dummy(request.password)
        raise authentication_error()

    password_matches = verify_password(request.password, user.password_hash)
    if not password_matches or not user.is_active:
        raise authentication_error()

    raw_session_token = generate_session_token()
    csrf_token = generate_csrf_token()
    now = utc_now()
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_session_token),
        expires_at=now + timedelta(hours=settings.session_lifetime_hours),
        last_seen_at=now,
    )
    try:
        db_session.add(user_session)
        db_session.flush()
        db_session.commit()
    except SQLAlchemyError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="認証処理に失敗しました。",
        ) from error

    _set_auth_cookies(response, raw_session_token, csrf_token, settings)
    return _user_response(user)


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> CurrentUserResponse:
    return _user_response(authenticated.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authenticated: Annotated[AuthenticatedSession, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    db_session = authenticated.db_session
    try:
        authenticated.session.revoked_at = utc_now()
        db_session.commit()
    except SQLAlchemyError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ログアウト処理に失敗しました。",
        ) from error

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _delete_auth_cookies(response, settings)
    return response
