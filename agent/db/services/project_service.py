"""Project and workspace lifecycle business service."""

from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from agent.db.models.project import Project
from agent.db.models.workspace import Workspace
from agent.db.repositories.project_repository import ProjectRepository
from agent.db.repositories.workspace_repository import WorkspaceRepository
from agent.workspace import workspace_base_dir


class ProjectOwnershipError(PermissionError):
    """Raised when an unauthenticated or unauthorized user accesses a project."""
    pass


class ProjectService:
    """Business service coordinating project lifecycle, ownership checks, and filesystem workspaces."""

    @staticmethod
    def create_project(
        db: Session,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
    ) -> tuple[Project, Workspace]:
        """Create a new project and initialize its dedicated storage workspace."""
        project = ProjectRepository.create(
            db,
            user_id=user_id,
            name=name,
            description=description,
        )

        # Storage directory under workspaces/{workspace_id}
        storage_path = str((workspace_base_dir() / str(project.id)).resolve())
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        workspace = WorkspaceRepository.create(
            db,
            project_id=project.id,
            user_id=user_id,
            storage_path=storage_path,
            status="ready",
        )
        return project, workspace

    @staticmethod
    def list_user_projects(
        db: Session,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Project]:
        """List all projects owned by the specified user."""
        return ProjectRepository.list_by_user(db, user_id=user_id, skip=skip, limit=limit)

    @staticmethod
    def get_project_checked(
        db: Session,
        project_id: UUID,
        user_id: UUID,
    ) -> Project:
        """Fetch project ensuring user has authorized ownership."""
        project = ProjectRepository.get_by_id(db, project_id)
        if not project:
            raise KeyError(f"Project with ID '{project_id}' not found.")
        if project.user_id != user_id:
            raise ProjectOwnershipError(f"User {user_id} does not own project {project_id}.")
        return project
