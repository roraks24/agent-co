import logging
from typing import List
from langchain_core.documents import Document

from backend.rag import vector_store as vector_store_module
from backend.core.config import RETRIEVAL_K


logger = logging.getLogger(__name__)


def retriev_func(
    query: str,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> List[Document]:
    """
    Retrieve candidate chunks from the vector store based on query similarity.
    Enforces conversation-level and user-level isolation when provided.
    """
    if vector_store_module.vector_store is None:
        logger.info("Vector store is empty. No documents available for retrieval.")
        return []

    try:
        vs = vector_store_module.vector_store
        ntotal = getattr(vs.index, "ntotal", 1000) if hasattr(vs, "index") else 1000
        fetch_k = max(ntotal, 500)

        # 1. Chat-wise conversation isolation
        if conversation_id:
            try:
                from uuid import UUID
                from backend.core.database import SessionLocal
                from backend.models.db.document import Document as DBDocument
                with SessionLocal() as db:
                    conv_doc_ids = {
                        str(d[0]) for d in
                        db.query(DBDocument.id).filter(DBDocument.conversation_id == UUID(str(conversation_id))).all()
                    }
            except Exception:
                conv_doc_ids = set()

            if not conv_doc_ids:
                logger.info("No documents linked to conversation %s. Returning 0 context chunks.", conversation_id)
                return []

            results = vs.similarity_search(
                query,
                k=RETRIEVAL_K,
                filter=lambda m: str(m.get("document_id", "")) in conv_doc_ids,
                fetch_k=fetch_k,
            )
            # If direct query similarity returned 0 chunks (e.g. conversational queries like "i already uploaded the details"),
            # retrieve the most descriptive chunks of the linked document(s)
            if not results:
                logger.info("Direct query similarity returned 0 chunks; performing semantic fallback for conversation %s", conversation_id)
                fallback_queries = ["overview instructions steps requirements details", "summary assignment project task"]
                for fq in fallback_queries:
                    results = vs.similarity_search(
                        fq,
                        k=RETRIEVAL_K,
                        filter=lambda m: str(m.get("document_id", "")) in conv_doc_ids,
                        fetch_k=fetch_k,
                    )
                    if results:
                        break

            logger.info(
                "Retrieved %d filtered chunks for conversation %s for query: %.60s",
                len(results), conversation_id, query
            )
            return results

        # 2. User-level isolation
        if user_id:
            target_user = str(user_id)
            results = vs.similarity_search(
                query,
                k=RETRIEVAL_K,
                filter=lambda m: str(m.get("user_id", "")) == target_user,
                fetch_k=fetch_k,
            )
            logger.info(
                "Retrieved %d filtered chunks for user %s for query: %.60s",
                len(results), user_id, query
            )
            return results

        logger.info("Retrieved chunks for query: %.60s", query)
        return vs.similarity_search(query, k=RETRIEVAL_K)
    except Exception:
        logger.exception("Error during vector retrieval for query.")
        return []


def context_func(results: List[Document]) -> str:
    """
    Format retrieved documents into structured context blocks.
    Accurately reflects page numbers for PDFs, or row/block metadata for non-PDFs.
    """
    if not results:
        return ""

    context_chunks = []
    for i, document in enumerate(results, start=1):
        source = document.metadata.get("source", "Unknown")
        meta_parts = [f"Source: {source}"]
        if "page" in document.metadata and document.metadata["page"] != "N/A":
            meta_parts.append(f"Page: {document.metadata['page']}")
        elif "row_start" in document.metadata:
            meta_parts.append(f"Rows: {document.metadata['row_start']}-{document.metadata.get('row_end', '')}")
        elif "block_type" in document.metadata:
            meta_parts.append(f"Section: {document.metadata['block_type']}")

        meta_str = ", ".join(meta_parts)
        content = document.page_content.strip()

        context_chunks.append(
            f"--- Document Chunk {i} ({meta_str}) ---\n{content}"
        )

    return "\n\n".join(context_chunks)