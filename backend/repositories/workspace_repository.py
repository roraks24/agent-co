"""Repository handling CRUD operations and queries for Workspaces and Artifacts."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.db.workspace import Workspace
from backend.models.db.workspace_artifact import WorkspaceArtifact


class WorkspaceRepository:
    """Repository handling database operations for Workspace and Artifact entities."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        workspace_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[Workspace]:
        """Fetch workspace by primary key ID, optionally scoped to user."""
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        if user_id is not None:
            stmt = stmt.where(Workspace.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_project_id(
        self,
        project_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[Workspace]:
        """Fetch workspace by associated project_id."""
        stmt = select(Workspace).where(Workspace.project_id == project_id)
        if user_id is not None:
            stmt = stmt.where(Workspace.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, workspace: Workspace) -> Workspace:
        """Persist a new workspace entity."""
        self.db.add(workspace)
        self.db.flush()
        return workspace

    def update(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace entity."""
        self.db.flush()
        return workspace

    def delete(self, workspace: Workspace) -> None:
        """Remove a workspace entity."""
        self.db.delete(workspace)
        self.db.flush()

    def create_artifact(self, artifact: WorkspaceArtifact) -> WorkspaceArtifact:
        """Record a generated artifact for a workspace."""
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def get_artifacts(
        self,
        workspace_id: UUID,
        limit: int = 100,
    ) -> list[WorkspaceArtifact]:
        """Fetch artifacts recorded for a workspace."""
        stmt = (
            select(WorkspaceArtifact)
            .where(WorkspaceArtifact.workspace_id == workspace_id)
            .order_by(WorkspaceArtifact.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())
