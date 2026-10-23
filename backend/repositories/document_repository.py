from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.models.db.document import Document


class DocumentRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        document_id: UUID,
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id
        )
        return self.db.execute(
            stmt
        ).scalar_one_or_none()

    def get_by_user(
        self,
        user_id: UUID,
        conversation_id: UUID | None = None,
    ) -> list[Document]:
        stmt = select(Document).where(
            Document.user_id == user_id
        )
        if conversation_id is not None:
            stmt = stmt.where(Document.conversation_id == conversation_id)

        stmt = stmt.order_by(Document.created_at.desc())
        return list(
            self.db.execute(
                stmt
            ).scalars().all()
        )

    def get_by_user_paginated(
        self,
        user_id: UUID,
        conversation_id: UUID | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Document]:
        stmt = select(Document).where(Document.user_id == user_id)
        if conversation_id is not None:
            stmt = stmt.where(Document.conversation_id == conversation_id)
        stmt = (
            stmt.order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(
            self.db.execute(stmt).scalars().all()
        )

    def count_by_user(
        self,
        user_id: UUID,
        conversation_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count(Document.id)).where(
            Document.user_id == user_id
        )
        if conversation_id is not None:
            stmt = stmt.where(Document.conversation_id == conversation_id)
        return self.db.execute(stmt).scalar() or 0

    def create(
        self,
        document: Document,
    ) -> Document:
        self.db.add(
            document
        )

        self.db.flush()

        return document

    def update(
        self,
        document: Document,
    ) -> Document:
        """
        Persist changes to an existing document.
        """
        self.db.add(
            document
        )

        self.db.flush()

        self.db.refresh(
            document
        )

        return document

    def update_status(
        self,
        document_id: UUID,
        status: str,
    ) -> Document | None:
        doc = self.get_by_id(
            document_id
        )

        if doc:
            doc.status = status
            self.db.flush()

        return doc

    def delete(
        self,
        document: Document,
    ) -> None:
        self.db.delete(
            document
        )

        self.db.flush()