import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.db.users import User
from backend.models.schemas import (
    APIErrorResponse,
    CreateMemoryRequest,
    MemoryListResponse,
    MemoryResponse,
    Pagination,
    UpdateMemoryRequest,
)
from backend.services.exceptions import (
    MemoryNotFound,
    UserNotFound,
    ValidationError,
)
from backend.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/memories",
    tags=["Memories"],
)


@router.post(
    "/",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
    },
)
def create_memory(
    payload: CreateMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store a new durable memory for the authenticated user."""
    service = MemoryService(db)
    try:
        memory = service.create_memory(
            user_id=current_user.id,
            content=payload.content,
            memory_type=payload.memory_type,
        )
        return memory
    except UserNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.get(
    "/",
    response_model=MemoryListResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
    },
)
def list_memories(
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    memory_type: str | None = Query(default=None, description="Optional memory type filter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List memories belonging to the authenticated user."""
    if user_id is not None and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Cannot list memories of another user."}},
        )

    service = MemoryService(db)
    try:
        memories, total = service.list_memories(
            user_id=current_user.id,
            memory_type=memory_type,
            page=page,
            page_size=page_size,
        )
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
        return MemoryListResponse(
            memories=memories,
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except UserNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Memory Not Found"},
    },
)
def get_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve a specific memory with ownership authorization."""
    service = MemoryService(db)
    try:
        memory = service.get_memory(memory_id=memory_id)
        if memory.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this memory."}},
            )
        return memory
    except MemoryNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Memory Not Found"},
    },
)
def update_memory(
    memory_id: UUID,
    payload: UpdateMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a memory with ownership enforcement."""
    service = MemoryService(db)
    try:
        memory = service.get_memory(memory_id=memory_id)
        if memory.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have permission to modify this memory."}},
            )
        return service.update_memory(
            memory_id=memory_id,
            content=payload.content,
            memory_type=payload.memory_type,
            user_id=current_user.id,
        )
    except MemoryNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.delete(
    "/{memory_id}",
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Memory Not Found"},
    },
)
def delete_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a memory with ownership enforcement."""
    service = MemoryService(db)
    try:
        memory = service.get_memory(memory_id=memory_id)
        if memory.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have permission to delete this memory."}},
            )
        service.delete_memory(
            memory_id=memory_id,
            user_id=current_user.id,
        )
        return {"status": "deleted", "message": f"Memory {memory_id} deleted."}
    except MemoryNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
