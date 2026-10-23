"""Repository handling CRUD operations and queries for Projects."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.db.project import Project


class ProjectRepository:
    """Repository handling database operations for Project entities."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        project_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[Project]:
        """Fetch project by primary key ID, optionally scoped to user."""
        stmt = select(Project).where(Project.id == project_id)
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """Fetch all projects owned by user, newest first."""
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc(), Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(self, project: Project) -> Project:
        """Persist a new project entity."""
        self.db.add(project)
        self.db.flush()
        return project

    def update(self, project: Project) -> Project:
        """Update an existing project entity."""
        self.db.flush()
        return project

    def delete(self, project: Project) -> None:
        """Remove a project entity."""
        self.db.delete(project)
        self.db.flush()
