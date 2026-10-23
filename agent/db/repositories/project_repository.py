"""Project persistence repository."""

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.db.models.project import Project


class ProjectRepository:
    """Repository handling Project CRUD operations."""

    @staticmethod
    def get_by_id(db: Session, project_id: UUID) -> Optional[Project]:
        return db.get(Project, project_id)

    @staticmethod
    def list_by_user(db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(desc(Project.updated_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def create(
        db: Session,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        status: str = "active",
    ) -> Project:
        project = Project(
            user_id=user_id,
            name=name.strip(),
            description=description,
            status=status,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def update(
        db: Session,
        project_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Project]:
        project = db.get(Project, project_id)
        if not project:
            return None

        if name is not None:
            project.name = name.strip()
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status

        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def delete(db: Session, project_id: UUID) -> bool:
        project = db.get(Project, project_id)
        if not project:
            return False
        db.delete(project)
        db.commit()
        return True
