import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.core.auth import get_optional_current_user
from backend.core.database import get_db
from backend.models.db import User
from backend.models.schemas import APIErrorResponse, ChatRequest, ChatResponse
from backend.services.conversation_service import ConversationService
from backend.services.exceptions import ConversationNotFound, ValidationError
from backend.services.generator import chat_func

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


@router.post(
    "/",
    response_model=ChatResponse,
    responses={
        400: {"model": APIErrorResponse, "description": "Validation Error"},
        401: {"model": APIErrorResponse, "description": "Unauthorized"},
        403: {"model": APIErrorResponse, "description": "Forbidden"},
        404: {"model": APIErrorResponse, "description": "Conversation Not Found"},
        422: {"model": APIErrorResponse, "description": "Validation Error"},
        500: {"model": APIErrorResponse, "description": "Internal Server Error"},
        503: {"model": APIErrorResponse, "description": "Service Unavailable"},
    },
)
def chat(
    request: ChatRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Document-grounded chat endpoint.
    Accepts user question, retrieves relevant context from documents, and generates answer.
    Enforces user authentication and conversation ownership.
    """
    try:
        if request.conversation_id:
            # Continuing an existing conversation thread requires authenticated ownership
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required to access conversation."}},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            service = ConversationService(db)
            conv = service.get_conversation(conversation_id=request.conversation_id)
            if conv.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": {"code": "FORBIDDEN", "message": "You do not have access to this conversation."}},
                )

            _, assistant_msg = service.send_user_message_and_reply(
                conversation_id=request.conversation_id,
                user_content=request.question,
                user_id=current_user.id,
                custom_keys=request.custom_keys,
            )
            return ChatResponse(
                answer=assistant_msg.content,
                conversation_id=request.conversation_id,
            )

        elif current_user:
            service = ConversationService(db)
            title = request.question.strip()[:50]
            conv = service.create_conversation(
                user_id=current_user.id,
                title=title,
            )
            _, assistant_msg = service.send_user_message_and_reply(
                conversation_id=conv.id,
                user_content=request.question,
                user_id=current_user.id,
                custom_keys=request.custom_keys,
            )
            return ChatResponse(
                answer=assistant_msg.content,
                conversation_id=conv.id,
            )

        else:
            # Standalone / stateless chat generation
            answer = chat_func(request.question, custom_keys=request.custom_keys)
            return ChatResponse(answer=answer, conversation_id=None)

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
    except HTTPException:
        raise
    except RuntimeError as e:
        error_msg = str(e)
        logger.error("Chat generation failed: %s", error_msg)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "LLM_PROVIDER_ERROR",
                    "message": error_msg,
                }
            },
        )
    except Exception:
        logger.exception("Unexpected error occurred in chat endpoint.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                }
            },
        )