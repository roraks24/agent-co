"""Memory persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.db.models.memory import Memory


class MemoryRepository:
    """Repository handling semantic Memory CRUD operations."""

    @staticmethod
    def create(
        db: Session,
        user_id: UUID,
        content: str,
        memory_type: str = "preference",
    ) -> Memory:
        mem = Memory(
            user_id=user_id,
            content=content.strip(),
            memory_type=memory_type,
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        return mem

    @staticmethod
    def list_by_user(
        db: Session, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(desc(Memory.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def delete(db: Session, memory_id: UUID) -> bool:
        mem = db.get(Memory, memory_id)
        if not mem:
            return False
        db.delete(mem)
        db.commit()
        return True
