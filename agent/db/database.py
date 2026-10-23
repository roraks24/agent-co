"""SQLAlchemy 2.0 database engine, session factory, and lifecycle management."""

from collections.abc import Generator
from contextlib import contextmanager
import logging
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from agent.db.config import (
    DATABASE_URL,
    DB_ECHO,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    normalize_database_url,
)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


def build_engine(url: str | None = None) -> Engine:
    """Build and configure a SQLAlchemy 2.x engine with connection pooling."""
    db_url = normalize_database_url(url) if url else DATABASE_URL
    is_sqlite = db_url.startswith("sqlite")

    engine_kwargs: dict[str, Any] = {
        "echo": DB_ECHO,
    }

    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in db_url:
            engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["poolclass"] = NullPool
    else:
        # PostgreSQL / MySQL connection pool configuration
        engine_kwargs["poolclass"] = QueuePool
        engine_kwargs["pool_size"] = DB_POOL_SIZE
        engine_kwargs["max_overflow"] = DB_MAX_OVERFLOW
        engine_kwargs["pool_timeout"] = DB_POOL_TIMEOUT
        engine_kwargs["pool_recycle"] = DB_POOL_RECYCLE
        engine_kwargs["pool_pre_ping"] = True

    return create_engine(db_url, **engine_kwargs)


# Application-level engine instance
engine: Engine = build_engine()

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI request-scoped database session dependency.
    
    Guarantees session closure and automated rollback upon uncaught exceptions.
    Prevents connection and transaction leaks under concurrent workloads.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone scripts, background tasks, and agent runs."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Compatibility aliases for legacy Rorak AI code
getdb = get_db
