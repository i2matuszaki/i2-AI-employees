import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utilities.email import normalize_email

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_login_email(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = normalize_email(value)
            if not normalized:
                raise ValueError("メールアドレスを入力してください。")
            if len(normalized) > 254:
                raise ValueError("メールアドレスは254文字以内で指定してください。")
            if EMAIL_PATTERN.fullmatch(normalized) is None:
                raise ValueError("メールアドレスの形式が正しくありません。")
            return normalized
        return value


class AuthenticatedUserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["user", "approver", "admin"]


class CurrentUserResponse(BaseModel):
    user: AuthenticatedUserResponse
