from __future__ import annotations

import base64
import hashlib
import hmac
import os
from itertools import count

from .exceptions import CryptoError


def generate_secret_key() -> str:
    """Return a high-entropy secret suitable for EMAIL_ASSISTANT_SECRET_KEY."""

    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


class TokenCipher:
    """Encrypt and decrypt OAuth tokens at the storage boundary.

    When `cryptography` is installed, this uses Fernet, which wraps AES-128-CBC
    plus HMAC authentication. If the package is missing, the class falls back to
    a deterministic development-only authenticated stream cipher so tests and
    demos can still run. Production mode refuses that fallback.
    """

    _DEV_PREFIX = "dev.v1."

    def __init__(self, secret_key: str, environment: str = "development", backend: str = "auto") -> None:
        if not secret_key or len(secret_key) < 16:
            raise CryptoError("EMAIL_ASSISTANT_SECRET_KEY must be at least 16 characters.")

        self.environment = environment
        self.backend = backend
        self._fernet = None
        self._dev_key = hashlib.sha256(secret_key.encode("utf-8")).digest()

        if backend in {"auto", "fernet"}:
            try:
                from cryptography.fernet import Fernet

                self._fernet = Fernet(_normalize_fernet_key(secret_key))
                self.backend = "fernet"
                return
            except ImportError:
                if backend == "fernet":
                    raise CryptoError("cryptography is required for the Fernet backend.") from None

        self.backend = "dev"
        if environment == "production":
            raise CryptoError("Production deployments require cryptography and the Fernet backend.")

    @property
    def production_safe(self) -> bool:
        return self.backend == "fernet"

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is not None:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

        nonce = os.urandom(16)
        data = plaintext.encode("utf-8")
        ciphertext = _xor_bytes(data, _keystream(self._dev_key, nonce, len(data)))
        tag = hmac.new(self._dev_key, nonce + ciphertext, hashlib.sha256).digest()
        payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")
        return f"{self._DEV_PREFIX}{payload}"

    def decrypt(self, token: str) -> str:
        if token.startswith(self._DEV_PREFIX):
            return self._decrypt_dev(token)
        if self._fernet is None:
            raise CryptoError("Cannot decrypt Fernet token without the cryptography package.")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as exc:  # Fernet raises several validation exceptions.
            raise CryptoError("Encrypted token could not be decrypted.") from exc

    def _decrypt_dev(self, token: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(token.removeprefix(self._DEV_PREFIX).encode("ascii"))
        except Exception as exc:
            raise CryptoError("Development token payload is not valid base64.") from exc
        if len(raw) < 48:
            raise CryptoError("Development token payload is too short.")

        nonce = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]
        expected = hmac.new(self._dev_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise CryptoError("Encrypted token failed integrity validation.")

        plaintext = _xor_bytes(ciphertext, _keystream(self._dev_key, nonce, len(ciphertext)))
        return plaintext.decode("utf-8")


def _normalize_fernet_key(secret_key: str) -> bytes:
    candidate = secret_key.encode("ascii", errors="ignore")
    try:
        decoded = base64.urlsafe_b64decode(candidate)
        if len(decoded) == 32:
            return candidate
    except Exception:
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    for index in count():
        if sum(len(chunk) for chunk in chunks) >= length:
            break
        counter_bytes = index.to_bytes(4, "big")
        chunks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
    return b"".join(chunks)[:length]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right))
