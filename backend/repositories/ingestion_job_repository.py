from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.db.ingestion_job import IngestionJob


class IngestionJobRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, job_id: UUID) -> IngestionJob | None:
        stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_document(self, document_id: UUID) -> list[IngestionJob]:
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_by_document(self, document_id: UUID) -> IngestionJob | None:
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, job: IngestionJob) -> IngestionJob:
        self.db.add(job)
        self.db.flush()
        return job

    def update_status(
        self,
        job_id: UUID,
        status: str,
        error_message: str | None = None,
        completed: bool = False,
    ) -> IngestionJob | None:
        job = self.get_by_id(job_id)
        if job:
            job.status = status
            if error_message is not None:
                job.error_message = error_message
            if completed:
                job.completed_at = datetime.now(timezone.utc)
            self.db.flush()
        return job

    def delete(self, job: IngestionJob) -> None:
        self.db.delete(job)
        self.db.flush()
