from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.db.memory import Memory


class MemoryRepository:
    """Repository handling CRUD operations and queries for durable memory scoped to users."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, memory_id: UUID) -> Memory | None:
        """Get memory by ID."""
        stmt = select(Memory).where(Memory.id == memory_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_user(self, user_id: UUID, limit: int = 10) -> list[Memory]:
        """Get recent memories for a user."""
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc(), Memory.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_scoped_memories(
        self,
        user_id: UUID,
        limit: int = 10,
    ) -> list[Memory]:
        """
        Retrieve relevant durable memories for the user, newest first.
        Never retrieves another user's memory.
        """
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc(), Memory.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_scoped_memories(
        self,
        user_id: UUID,
        memory_type: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Memory]:
        """
        List memories scoped to user with pagination.
        """
        stmt = select(Memory).where(Memory.user_id == user_id)

        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)

        stmt = stmt.order_by(Memory.created_at.desc(), Memory.id.desc()).offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_scoped_memories(
        self,
        user_id: UUID,
        memory_type: str | None = None,
    ) -> int:
        """Count memories for a user."""
        stmt = select(func.count(Memory.id)).where(Memory.user_id == user_id)

        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)

        return self.db.execute(stmt).scalar_one()

    def count_by_user(self, user_id: UUID) -> int:
        """Count memories for a user."""
        stmt = select(func.count(Memory.id)).where(Memory.user_id == user_id)
        return self.db.execute(stmt).scalar_one()

    def create(self, memory: Memory) -> Memory:
        """Create and flush a new memory record."""
        self.db.add(memory)
        self.db.flush()
        return memory

    def update(
        self,
        memory: Memory,
        content: str | None = None,
        memory_type: str | None = None,
    ) -> Memory:
        """Update memory content or type and flush changes."""
        if content is not None:
            memory.content = content
        if memory_type is not None:
            memory.memory_type = memory_type
        self.db.flush()
        return memory

    def delete(self, memory: Memory) -> None:
        """Delete a memory record."""
        self.db.delete(memory)
        self.db.flush()
