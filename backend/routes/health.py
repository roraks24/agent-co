import logging
from typing import Optional
from fastapi import APIRouter
from sqlalchemy import text

from backend import __version__
from backend.core.database import engine
from backend.models.schemas import HealthResponse, ReadyResponse
from backend.rag import vector_store as vector_store_module
from backend.rag.embeddings import embedding_model
from backend.services.reranker import reranker


logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Health & Readiness"]
)


@router.get("/health/", response_model=HealthResponse)
def health_check():
    """
    Liveness probe: returns immediate 200 OK if service process is alive.
    Does not perform AI inference.
    """
    return HealthResponse(status="healthy", version=__version__)


@router.get("/ready/", response_model=ReadyResponse)
def readiness_check():
    """
    Readiness probe: checks if ML models, database, and vector store are loaded and ready.
    Explicitly distinguishes application readiness (ML models + vector store)
    from database readiness (PostgreSQL connectivity).
    """
    stats = vector_store_module.get_vector_store_stats()
    models_ready = (embedding_model is not None) and (reranker is not None)
    vector_store_ready = stats.get("initialized", False)
    app_ready = models_ready and vector_store_ready

    db_ready = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ready = True
    except Exception as e:
        logger.warning("Database connectivity check failed during readiness probe: %s", e)

    if app_ready and db_ready:
        status_value = "ready"
    elif app_ready and not db_ready:
        status_value = "degraded"
    else:
        status_value = "initializing"

    return ReadyResponse(
        status=status_value,
        models_loaded=models_ready,
        vector_store_initialized=vector_store_ready,
        database_connected=db_ready,
        documents_indexed=stats.get("files_found", 0),
        chunks_indexed=stats.get("chunks_indexed", 0),
        details={
            "application_ready": app_ready,
            "database_connected": db_ready,
            "files_found": stats.get("files_found", 0),
            "file_names": stats.get("file_names", []),
            "init_duration_seconds": round(stats.get("init_duration_seconds", 0.0), 3)
        }
    )