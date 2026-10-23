import logging
import threading
import time
from pathlib import Path
import shutil
from typing import Optional, Dict, Any

from langchain_community.vectorstores import FAISS

from backend.rag.embeddings import embedding_model
from backend.core.config import DOCUMENTS_DIR


logger = logging.getLogger(__name__)


# ============================================================
# GLOBAL VECTOR STORE STATE
# ============================================================

vector_store: Optional[FAISS] = None

_lock = threading.Lock()

FAISS_INDEX_DIR = DOCUMENTS_DIR / ".faiss_index"


# ============================================================
# VECTOR STORE STATS
# ============================================================

_stats: Dict[str, Any] = {
    "files_found": 0,
    "file_names": [],
    "chunks_indexed": 0,
    "initialized": False,
    "init_duration_seconds": 0.0,
}


def get_vector_store_stats() -> Dict[str, Any]:
    """Return runtime vector store metadata."""

    return dict(_stats)


# ============================================================
# BUILD VECTOR STORE
# ============================================================

def build_vector_store() -> Optional[FAISS]:
    """
    Build or rebuild the FAISS vector store from PDF files
    found in DOCUMENTS_DIR.
    """

    global vector_store, _stats

    t0 = time.perf_counter()

    logger.info(
        "Initializing vector store from document directory: %s",
        DOCUMENTS_DIR.resolve(),
    )

    if not DOCUMENTS_DIR.exists():
        logger.info(
            "Documents directory does not exist at %s. "
            "Starting with empty vector store.",
            DOCUMENTS_DIR.resolve(),
        )

        with _lock:
            vector_store = None

            _stats.update(
                {
                    "files_found": 0,
                    "file_names": [],
                    "chunks_indexed": 0,
                    "initialized": True,
                    "init_duration_seconds": (
                        time.perf_counter() - t0
                    ),
                }
            )

        return vector_store

    # Find all supported documents recursively.
    supported_patterns = ["*.pdf", "*.docx", "*.txt", "*.md", "*.csv"]
    doc_files = []
    for pattern in supported_patterns:
        doc_files.extend(list(DOCUMENTS_DIR.rglob(pattern)))

    doc_names = [
        file_path.name
        for file_path in doc_files
    ]

    logger.info(
        "Discovered %d supported document file(s) in %s: %s",
        len(doc_files),
        DOCUMENTS_DIR.resolve(),
        doc_names,
    )

    if not doc_files:
        logger.info(
            "No supported document files found in %s. "
            "Starting with empty vector store.",
            DOCUMENTS_DIR.resolve(),
        )

        with _lock:
            vector_store = None

            _stats.update(
                {
                    "files_found": 0,
                    "file_names": [],
                    "chunks_indexed": 0,
                    "initialized": True,
                    "init_duration_seconds": (
                        time.perf_counter() - t0
                    ),
                }
            )

        return vector_store

    # Local import avoids the ingestion/vector-store
    # circular import that existed historically.
    from backend.services.ingestion import ingest_func

    documents = []

    for file_path in doc_files:
        try:
            chunks = ingest_func(file_path)

            documents.extend(chunks)

            logger.info(
                "Ingested %s -> %d chunks created.",
                file_path.name,
                len(chunks),
            )

        except Exception:
            logger.exception(
                "Failed to ingest file: %s",
                file_path,
            )

    with _lock:

        if documents:

            # ----------------------------------------------------
            # Build initial vector store.
            # Stable UUID IDs prevent collisions with live additions.
            # ----------------------------------------------------
            from uuid import uuid4

            faiss_ids = [
                str(uuid4())
                for _ in range(len(documents))
            ]

            vector_store = FAISS.from_documents(
                documents=documents,
                embedding=embedding_model,
                ids=faiss_ids,
            )

            _save_index()

            duration = (
                time.perf_counter() - t0
            )

            _stats.update(
                {
                    "files_found": len(doc_files),
                    "file_names": doc_names,
                    "chunks_indexed": len(documents),
                    "initialized": True,
                    "init_duration_seconds": duration,
                }
            )

            logger.info(
                "Built vector store with %d chunks "
                "from %d files in %.2f seconds.",
                len(documents),
                len(doc_files),
                duration,
            )

        else:

            vector_store = None

            _stats.update(
                {
                    "files_found": len(doc_files),
                    "file_names": doc_names,
                    "chunks_indexed": 0,
                    "initialized": True,
                    "init_duration_seconds": (
                        time.perf_counter() - t0
                    ),
                }
            )

            logger.warning(
                "No chunks were successfully extracted "
                "from discovered document files."
            )

    return vector_store


# ============================================================
# ADD DOCUMENTS
# ============================================================

