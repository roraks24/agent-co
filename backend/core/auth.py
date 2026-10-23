"""Compatibility shim for backend.core.auth."""

from agent.core.auth import (
    get_current_user,
    get_optional_current_user,
    security_scheme,
)

__all__ = [
    "get_current_user",
    "get_optional_current_user",
    "security_scheme",
]
