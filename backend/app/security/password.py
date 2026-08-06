import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_password_hash = PasswordHash.recommended()
_dummy_password_hash = _password_hash.hash(secrets.token_urlsafe(32))


def validate_password(password: str) -> None:
    """パスワード長を検証する。"""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("パスワードは8文字以上128文字以下で指定してください。")


def hash_password(password: str) -> str:
    """パスワードをArgon2でハッシュ化する。"""
    validate_password(password)
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """平文パスワードと保存済みハッシュを安全に照合する。"""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        return False
    try:
        return _password_hash.verify(password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def verify_password_against_dummy(password: str) -> None:
    """利用者が存在しない場合もArgon2検証相当を一度実行する。"""
    verify_password(password, _dummy_password_hash)
