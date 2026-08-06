from app.security.session import (
    csrf_tokens_match,
    generate_csrf_token,
    generate_session_token,
    hash_session_token,
)


def test_session_token_is_random_and_hash_is_sha256_hex() -> None:
    first = generate_session_token()
    second = generate_session_token()
    token_hash = hash_session_token(first)

    assert first != second
    assert first != token_hash
    assert len(token_hash) == 64
    assert all(character in "0123456789abcdef" for character in token_hash)


def test_csrf_token_comparison() -> None:
    csrf_token = generate_csrf_token()

    assert csrf_tokens_match(csrf_token, csrf_token) is True
    assert csrf_tokens_match(csrf_token, generate_csrf_token()) is False
