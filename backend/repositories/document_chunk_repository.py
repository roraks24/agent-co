from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.models.db.document_chunk import DocumentChunk


class DocumentChunkRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        chunk_id: UUID,
    ) -> DocumentChunk | None:
        stmt = select(DocumentChunk).where(
            DocumentChunk.id == chunk_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_document(
        self,
        document_id: UUID,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_by_document(self, document_id: UUID) -> int:
        stmt = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
        return self.db.execute(stmt).scalar() or 0

    def create(
        self,
        chunk: DocumentChunk,
    ) -> DocumentChunk:
        self.db.add(chunk)
        self.db.flush()
        return chunk

    def bulk_create(
        self,
        chunks: list[DocumentChunk],
    ) -> list[DocumentChunk]:
        self.db.add_all(chunks)
        self.db.flush()
        return chunks

    def delete(
        self,
        chunk: DocumentChunk,
    ) -> None:
        self.db.delete(chunk)
        self.db.flush()