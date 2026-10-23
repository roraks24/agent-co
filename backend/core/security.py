"""Compatibility shim for backend.core.security."""

from agent.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

__all__ = [
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "JWT_ALGORITHM",
    "JWT_SECRET_KEY",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
