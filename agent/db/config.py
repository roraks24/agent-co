"""Database configuration and environment variable loading."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Base repository root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env if present
load_dotenv(BASE_DIR / ".env")


def normalize_database_url(url: str | None) -> str:
    """Normalize database connection URL for SQLAlchemy 2.x and drivers.
    
    Handles Heroku/Render/Supabase/Neon style postgres:// and bare postgresql://
    by mapping to postgresql+psycopg:// driver if no driver is explicitly qualified.
    Falls back to a safe SQLite development database if no URL is provided.
    """
    raw_url = (url or "").strip()
    if not raw_url:
        fallback_db = BASE_DIR / "rorak_dev.db"
        logger.warning(
            "DATABASE_URL is not set. Falling back to local SQLite: sqlite:///%s",
            fallback_db.as_posix(),
        )
        return f"sqlite:///{fallback_db.as_posix()}"

    # Replace postgres:// with postgresql+psycopg://
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)

    # If bare postgresql:// without driver specified, use postgresql+psycopg://
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return raw_url


RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = normalize_database_url(RAW_DATABASE_URL)

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
DB_ECHO = os.getenv("DB_ECHO", "false").lower() in {"1", "true", "yes"}
