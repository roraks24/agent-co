"""Compatibility shim for backend.core.database."""

from agent.db.database import (
    Base,
    SessionLocal,
    build_engine,
    engine,
    get_db,
    get_db_context,
    getdb,
)

__all__ = [
    "Base",
    "engine",
    "build_engine",
    "SessionLocal",
    "get_db",
    "get_db_context",
    "getdb",
]
