"""Repository handling CRUD operations and queries for AgentRuns and ExecutionActions."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.db.agent_run import AgentRun
from backend.models.db.execution_action import ExecutionAction


class AgentRunRepository:
    """Repository handling database operations for AgentRun and ExecutionAction entities."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, run_id: UUID) -> Optional[AgentRun]:
        """Fetch agent run by primary key ID."""
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentRun]:
        """Fetch agent runs for a workspace, newest first."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_project(
        self,
        project_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentRun]:
        """Fetch agent runs for a project, newest first."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.project_id == project_id)
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(self, run: AgentRun) -> AgentRun:
        """Persist a new agent run entity."""
        self.db.add(run)
        self.db.flush()
        return run

    def update(self, run: AgentRun) -> AgentRun:
        """Update an existing agent run entity."""
        self.db.flush()
        return run

    def record_action(self, action: ExecutionAction) -> ExecutionAction:
        """Record an individual action/tool execution step."""
        self.db.add(action)
        self.db.flush()
        return action

    def get_actions_by_run(
        self,
        run_id: UUID,
    ) -> list[ExecutionAction]:
        """Fetch recorded tool execution actions for a run."""
        stmt = (
            select(ExecutionAction)
            .where(ExecutionAction.run_id == run_id)
            .order_by(ExecutionAction.started_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
