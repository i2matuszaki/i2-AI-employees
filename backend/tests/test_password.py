import pytest

from app.security.password import hash_password, verify_password


def test_password_is_hashed_with_argon2_and_can_be_verified() -> None:
    password = "fictional-password"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2")
    assert verify_password(password, password_hash) is True
    assert verify_password("different-password", password_hash) is False


@pytest.mark.parametrize("password", ["", "1234567", "x" * 129])
def test_hash_password_rejects_invalid_length_without_exposing_value(password: str) -> None:
    with pytest.raises(ValueError) as error:
        hash_password(password)

    assert password not in str(error.value) or password == ""


def test_verify_password_safely_rejects_invalid_hash() -> None:
    assert verify_password("fictional-password", "not-a-valid-hash") is False
    assert verify_password("", "not-a-valid-hash") is False
