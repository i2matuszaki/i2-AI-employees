import hashlib
import hmac
import secrets

SESSION_COOKIE_NAME = "meeting_ai_session"
CSRF_COOKIE_NAME = "meeting_ai_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if len(token_hash) != 64:
        raise RuntimeError("セッショントークンのハッシュ生成に失敗しました。")
    return token_hash


def csrf_tokens_match(cookie_token: str, header_token: str) -> bool:
    return hmac.compare_digest(cookie_token, header_token)
