"""Workspace entity model."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.db.database import Base

if TYPE_CHECKING:
    from agent.db.models.project import Project
    from agent.db.models.user import User
    from agent.db.models.agent_run import AgentRun
    from agent.db.models.workspace_artifact import WorkspaceArtifact


class Workspace(Base):
    """Workspace entity representing isolated filesystem environment and project storage."""
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ready",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="workspace")
    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    agent_runs: Mapped[List["AgentRun"]] = relationship(
        "AgentRun", back_populates="workspace", cascade="all, delete-orphan"
    )
    artifacts: Mapped[List["WorkspaceArtifact"]] = relationship(
        "WorkspaceArtifact", back_populates="workspace", cascade="all, delete-orphan"
    )
