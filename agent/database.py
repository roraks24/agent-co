"""Database engine, session factory, connection pooling, and lifecycle helpers.

Usage
-----
    from agent.database import get_db, init_db, get_db_context

    # Dependency in FastAPI routes:
    @app.get("/items")
    def list_items(db: Session = Depends(get_db)):
        ...

    # Context manager for background tasks / streaming:
    with get_db_context() as db:
        run = db.query(WorkflowRun).filter(...).first()

Environment Variables
---------------------
DATABASE_URL
    SQLAlchemy-compatible connection string.
    Defaults to SQLite for lightweight local runs when Postgres is absent.
    Production / Docker: postgresql+psycopg2://postgres:postgres@localhost:5432/charito
DB_POOL_SIZE
    Size of persistent connection pool (PostgreSQL). Default: 10
DB_MAX_OVERFLOW
    Maximum overflow connections beyond pool size. Default: 20
DB_ECHO
    Log all generated SQL statements. Default: false
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./charito.db")
DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_ECHO: bool = os.getenv("DB_ECHO", "").lower() in ("1", "true", "yes")

# Engine options
engine_kwargs: dict = {
    "echo": DB_ECHO,
}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL / other RDBMS with connection pooling
    engine_kwargs.update(
        {
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
            "pool_pre_ping": True,
            "pool_recycle": 1800,  # recycle connections every 30 minutes
        }
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create all tables that do not yet exist (useful for test/dev)."""
    from agent.models import Base  # lazy import to avoid circular dependency
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for non-route database interactions (streaming/workers)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