def add_documents(
    documents: list,
    ids: list[str] | None = None,
) -> None:
    """
    Add document chunks to the active FAISS vector store.

    Args:
        documents:
            LangChain Document objects to index.

        ids:
            Optional stable vector IDs.

            In V2.2 these should be the corresponding
            DocumentChunk UUIDs.

    Raises:
        ValueError:
            If the number of IDs does not match the number
            of documents.
    """

    global vector_store, _stats

    if not documents:
        return

    # Validate ID count before touching FAISS.
    if ids is not None and len(ids) != len(documents):
        raise ValueError(
            "Number of IDs must match "
            "number of documents."
        )

    # Reject duplicate IDs before modifying the store.
    if ids is not None and len(ids) != len(set(ids)):
        raise ValueError(
            "Duplicate vector IDs are not allowed."
        )

    with _lock:

        if vector_store is None:

            vector_store = FAISS.from_documents(
                documents=documents,
                embedding=embedding_model,
                ids=ids,
            )

        else:

            vector_store.add_documents(
                documents=documents,
                ids=ids,
            )

        _save_index()

        _stats["chunks_indexed"] = (
            _stats.get("chunks_indexed", 0)
            + len(documents)
        )

    logger.info(
        "Added %d chunks to vector store "
        "(total indexed: %d).",
        len(documents),
        _stats["chunks_indexed"],
    )


# ============================================================
# DELETE DOCUMENT VECTORS
# ============================================================

def delete_documents_by_document_id(
    document_id: str,
) -> int:
    """
    Delete all FAISS vectors belonging to one document.

    The function looks at stored document metadata and finds
    the FAISS IDs whose metadata contains the requested
    document_id.

    Args:
        document_id:
            UUID of the document as a string.

    Returns:
        Number of vectors deleted.
    """

    global vector_store, _stats

    if vector_store is None:
        return 0

    target_document_id = str(document_id)

    with _lock:

        ids_to_delete: list[str] = []

        # index_to_docstore_id maps FAISS integer indexes
        # to the stable document-store IDs.
        for _, docstore_id in (
            vector_store.index_to_docstore_id.items()
        ):
            stored_document = (
                vector_store.docstore.search(
                    docstore_id
                )
            )

            if stored_document is None:
                continue

            metadata = (
                stored_document.metadata or {}
            )

            stored_document_id = metadata.get(
                "document_id"
            )

            if stored_document_id is None:
                continue

            if str(stored_document_id) == target_document_id:
                ids_to_delete.append(
                    docstore_id
                )

        if not ids_to_delete:
            logger.info(
                "No vectors found for document %s.",
                target_document_id,
            )

            return 0

        # Delete only the matching vectors.
        vector_store.delete(
            ids=ids_to_delete
        )

        _save_index()

        deleted_count = len(ids_to_delete)

        _stats["chunks_indexed"] = max(
            0,
            _stats.get("chunks_indexed", 0)
            - deleted_count,
        )

    logger.info(
        "Deleted %d vector(s) for document %s.",
        deleted_count,
        target_document_id,
    )

    return deleted_count


# ============================================================
# CLEAR ENTIRE VECTOR STORE
# ============================================================

def clear_vector_store() -> None:
    """
    Clear the complete FAISS vector store.

    This remains available for V1 compatibility/testing.

    V2.2 document deletion should use
    delete_documents_by_document_id() instead.
    """

    global vector_store, _stats

    with _lock:

        vector_store = None

        _stats.update(
            {
                "files_found": 0,
                "file_names": [],
                "chunks_indexed": 0,
                "initialized": True,
                "init_duration_seconds": 0.0,
            }
        )

        if FAISS_INDEX_DIR.exists():

            try:
                shutil.rmtree(
                    FAISS_INDEX_DIR,
                    ignore_errors=True,
                )

            except Exception:
                logger.warning(
                    "Failed to remove FAISS "
                    "index directory: %s",
                    FAISS_INDEX_DIR,
                )

    logger.info(
        "Vector store has been reset to an empty state."
    )


# ============================================================
# SAVE INDEX
# ============================================================

def _save_index() -> None:
    """
    Persist the FAISS index to disk.
    """

    if vector_store is None:
        return

    try:

        FAISS_INDEX_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        vector_store.save_local(
            str(FAISS_INDEX_DIR)
        )

        logger.info(
            "Persisted FAISS index to %s",
            FAISS_INDEX_DIR.resolve(),
        )

    except Exception:

        logger.exception(
            "Failed to save FAISS index to disk."
        )


# ============================================================
# LOAD INDEX
# ============================================================

def _load_index() -> bool:
    """
    Try to load an existing persisted FAISS index.

    Returns:
        True if loading succeeded.
        False if no usable index exists.
    """

    global vector_store, _stats

    index_file = (
        FAISS_INDEX_DIR / "index.faiss"
    )

    if not index_file.exists():
        return False

    t0 = time.perf_counter()

    try:

        vector_store = FAISS.load_local(
            str(FAISS_INDEX_DIR),
            embedding_model,
            allow_dangerous_deserialization=True,
        )

        duration = (
            time.perf_counter() - t0
        )

        _stats.update(
            {
                "initialized": True,
                "init_duration_seconds": duration,
                "chunks_indexed": (
                    len(
                        vector_store.index_to_docstore_id
                    )
                ),
            }
        )

        logger.info(
            "Loaded persisted FAISS index "
            "from disk in %.2f seconds.",
            duration,
        )

        return True

    except Exception:

        logger.exception(
            "Failed to load persisted FAISS index "
            "from disk. Will rebuild from PDFs."
        )

        vector_store = None

        return False


# ============================================================
# MODULE INITIALIZATION
# ============================================================

# Try the persisted index first.
# If it cannot be loaded, rebuild it from PDFs.
if not _load_index():
    build_vector_store()