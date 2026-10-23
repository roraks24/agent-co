from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.db.conversation import Conversation
from backend.models.db.message import Message


class MessageRepository:
    """Repository handling CRUD operations and queries for conversation messages."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        message_id: UUID,
        conversation_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> Message | None:
        """
        Get a message by ID, optionally scoped to a conversation and user.
        """
        stmt = select(Message).where(Message.id == message_id)
        if conversation_id is not None:
            stmt = stmt.where(Message.conversation_id == conversation_id)
        if user_id is not None:
            stmt = stmt.join(
                Conversation,
                Message.conversation_id == Conversation.id,
            ).where(Conversation.user_id == user_id)

        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> list[Message]:
        """
        Return all messages belonging to a conversation, ordered chronologically.
        """
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if user_id is not None:
            stmt = stmt.join(
                Conversation,
                Message.conversation_id == Conversation.id,
            ).where(Conversation.user_id == user_id)

        stmt = stmt.order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )

        return list(self.db.execute(stmt).scalars().all())

    def get_by_conversation_paginated(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Message]:
        """
        Return paginated messages for a conversation, ordered chronologically.
        """
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if user_id is not None:
            stmt = stmt.join(
                Conversation,
                Message.conversation_id == Conversation.id,
            ).where(Conversation.user_id == user_id)

        stmt = (
            stmt.order_by(
                Message.created_at.asc(),
                Message.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.execute(stmt).scalars().all())

    def get_recent_for_context(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """
        Return the most recent N messages for LLM context, returned in chronological order.
        """
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if user_id is not None:
            stmt = stmt.join(
                Conversation,
                Message.conversation_id == Conversation.id,
            ).where(Conversation.user_id == user_id)

        stmt = (
            stmt.order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .limit(limit)
        )

        messages = list(self.db.execute(stmt).scalars().all())
        messages.reverse()
        return messages

    def count_by_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> int:
        """Count messages in a conversation."""
        stmt = select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id
        )
        if user_id is not None:
            stmt = stmt.join(
                Conversation,
                Message.conversation_id == Conversation.id,
            ).where(Conversation.user_id == user_id)

        return self.db.execute(stmt).scalar_one()

    def create(
        self,
        message: Message,
    ) -> Message:
        """Create and flush a new message."""
        self.db.add(message)
        self.db.flush()
        return message

    def delete(
        self,
        message: Message | UUID,
        conversation_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> bool:
        """
        Delete a message. Accepts either a Message instance or message UUID.
        """
        if isinstance(message, UUID):
            msg = self.get_by_id(
                message_id=message,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            if msg is None:
                return False
            target = msg
        else:
            target = message

        self.db.delete(target)
        self.db.flush()
        return True

    def delete_by_conversation(
        self,
        conversation_id: UUID,
    ) -> int:
        """Delete all messages belonging to a conversation."""
        stmt = delete(Message).where(Message.conversation_id == conversation_id)
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount