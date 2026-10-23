"""Workspace persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.db.models.workspace import Workspace


class WorkspaceRepository:
    """Repository handling Workspace entity persistence."""

    @staticmethod
    def get_by_id(db: Session, workspace_id: UUID) -> Optional[Workspace]:
        return db.get(Workspace, workspace_id)

    @staticmethod
    def get_by_project_id(db: Session, project_id: UUID) -> Optional[Workspace]:
        stmt = select(Workspace).where(Workspace.project_id == project_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def create(
        db: Session,
        project_id: UUID,
        user_id: UUID,
        storage_path: str,
        status: str = "ready",
    ) -> Workspace:
        workspace = Workspace(
            project_id=project_id,
            user_id=user_id,
            storage_path=storage_path,
            status=status,
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        return workspace

    @staticmethod
    def get_or_create_for_project(
        db: Session,
        project_id: UUID,
        user_id: UUID,
        storage_path: str,
    ) -> Workspace:
        workspace = WorkspaceRepository.get_by_project_id(db, project_id)
        if workspace is None:
            workspace = WorkspaceRepository.create(
                db, project_id=project_id, user_id=user_id, storage_path=storage_path
            )
        return workspace

    @staticmethod
    def update_status(db: Session, workspace_id: UUID, status: str) -> Optional[Workspace]:
        workspace = db.get(Workspace, workspace_id)
        if not workspace:
            return None
        workspace.status = status
        db.commit()
        db.refresh(workspace)
        return workspace
