"""Authenticated encryption helpers for local persisted secrets."""

from __future__ import annotations

import os
from base64 import urlsafe_b64encode
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken


class SecretCipherError(RuntimeError):
    """Raised when the root key is absent or ciphertext cannot be decrypted."""


def _fernet() -> Fernet:
    app_secret = os.getenv("APP_SECRET_KEY", "").strip()
    if not app_secret:
        raise SecretCipherError("APP_SECRET_KEY is required for encrypted secret storage")
    digest = sha256(app_secret.encode("utf-8")).digest()
    return Fernet(urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    """Encrypt one non-empty secret with the deployment root key."""

    if not value:
        raise SecretCipherError("secret value cannot be empty")
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """Decrypt one secret or fail without exposing its value."""

    try:
        decoded = _fernet().decrypt(value.encode("utf-8"))
    except InvalidToken as exc:
        raise SecretCipherError(
            "APP_SECRET_KEY does not match stored secret encryption"
        ) from exc
    return decoded.decode("utf-8")
