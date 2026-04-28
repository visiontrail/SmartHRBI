from __future__ import annotations

from apps.api.users import hash_password, verify_password


def test_hash_and_verify_password() -> None:
    plain = "MySecurePassword123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_wrong_password_fails() -> None:
    hashed = hash_password("correctpass")
    assert not verify_password("wrongpass", hashed)


def test_hash_is_unique() -> None:
    pw = "samepassword"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2  # bcrypt salts are random


def test_mask_email() -> None:
    from apps.api.users import _mask_email

    assert _mask_email("alice@example.com") == "al***@example.com"
    assert _mask_email("a@example.com") == "a***@example.com"
    assert _mask_email("ab@example.com") == "ab***@example.com"
    assert _mask_email("notanemail") == "notanemail"
