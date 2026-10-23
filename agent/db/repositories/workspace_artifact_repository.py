"""WorkspaceArtifact persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.db.models.workspace_artifact import WorkspaceArtifact


class WorkspaceArtifactRepository:
    """Repository handling WorkspaceArtifact persistence."""

    @staticmethod
    def record_artifact(
        db: Session,
        workspace_id: UUID,
        file_path: str,
        file_size: int = 0,
        mime_type: str = "text/plain",
        run_id: Optional[UUID] = None,
    ) -> WorkspaceArtifact:
        artifact = WorkspaceArtifact(
            workspace_id=workspace_id,
            run_id=run_id,
            file_path=file_path.strip(),
            file_size=file_size,
            mime_type=mime_type,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact

    @staticmethod
    def list_by_workspace(
        db: Session, workspace_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[WorkspaceArtifact]:
        stmt = (
            select(WorkspaceArtifact)
            .where(WorkspaceArtifact.workspace_id == workspace_id)
            .order_by(desc(WorkspaceArtifact.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def list_by_run(db: Session, run_id: UUID) -> list[WorkspaceArtifact]:
        stmt = (
            select(WorkspaceArtifact)
            .where(WorkspaceArtifact.run_id == run_id)
            .order_by(desc(WorkspaceArtifact.created_at))
        )
        return list(db.execute(stmt).scalars().all())
