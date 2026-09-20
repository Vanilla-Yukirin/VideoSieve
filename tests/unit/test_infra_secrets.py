from __future__ import annotations

import pytest

from infra import SecretCipherError, decrypt_secret, encrypt_secret


def test_secret_cipher_encrypts_and_rejects_wrong_root_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "root-key-one")
    encrypted = encrypt_secret("provider-secret")

    assert "provider-secret" not in encrypted
    assert decrypt_secret(encrypted) == "provider-secret"

    monkeypatch.setenv("APP_SECRET_KEY", "root-key-two")
    with pytest.raises(SecretCipherError, match="does not match"):
        decrypt_secret(encrypted)
