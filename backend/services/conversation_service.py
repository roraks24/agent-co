import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.core.config import CONTEXT_WINDOW_SIZE, MEMORY_WINDOW_SIZE
from backend.models.db.conversation import Conversation
from backend.models.db.message import Message
from backend.models.db.users import User
from backend.models.schemas import MessageRole
from backend.repositories.conversation_repository import ConversationRepository
from backend.repositories.message_repository import MessageRepository
from backend.repositories.memory_repository import MemoryRepository
from backend.services.exceptions import (
    ConversationNotFound,
    UserNotFound,
    ValidationError,
)
from backend.services.generator import chat_func


logger = logging.getLogger(__name__)

VALID_ROLES = {role.value for role in MessageRole}


class ConversationService:
    """
    Coordinates conversation lifecycle, message history,
    validation, context window policy,
    and RAG generation integration.
    """

    def __init__(
        self,
        db: Session,
        repository: ConversationRepository | None = None,
        message_repository: MessageRepository | None = None,
        memory_repository: MemoryRepository | None = None,
        context_window_size: int = CONTEXT_WINDOW_SIZE,
        memory_window_size: int = MEMORY_WINDOW_SIZE,
    ):
        self.db = db
        self.repository = repository or ConversationRepository(db)
        self.message_repository = (
            message_repository or MessageRepository(db)
        )
        self.memory_repository = (
            memory_repository or MemoryRepository(db)
        )
        self.context_window_size = context_window_size
        self.memory_window_size = memory_window_size

    # ------------------------------------------------------------------
    # Conversation lookup
    # ------------------------------------------------------------------

    def get_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> Conversation:
        """
        Resolve a conversation, optionally validating owner context.
        Converts missing/forbidden lookups into clean domain errors.
        """
        conversation = self.repository.get_by_id(conversation_id)

        if conversation is None:
            raise ConversationNotFound(
                f"Conversation with ID {conversation_id} was not found."
            )

        if user_id is not None and conversation.user_id != user_id:
            raise ConversationNotFound(
                f"Conversation with ID {conversation_id} was not found for user {user_id}."
            )

        return conversation

    # ------------------------------------------------------------------
    # Conversation listing
    # ------------------------------------------------------------------

    def list_user_conversations(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Conversation], int]:
        """List conversations for a user with pagination."""
        self._validate_pagination(page, page_size)

        skip = (page - 1) * page_size

        conversations = self.repository.get_by_user_paginated(
            user_id=user_id,
            skip=skip,
            limit=page_size,
        )

        total = self.repository.count_by_user(
            user_id=user_id,
        )

        return conversations, total

    # ------------------------------------------------------------------
    # Conversation creation
    # ------------------------------------------------------------------

    def create_conversation(
        self,
        user_id: UUID,
        title: str,
    ) -> Conversation:
        """
        Create a conversation for an authenticated user.
        Converts missing user into clean domain errors.
        """
        clean_title = title.strip() if title else ""

        if not clean_title:
            raise ValidationError(
                "Conversation title cannot be empty."
            )

        if len(clean_title) > 255:
            raise ValidationError(
                "Conversation title exceeds maximum length of 255 characters."
            )

        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(
                f"User with ID {user_id} was not found."
            )

        conversation = Conversation(
            id=uuid4(),
            user_id=user_id,
            title=clean_title,
        )

        try:
            self.repository.create(conversation)
            self.db.commit()
            self.db.refresh(conversation)
            return conversation
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Conversation rename
    # ------------------------------------------------------------------

    def rename_conversation(
        self,
        conversation_id: UUID,
        title: str,
        user_id: UUID | None = None,
    ) -> Conversation:
        """
        Rename a conversation without modifying historical messages.
        Updates conversation.updated_at.
        """
        conversation = self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        clean_title = title.strip() if title else ""

        if not clean_title:
            raise ValidationError(
                "Conversation title cannot be empty."
            )

        if len(clean_title) > 255:
            raise ValidationError(
                "Conversation title exceeds maximum length of 255 characters."
            )

        try:
            self.repository.update_title(
                conversation=conversation,
                title=clean_title,
            )
            conversation.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(conversation)
            return conversation
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Conversation deletion
    # ------------------------------------------------------------------

    def delete_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        """
        Delete only the selected conversation and its messages.
        """
        conversation = self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        try:
            # Delete messages belonging specifically to this conversation
            self.message_repository.delete_by_conversation(conversation.id)
            self.repository.delete(conversation)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Message retrieval
    # ------------------------------------------------------------------

    def get_messages(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Message], int]:
        """
        Retrieve paginated messages for a validated conversation.
        """
        self._validate_pagination(page, page_size)

        # Resolve and validate the conversation first
        self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        skip = (page - 1) * page_size

        messages = self.message_repository.get_by_conversation_paginated(
            conversation_id=conversation_id,
            user_id=user_id,
            skip=skip,
            limit=page_size,
        )

        total = self.message_repository.count_by_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        return messages, total

    # ------------------------------------------------------------------
    # Message creation
    # ------------------------------------------------------------------

    def create_message(
        self,
        conversation_id: UUID,
        role: str | MessageRole,
        content: str,
        user_id: UUID | None = None,
    ) -> Message:
        """
        Resolve and validate conversation before adding a message.
        Updates conversation.updated_at.
        """
        conversation = self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        role_str = (
            role.value
            if isinstance(role, MessageRole)
            else str(role).lower().strip()
        )

        if role_str not in VALID_ROLES:
            raise ValidationError(
                f"Invalid message role '{role}'. Allowed roles: {sorted(list(VALID_ROLES))}."
            )

        clean_content = content.strip() if content else ""

        if not clean_content:
            raise ValidationError(
                "Message content cannot be empty."
            )

        if len(clean_content) > 10000:
            raise ValidationError(
                "Message content cannot exceed 10000 characters."
            )

        message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=role_str,
            content=clean_content,
            created_at=datetime.now(timezone.utc),
        )

        try:
            self.message_repository.create(message)
            conversation.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(message)
            return message
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Recent generation context
    # ------------------------------------------------------------------

    def get_recent_messages_for_context(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Return recent messages for LLM generation context."""
        if limit < 1 or limit > 100:
            raise ValidationError(
                "Context message limit must be between 1 and 100."
            )

        self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        return self.message_repository.get_recent_for_context(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # User message + assistant response
    # ------------------------------------------------------------------

    def send_user_message_and_reply(
        self,
        conversation_id: UUID,
        user_content: str,
        user_id: UUID | None = None,
        history_limit: int | None = None,
        memory_limit: int | None = None,
        auto_extract_memories: bool = True,
        custom_keys: Optional[dict] = None,
    ) -> tuple[Message, Message]:
        """
        Step 6 & 7 — Stateful Chat Context Assembly & Context Window Policy:
        - Start with a deterministic recent-message window.
        - Make its size configurable (via config/instance/call).
        - Preserve message role and chronological order.
        - Do not confuse short-term conversation history with long-term memory.
        - Keep raw history intact in DB without destructive truncation.
        - Avoid logging sensitive conversation content.
        """
        # 11. Identify the conversation from the request
        conversation = self.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        clean_content = user_content.strip() if user_content else ""

        if not clean_content:
            raise ValidationError(
                "Message content cannot be empty."
            )

        if len(clean_content) > 10000:
            raise ValidationError(
                "Message content cannot exceed 10000 characters."
            )

        # Configurable bounded window limits
        effective_history_limit = (
            history_limit if history_limit is not None else self.context_window_size
        )
        effective_memory_limit = (
            memory_limit if memory_limit is not None else self.memory_window_size
        )

        # 13. Load deterministic, bounded recent history window (raw history stays intact)
        bounded_history = self.message_repository.get_recent_for_context(
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            limit=effective_history_limit,
        )

        # 14. Auto-extract durable memories from user message (e.g. name, role, preferences)
        if auto_extract_memories:
            try:
                from backend.services.memory_extractor import auto_extract_and_save_memories
                auto_extract_and_save_memories(
                    db=self.db,
                    user_content=clean_content,
                    user_id=conversation.user_id,
                    memory_repo=self.memory_repository,
                )
            except Exception as e:
                logger.warning("Auto-memory extraction encountered error: %s", e)

        # Retrieve relevant durable memory for the correct scope (includes newly auto-saved memories)
        scoped_memories = self.memory_repository.get_scoped_memories(
            user_id=conversation.user_id,
            limit=effective_memory_limit,
        )

        try:
            # 12. Persist user message within deliberate transaction boundary
            user_message = Message(
                id=uuid4(),
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=clean_content,
            )
            self.message_repository.create(user_message)

            # 15, 16, 17. Execute grounded RAG (isolated to conversation), assemble stateful context, generate response
            answer = chat_func(
                query=clean_content,
                conversation_history=bounded_history,
                memory_context=scoped_memories,
                conversation_id=conversation.id,
                user_id=conversation.user_id,
                custom_keys=custom_keys,
            )

            if not answer:
                raise ValidationError(
                    "The assistant returned an empty response."
                )

            answer = str(answer).strip()

            if len(answer) > 10000:
                raise ValidationError(
                    "Assistant response exceeds maximum message length."
                )

            # 18. Persist assistant message only after successful generation
            assistant_message = Message(
                id=uuid4(),
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT.value,
                content=answer,
            )
            self.message_repository.create(assistant_message)

            # Update conversation.updated_at
            conversation.updated_at = datetime.now(timezone.utc)

            # Commit both user and assistant message atomically
            self.db.commit()

            self.db.refresh(user_message)
            self.db.refresh(assistant_message)

            return user_message, assistant_message

        except Exception:
            self.db.rollback()
            logger.exception(
                "Failed to process message for conversation %s",
                conversation_id,
            )
            raise

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pagination(
        page: int,
        page_size: int,
    ) -> None:
        if page < 1:
            raise ValidationError(
                "Page number must be >= 1."
            )

        if page_size < 1 or page_size > 100:
            raise ValidationError(
                "Page size must be between 1 and 100."
            )