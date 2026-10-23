"""Compatibility shim for backend.core.config."""

import os
from pathlib import Path
from dotenv import load_dotenv
from agent.db.config import DATABASE_URL, BASE_DIR

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "rorak-ai-v2.6-insecure-default-secret-key-change-in-prod")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))
WORKSPACES_DIR = Path(os.getenv("WORKSPACES_DIR", str(BASE_DIR / "workspaces"))).resolve()

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "10"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "3"))
CONTEXT_WINDOW_SIZE = int(os.getenv("CONTEXT_WINDOW_SIZE", "10"))
MEMORY_WINDOW_SIZE = int(os.getenv("MEMORY_WINDOW_SIZE", "5"))
DOCUMENTS_DIR = BASE_DIR / "documents"
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

__all__ = [
    "BASE_DIR",
    "DATABASE_URL",
    "GROQ_API_KEY",
    "TAVILY_API_KEY",
    "JWT_SECRET_KEY",
    "ENVIRONMENT",
    "JWT_ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "WORKSPACES_DIR",
    "GROQ_MODEL",
    "EMBEDDING_MODEL",
    "RERANKER_MODEL",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "RETRIEVAL_K",
    "RERANK_TOP_K",
    "CONTEXT_WINDOW_SIZE",
    "MEMORY_WINDOW_SIZE",
    "DOCUMENTS_DIR",
    "MAX_UPLOAD_SIZE_BYTES",
    "ALLOWED_EXTENSIONS",
    "LOG_LEVEL",
]
