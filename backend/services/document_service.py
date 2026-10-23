import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.models.db.document import Document
from backend.models.db.document_chunk import DocumentChunk
from backend.models.db.ingestion_job import IngestionJob
from backend.models.schemas import DocumentStatus, IngestionStatus

from backend.rag.vector_store import (
    add_documents,
    delete_documents_by_document_id,
)

from backend.repositories.document_chunk_repository import (
    DocumentChunkRepository,
)
from backend.repositories.document_repository import (
    DocumentRepository,
)
from backend.repositories.ingestion_job_repository import (
    IngestionJobRepository,
)

from backend.services.document_storage import (
    calculate_sha256,
    save_artifact,
    delete_artifact,
)

from backend.services.exceptions import (
    DocumentNotFound,
    IngestionError,
    ValidationError,
)

from backend.services.ingestion import ingest_func


logger = logging.getLogger(__name__)


class DocumentService:
    """
    Coordinates document persistence, retrieval, per-user isolation,
    durable document storage, and document ingestion.
    """

    def __init__(
        self,
        db: Session,
        repository: DocumentRepository | None = None,
        chunk_repository: DocumentChunkRepository | None = None,
        job_repository: IngestionJobRepository | None = None,
    ):
        self.db = db

        self.repository = (
            repository
            or DocumentRepository(db)
        )

        self.chunk_repository = (
            chunk_repository
            or DocumentChunkRepository(db)
        )

        self.job_repository = (
            job_repository
            or IngestionJobRepository(db)
        )

    # ============================================================
    # GET DOCUMENT
    # ============================================================

    def get_document(
        self,
        document_id: UUID,
    ) -> Document:
        """Retrieve a document by ID or raise DocumentNotFound."""

        document = self.repository.get_by_id(
            document_id
        )

        if not document:
            raise DocumentNotFound(
                f"Document with ID {document_id} was not found."
            )

        return document

    # ============================================================
    # LIST DOCUMENTS
    # ============================================================

    def get_user_documents(
        self,
        user_id: UUID,
        conversation_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int]:
        """List documents belonging to a user (optionally filtered by conversation)."""
        if page < 1:
            raise ValidationError(
                "Page number must be >= 1."
            )

        if page_size < 1 or page_size > 100:
            raise ValidationError(
                "Page size must be between 1 and 100."
            )

        skip = (page - 1) * page_size

        documents = self.repository.get_by_user_paginated(
            user_id=user_id,
            conversation_id=conversation_id,
            skip=skip,
            limit=page_size,
        )

        total = self.repository.count_by_user(
            user_id=user_id,
            conversation_id=conversation_id,
        )

        return documents, total

    # ============================================================
    # RENAME DOCUMENT
    # ============================================================

    def rename_document(
        self,
        document_id: UUID,
        display_name: str,
    ) -> Document:
        """
        Rename the user-facing display name of a document.

        Rename must not:
        - reindex the document
        - change the checksum
        - change the storage key
        - change the original filename
        """

        if not display_name or not display_name.strip():
            raise ValidationError(
                "Display name cannot be empty."
            )

        display_name = display_name.strip()

        if len(display_name) > 255:
            raise ValidationError(
                "Display name must be 255 characters or fewer."
            )

        document = self.get_document(
            document_id
        )

        document.display_name = display_name

        self.repository.update(
            document
        )

        self.db.commit()

        self.db.refresh(
            document
        )

        logger.info(
            "Document %s renamed to '%s'.",
            document_id,
            display_name,
        )

        return document

    # ============================================================
    # CREATE DOCUMENT
    # ============================================================

    def create_document(
        self,
        filename: str,
        original_filename: str,
        user_id: UUID | None = None,
        file_type: str = "pdf",
        file_size: int = 0,
        page_count: int = 0,
        status: DocumentStatus = DocumentStatus.UPLOADED,
        display_name: str | None = None,
        mime_type: str = "application/pdf",
        storage_key: str | None = None,
        checksum_sha256: str | None = None,
        failure_reason: str | None = None,
        conversation_id: UUID | None = None,
    ) -> Document:
        """
        Create a document database record.

        This method creates document metadata.
        The complete upload/ingestion workflow is handled by
        ingest_document().
        """

        if not filename or not filename.strip():
            raise ValidationError(
                "Filename cannot be empty."
            )

        if not original_filename or not original_filename.strip():
            raise ValidationError(
                "Original filename cannot be empty."
            )

        safe_filename = filename.strip()
        safe_original_filename = original_filename.strip()

        document_id = uuid4()

        if display_name is None:
            display_name = safe_original_filename

        if storage_key is None:
            storage_key = (
                f"documents/"
                f"{document_id}/"
                f"original/"
                f"{Path(safe_filename).name}"
            )

        document = Document(
            id=document_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=safe_filename,
            display_name=display_name.strip(),
            original_filename=safe_original_filename,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            page_count=page_count,
            chunk_count=0,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
            status=(
                status.value
                if isinstance(status, DocumentStatus)
                else status
            ),
            failure_reason=failure_reason,
        )

        self.repository.create(
            document
        )

        self.db.commit()

        self.db.refresh(
            document
        )

        return document

    # ============================================================
    # DELETE DOCUMENT
    # ============================================================

    def delete_document(
        self,
        document_id: UUID,
    ) -> None:
        """
        Delete a document and all of its associated resources.

        Cleanup order:
        1. Remove document vectors from FAISS.
        2. Remove document chunks from PostgreSQL.
        3. Remove ingestion jobs from PostgreSQL.
        4. Remove the durable source artifact.
        5. Remove the document record.
        """

        document = self.get_document(
            document_id
        )

        # --------------------------------------------------------
        # 1. Remove only this document's vectors from FAISS.
        # --------------------------------------------------------

        try:
            delete_documents_by_document_id(
                str(document.id)
            )

            # --------------------------------------------------------
            # 2. Delete document chunks.
            # --------------------------------------------------------

            chunks = self.chunk_repository.get_by_document(
                document_id
            )

            for chunk in chunks:
                self.chunk_repository.delete(
                    chunk
                )

            # --------------------------------------------------------
            # 3. Delete ingestion jobs.
            # --------------------------------------------------------

            jobs = self.job_repository.get_by_document(
                document_id
            )

            for job in jobs:
                self.job_repository.delete(
                    job
                )

            # --------------------------------------------------------
            # 4. Delete durable source artifact.
            # --------------------------------------------------------

            delete_artifact(
                document.storage_key
            )

            # --------------------------------------------------------
            # 5. Delete document record.
            # --------------------------------------------------------

            self.repository.delete(
                document
            )

            self.db.commit()

            logger.info(
                "Document %s deleted successfully.",
                document_id,
            )
        except Exception:
            self.db.rollback()
            logger.exception("Failed to delete document %s cleanly.", document_id)
            raise

    # ============================================================
    # INGEST DOCUMENT
    # ============================================================

    def ingest_document(
        self,
        file_path: Path | str,
        original_filename: str,
        file_size: int = 0,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> tuple[Document, IngestionJob, int]:
        """
        Full V2.2 document ingestion workflow.

        1. Validate source file.
        2. Generate stable document UUID.
        3. Save durable source artifact.
        4. Calculate SHA-256 checksum.
        5. Create Document with PROCESSING status.
        6. Create IngestionJob with RUNNING status.
        7. Extract and chunk document.
        8. Create stable database chunk IDs.
        9. Attach document/user/chunk metadata to chunks.
        10. Add chunks to FAISS using stable IDs.
        11. Persist document chunks.
        12. Update document metadata.
        13. Mark Document INDEXED.
        14. Mark IngestionJob SUCCEEDED.

        On processing failure:
        - Document -> FAILED
        - failure_reason populated
        - IngestionJob -> FAILED
        - original artifact remains available.
        """

        # --------------------------------------------------------
        # 1. Validate source file.
        # --------------------------------------------------------

        path = Path(
            file_path
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Source file does not exist: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Source path is not a file: {path}"
            )

        if not original_filename or not original_filename.strip():
            raise ValidationError(
                "Original filename cannot be empty."
            )

        safe_name = path.name

        safe_original_filename = (
            original_filename.strip()
        )

        # --------------------------------------------------------
        # 2. Generate ONE stable document UUID.
        # --------------------------------------------------------

        document_id = uuid4()

        # --------------------------------------------------------
        # 3. Save durable original artifact.
        # --------------------------------------------------------

        storage_key = save_artifact(
            source_path=path,
            document_id=document_id,
            filename=safe_original_filename,
        )

        # --------------------------------------------------------
        # 4. Calculate SHA-256 checksum.
        # --------------------------------------------------------

        checksum_sha256 = calculate_sha256(
            path
        )

        # --------------------------------------------------------
        # 5. Create Document.
        # --------------------------------------------------------

        import mimetypes

        guessed_mime, _ = mimetypes.guess_type(safe_original_filename)
        mime_type = guessed_mime or "application/octet-stream"

        document = Document(
            id=document_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=safe_name,
            display_name=safe_original_filename,
            original_filename=safe_original_filename,
            file_type=(
                path.suffix.lstrip(".").lower()
                or "pdf"
            ),
            mime_type=mime_type,
            file_size=file_size,
            page_count=0,
            chunk_count=0,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
            status=DocumentStatus.PROCESSING.value,
            failure_reason=None,
        )

        try:
            self.repository.create(
                document
            )

            # --------------------------------------------------------
            # 6. Create ingestion job.
            # --------------------------------------------------------

            job = IngestionJob(
                id=uuid4(),
                document_id=document.id,
                status=IngestionStatus.RUNNING.value,
                started_at=datetime.now(
                    timezone.utc
                ),
            )

            self.job_repository.create(
                job
            )

            # Persist the initial lifecycle state.
            self.db.commit()

            self.db.refresh(
                document
            )

            self.db.refresh(
                job
            )
        except Exception:
            self.db.rollback()
            try:
                delete_artifact(storage_key)
            except Exception:
                logger.warning("Failed to clean up artifact %s after commit failure", storage_key)
            raise

        try:
            # ----------------------------------------------------
            # 7. Extract and chunk document.
            # ----------------------------------------------------

            chunks = ingest_func(
                path
            )

            if not chunks:
                raise IngestionError(
                    "No readable text content could be extracted "
                    "from this document."
                )

            # ----------------------------------------------------
            # 8. Create stable database chunk IDs.
            # ----------------------------------------------------

            db_chunks: list[DocumentChunk] = []
            faiss_ids: list[str] = []

            max_page = 0

            for index, chunk in enumerate(
                chunks
            ):
                metadata = (
                    chunk.metadata
                    or {}
                )

                page_num = metadata.get(
                    "page",
                    1,
                )

                if (
                    isinstance(page_num, int)
                    and page_num > max_page
                ):
                    max_page = page_num

                chunk_id = uuid4()

                # ------------------------------------------------
                # 9. Add stable V2.2 metadata to LangChain chunk.
                # ------------------------------------------------

                chunk.metadata = {
                    **metadata,
                    "document_id": str(
                        document.id
                    ),
                    "user_id": str(
                        document.user_id
                    ),
                    "conversation_id": str(
                        conversation_id
                    ) if conversation_id else "",
                    "chunk_id": str(
                        chunk_id
                    ),
                    "chunk_index": index,
                    "page": (
                        page_num
                        if isinstance(
                            page_num,
                            int,
                        )
                        else 1
                    ),
                }

                db_chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk.page_content,
                        page_number=(
                            page_num
                            if isinstance(
                                page_num,
                                int,
                            )
                            else 1
                        ),
                    )
                )

                # FAISS ID = database DocumentChunk UUID.
                faiss_ids.append(
                    str(chunk_id)
                )

            # ----------------------------------------------------
            # 10. Add chunks to FAISS using stable IDs.
            # ----------------------------------------------------

            add_documents(
                chunks,
                ids=faiss_ids,
            )

            # ----------------------------------------------------
            # 11. Persist document chunks.
            # ----------------------------------------------------

            self.chunk_repository.bulk_create(
                db_chunks
            )

            # ----------------------------------------------------
            # 12. Update document metadata.
            # ----------------------------------------------------

            document.chunk_count = (
                len(db_chunks)
            )

            document.page_count = max(
                max_page,
                1,
            )

            # ----------------------------------------------------
            # 13. Mark document indexed.
            # ----------------------------------------------------

            document.status = (
                DocumentStatus.INDEXED.value
            )

            document.failure_reason = None

            # ----------------------------------------------------
            # 14. Mark ingestion job successful.
            # ----------------------------------------------------

            job.status = (
                IngestionStatus.SUCCEEDED.value
            )

            job.completed_at = (
                datetime.now(
                    timezone.utc
                )
            )

            # Persist successful lifecycle.
            self.db.commit()

            self.db.refresh(
                document
            )

            self.db.refresh(
                job
            )

            logger.info(
                "Document %s (%s) ingested successfully: "
                "%d chunks created.",
                document.id,
                safe_original_filename,
                len(db_chunks),
            )

            return (
                document,
                job,
                len(db_chunks),
            )

        except Exception as exc:
            # Roll back uncommitted database work.
            self.db.rollback()

            error_message = str(
                exc
            )

            logger.exception(
                "Ingestion failed for document %s: %s",
                document.id,
                error_message,
            )

            try:
                # Re-fetch persistent rows after rollback.
                failed_document = (
                    self.repository.get_by_id(
                        document.id
                    )
                )

                failed_job = (
                    self.job_repository.get_by_id(
                        job.id
                    )
                )

                if failed_document:
                    failed_document.status = (
                        DocumentStatus.FAILED.value
                    )

                    failed_document.failure_reason = (
                        error_message
                    )

                if failed_job:
                    failed_job.status = (
                        IngestionStatus.FAILED.value
                    )

                    failed_job.error_message = (
                        error_message
                    )

                    failed_job.completed_at = (
                        datetime.now(
                            timezone.utc
                        )
                    )

                self.db.commit()

            except Exception:
                self.db.rollback()

                logger.exception(
                    "Failed to persist failure state "
                    "for document %s.",
                    document.id,
                )

            raise IngestionError(
                f"Document ingestion failed: {error_message}"
            ) from exc