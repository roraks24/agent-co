"""Database engine, session factory, and table initialisation.

Usage
-----
    from agent.database import get_db, init_db

    # At application startup (e.g. in a FastAPI lifespan handler):
    init_db()

    # In a request handler:
    async def some_endpoint(db: Session = Depends(get_db)):
        ...

Environment Variables
---------------------
DATABASE_URL
    A SQLAlchemy-compatible connection string.
    Defaults to a local SQLite file for development.

    Examples:
        sqlite:///./charito.db
        postgresql+psycopg2://user:pass@host:5432/charito
        postgresql+asyncpg://user:pass@host:5432/charito   (async)
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agent.models import Base

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./charito.db")

# For SQLite, check_same_thread must be False when used with FastAPI.
_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=os.getenv("DB_ECHO", "").lower() in ("1", "true", "yes"),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables that do not yet exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
