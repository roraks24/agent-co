"""Cryptographic encryption and decryption for sensitive API keys stored at rest."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    HAS_CRYPTOGRAPHY = False


def _get_encryption_key() -> bytes:
    """Derive 256-bit AES key from environment secret or application identifier."""
    raw_secret = os.getenv("API_KEY_ENCRYPTION_SECRET", "agent-co-default-local-encryption-secret-v1")
    return hashlib.sha256(raw_secret.encode("utf-8")).digest()


def encrypt_secret(plain_text: str) -> str:
    """Encrypt plain text API key using AES-256-GCM and return encoded string with 'enc:' prefix."""
    if not plain_text or not plain_text.strip():
        return ""
    clean = plain_text.strip()

    # If it's already an env reference or encrypted, don't re-encrypt
    if clean.startswith("env:") or clean.startswith("enc:"):
        return clean

    key = _get_encryption_key()
    if HAS_CRYPTOGRAPHY:
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, clean.encode("utf-8"), None)
        payload = nonce + ciphertext
        return "enc:" + base64.b64encode(payload).decode("utf-8")
    else:  # pragma: no cover - fallback standard library XOR/hash stream if cryptography absent
        nonce = os.urandom(12)
        stream = hashlib.sha256(key + nonce).digest()
        cipher_bytes = bytes([b ^ stream[i % len(stream)] for i, b in enumerate(clean.encode("utf-8"))])
        return "enc:" + base64.b64encode(nonce + cipher_bytes).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt ciphertext with 'enc:' prefix or resolve 'env:VAR' reference."""
    if not cipher_text or not cipher_text.strip():
        return ""
    clean = cipher_text.strip()

    # Resolve environment variable reference
    if clean.startswith("env:"):
        env_var = clean[4:].strip()
        return os.getenv(env_var, "").strip()

    # If not encrypted, return as is (support legacy/unencrypted migration)
    if not clean.startswith("enc:"):
        return clean

    encoded = clean[4:].strip()
    raw = base64.b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]
    key = _get_encryption_key()

    if HAS_CRYPTOGRAPHY:
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode("utf-8")
    else:  # pragma: no cover
        stream = hashlib.sha256(key + nonce).digest()
        plain_bytes = bytes([b ^ stream[i % len(stream)] for i, b in enumerate(ciphertext)])
        return plain_bytes.decode("utf-8")


def mask_secret(secret: Optional[str]) -> str:
    """Return safe masked representation for UI display, e.g. 'gsk_...4a8e' or '***'."""
    if not secret or not secret.strip():
        return ""
    clean = secret.strip()
    if clean.startswith("env:"):
        return f"env({clean[4:]})"
    if len(clean) <= 8:
        return "****"
    return f"{clean[:4]}...{clean[-4:]}"
