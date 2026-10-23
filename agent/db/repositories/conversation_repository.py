"""Conversation and Message persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.db.models.conversation import Conversation
from agent.db.models.message import Message


class ConversationRepository:
    """Repository handling Conversation and Message CRUD operations."""

    @staticmethod
    def get_by_id(db: Session, conversation_id: UUID) -> Optional[Conversation]:
        return db.get(Conversation, conversation_id)

    @staticmethod
    def list_by_user(
        db: Session, user_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def create(db: Session, user_id: UUID, title: str) -> Conversation:
        convo = Conversation(user_id=user_id, title=title.strip())
        db.add(convo)
        db.commit()
        db.refresh(convo)
        return convo

    @staticmethod
    def add_message(
        db: Session,
        conversation_id: UUID,
        role: str,
        content: str,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def get_messages(
        db: Session, conversation_id: UUID, limit: int = 100
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())
