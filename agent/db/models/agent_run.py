"""AgentRun entity model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.db.database import Base

if TYPE_CHECKING:
    from agent.db.models.execution_action import ExecutionAction
    from agent.db.models.project import Project
    from agent.db.models.user import User
    from agent.db.models.workspace import Workspace
    from agent.db.models.workspace_artifact import WorkspaceArtifact


class AgentRun(Base):
    """Execution instance of an autonomous agent workflow decomposed into tasks and actions."""
    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    objective: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="general",
    )

    plan_json: Mapped[Optional[Any]] = mapped_column(
        JSON().with_variant(PG_JSONB(), "postgresql"),
        nullable=True,
    )

    execution_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
    )

    deliverable_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    source_verification_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    objective_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
    )

    evidence_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    final_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="agent_runs")
    project: Mapped["Project"] = relationship("Project", back_populates="agent_runs")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="agent_runs")
    actions: Mapped[List["ExecutionAction"]] = relationship(
        "ExecutionAction", back_populates="run", cascade="all, delete-orphan", order_by="ExecutionAction.started_at"
    )
    artifacts: Mapped[List["WorkspaceArtifact"]] = relationship(
        "WorkspaceArtifact", back_populates="run"
    )
