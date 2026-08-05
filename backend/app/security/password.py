from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_password_hash = PasswordHash.recommended()


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
