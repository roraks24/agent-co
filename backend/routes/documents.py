import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.db import User
from backend.models.db.document import Document
from backend.models.schemas import (
    APIErrorResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    IngestionJobResponse,
    Pagination,
    RenameDocumentRequest,
)
from backend.services.document_service import DocumentService
from backend.services.exceptions import (
    DocumentNotFound,
    IngestionError,
    ValidationError,
)


logger = logging.getLogger(__name__)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Not Found"},
    },
)
async def upload_document(
    conversation_id: Optional[UUID] = Query(
        None,
        description="Optional conversation/chat that will own the document",
    ),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload and ingest a document directly for the authenticated user and optional conversation.
    """
    if conversation_id:
        from backend.services.conversation_service import ConversationService
        conv_service = ConversationService(db)
        conv = conv_service.get_conversation(conversation_id=conversation_id, user_id=current_user.id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this conversation.",
            )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required.",
        )

    original_filename = Path(
        file.filename
    ).name

    extension = Path(
        original_filename
    ).suffix.lower()

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{extension}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    service = DocumentService(db)

    temporary_path: Path | None = None

    try:
        # Save uploaded file to a temporary location.
        with NamedTemporaryFile(
            suffix=extension,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(
                temporary_file.name
            )

            total_size = 0

            while True:
                chunk = await file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                temporary_file.write(
                    chunk
                )

                total_size += len(
                    chunk
                )

                from backend.core.config import MAX_UPLOAD_SIZE_BYTES
                if total_size > MAX_UPLOAD_SIZE_BYTES:
                    temporary_file.close()
                    if temporary_path and temporary_path.exists():
                        temporary_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Uploaded file exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
                    )

        # Delegate complete ingestion workflow to the service.
        document, job, chunk_count = (
            service.ingest_document(
                user_id=current_user.id,
                file_path=temporary_path,
                original_filename=original_filename,
                file_size=total_size,
                conversation_id=conversation_id,
            )
        )

        return DocumentUploadResponse(
            document=_document_response(
                document
            ),
            ingestion_job=IngestionJobResponse.model_validate(
                job
            ),
            chunk_count=chunk_count,
        )

    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    finally:
        # Remove temporary upload.
        if temporary_path is not None:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except Exception:
                logger.warning(
                    "Failed to remove temporary upload: %s",
                    temporary_path,
                )

        try:
            await file.close()
        except Exception:
            logger.warning(
                "Failed to close uploaded file: %s",
                original_filename,
            )


# ============================================================
# LIST DOCUMENTS
# ============================================================

@router.get(
    "/",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Not Found"},
    },
)
def get_documents(
    conversation_id: Optional[UUID] = Query(
        default=None,
        description="Optional conversation whose documents should be listed",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of documents per page",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List documents belonging to the authenticated user (optionally filtered by conversation).
    """
    service = DocumentService(db)

    try:
        documents, total = (
            service.get_user_documents(
                user_id=current_user.id,
                conversation_id=conversation_id,
                page=page,
                page_size=page_size,
            )
        )

        total_pages = (
            max(1, (total + page_size - 1) // page_size)
            if total > 0
            else 1
        )

        return DocumentListResponse(
            documents=[
                _document_response(
                    document
                )
                for document in documents
            ],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )

    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ============================================================
# GET DOCUMENT
# ============================================================

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Document Not Found"},
    },
)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a single document by ID with user ownership check.
    """
    service = DocumentService(db)

    try:
        document = service.get_document(
            document_id
        )

        if document.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this document."}},
            )

        return _document_response(
            document
        )

    except DocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ============================================================
# RENAME DOCUMENT
# ============================================================

@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Document Not Found"},
    },
)
def rename_document(
    document_id: UUID,
    request: RenameDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Rename the user-facing display name of a document.
    """
    if not request.display_name or not request.display_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name cannot be empty.",
        )

    service = DocumentService(db)

    try:
        document = service.get_document(document_id)
        if document.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this document."}},
            )

        document = service.rename_document(
            document_id=document_id,
            display_name=request.display_name,
        )

        return _document_response(
            document
        )

    except DocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ============================================================
# DELETE DOCUMENT
# ============================================================

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Document Not Found"},
    },
)
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete one document and all associated resources.
    """
    service = DocumentService(db)

    try:
        document = service.get_document(document_id)
        if document.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this document."}},
            )

        service.delete_document(
            document_id
        )

    except DocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return None


# ============================================================
# RESPONSE HELPER
# ============================================================

def _document_response(
    document: Document,
) -> DocumentResponse:
    """
    Convert a Document ORM object into the public API schema.
    """
    return DocumentResponse(
        id=document.id,
        user_id=document.user_id,
        conversation_id=document.conversation_id,
        filename=document.filename,
        original_filename=document.original_filename,
        display_name=document.display_name,
        file_type=document.file_type,
        mime_type=document.mime_type,
        file_size=document.file_size,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        status=document.status,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )