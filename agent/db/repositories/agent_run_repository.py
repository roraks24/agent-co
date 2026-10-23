"""AgentRun persistence repository."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from agent.db.models.agent_run import AgentRun


class AgentRunRepository:
    """Repository handling AgentRun CRUD and lifecycle status updates."""

    @staticmethod
    def create_run(
        db: Session,
        workspace_id: UUID,
        project_id: UUID,
        user_id: UUID,
        objective: str,
        task_type: str = "general",
        plan_json: Optional[Any] = None,
        run_id: Optional[UUID] = None,
    ) -> AgentRun:
        kwargs: dict[str, Any] = {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "user_id": user_id,
            "objective": objective,
            "task_type": task_type,
            "plan_json": plan_json,
            "execution_status": "RUNNING",
            "objective_status": "RUNNING",
        }
        if run_id is not None:
            kwargs["id"] = run_id

        run = AgentRun(**kwargs)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def get_by_id(db: Session, run_id: UUID) -> Optional[AgentRun]:
        return db.get(AgentRun, run_id)

    @staticmethod
    def list_by_project(
        db: Session, project_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.project_id == project_id)
            .order_by(desc(AgentRun.started_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def list_by_workspace(
        db: Session, workspace_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(desc(AgentRun.started_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def list_by_user(
        db: Session, user_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.user_id == user_id)
            .order_by(desc(AgentRun.started_at))
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def update_status(
        db: Session,
        run_id: UUID,
        execution_status: Optional[str] = None,
        objective_status: Optional[str] = None,
        deliverable_status: Optional[str] = None,
        source_verification_status: Optional[str] = None,
        evidence_summary: Optional[str] = None,
        final_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        plan_json: Optional[Any] = None,
        completed: bool = False,
    ) -> Optional[AgentRun]:
        run = db.get(AgentRun, run_id)
        if not run:
            return None

        if execution_status is not None:
            run.execution_status = execution_status
        if objective_status is not None:
            run.objective_status = objective_status
        if deliverable_status is not None:
            run.deliverable_status = deliverable_status
        if source_verification_status is not None:
            run.source_verification_status = source_verification_status
        if evidence_summary is not None:
            run.evidence_summary = evidence_summary
        if final_summary is not None:
            run.final_summary = final_summary
        if error_message is not None:
            run.error_message = error_message
        if plan_json is not None:
            run.plan_json = plan_json
        if completed:
            run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)
        return run
