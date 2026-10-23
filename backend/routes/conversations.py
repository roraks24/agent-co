import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.db.users import User
from backend.models.schemas import (
    APIErrorResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    CreateMessageRequest,
    MessageListResponse,
    MessageResponse,
    Pagination,
    RenameConversationRequest,
)
from backend.services.conversation_service import ConversationService
from backend.services.exceptions import (
    ConversationNotFound,
    UserNotFound,
    ValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "User Not Found"},
    },
)
def create_conversation(
    payload: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new conversation thread bound to authenticated user."""
    service = ConversationService(db)
    try:
        conv = service.create_conversation(
            user_id=current_user.id,
            title=payload.title,
        )
        return conv
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
    "/{conversation_id}",
    response_model=ConversationResponse,
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
    },
)
def get_conversation(
    conversation_id: UUID,
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve / reopen a conversation thread with owner validation."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id=conversation_id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
            )
        return conv
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
    },
)
def rename_conversation(
    conversation_id: UUID,
    payload: RenameConversationRequest,
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change conversation title with owner verification."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id=conversation_id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
            )
        return service.rename_conversation(
            conversation_id=conversation_id,
            title=payload.title,
            user_id=current_user.id,
        )
    except ConversationNotFound as e:
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
    response_model=ConversationListResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "User Not Found"},
    },
)
def list_conversations(
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List conversation threads scoped to current user."""
    if user_id is not None and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Cannot list conversations of another user."}},
        )

    service = ConversationService(db)
    try:
        convs, total = service.list_user_conversations(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )

        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
        return ConversationListResponse(
            conversations=convs,
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


@router.delete(
    "/{conversation_id}",
    responses={
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
    },
)
def delete_conversation(
    conversation_id: UUID,
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a conversation thread and cleanly delete all associated messages."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id=conversation_id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
            )
        service.delete_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
        return {"status": "deleted", "message": f"Conversation {conversation_id} deleted."}
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
    },
)
def create_message(
    conversation_id: UUID,
    payload: CreateMessageRequest,
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a message to a conversation thread."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id=conversation_id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
            )
        msg = service.create_message(
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
            user_id=current_user.id,
        )
        return msg
    except ConversationNotFound as e:
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
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
    },
)
def get_messages(
    conversation_id: UUID,
    user_id: UUID | None = Query(default=None, description="Optional user ID scoping"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Load conversation history in deterministic order."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id=conversation_id)
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
            )
        messages, total = service.get_messages(
            conversation_id=conversation_id,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
        return MessageListResponse(
            messages=messages,
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e)}},
        )
