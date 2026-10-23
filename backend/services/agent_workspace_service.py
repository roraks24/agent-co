"""Service layer orchestrating projects, workspaces, and persistent agent runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.agent.workspace_service import get_workspace_dir
from backend.models.db.agent_run import AgentRun
from backend.models.db.execution_action import ExecutionAction
from backend.models.db.project import Project
from backend.models.db.users import User
from backend.models.db.workspace import Workspace
from backend.models.db.workspace_artifact import WorkspaceArtifact
from backend.repositories.agent_run_repository import AgentRunRepository
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger("rorak.service.agent_workspace")

GUEST_FALLBACK_UUID = UUID("a0000000-0000-4000-8000-000000000001")


class AgentWorkspaceService:
    """Orchestrates persistent projects, workspaces, agent runs, and tool actions."""

    def __init__(self, db: Session):
        self.db = db
        self.projects_repo = ProjectRepository(db)
        self.workspaces_repo = WorkspaceRepository(db)
        self.runs_repo = AgentRunRepository(db)

    def resolve_user_id(self, current_user: Optional[User]) -> UUID:
        """Resolve current user UUID or ensure guest user in database."""
        if current_user and current_user.id:
            return current_user.id if isinstance(current_user.id, UUID) else UUID(str(current_user.id))

        try:
            guest_user = self.db.query(User).filter(User.id == GUEST_FALLBACK_UUID).first()
            if not guest_user:
                guest_user = User(
                    id=GUEST_FALLBACK_UUID,
                    email="guest@rorak.local",
                    name="Guest User",
                )
                self.db.add(guest_user)
                self.db.flush()
        except Exception:
            self.db.rollback()
        return GUEST_FALLBACK_UUID

    def create_project(
        self,
        name: str,
        description: Optional[str],
        user_id: UUID,
    ) -> tuple[Project, Workspace]:
        """Create a new project and initialize its dedicated storage workspace."""
        proj_id = uuid4()
        project = Project(
            id=proj_id,
            name=name.strip(),
            description=description,
            user_id=user_id,
            status="active",
        )
        self.projects_repo.create(project)

        ws_id = uuid4()
        ws_path = str(get_workspace_dir(str(ws_id)))
        workspace = Workspace(
            id=ws_id,
            project_id=proj_id,
            user_id=user_id,
            storage_path=ws_path,
            status="ready",
        )
        self.workspaces_repo.create(workspace)
        self.db.commit()
        return project, workspace

    def list_projects(self, user_id: UUID) -> list[dict[str, Any]]:
        """List all projects owned by the user, formatted for the UI."""
        projects = self.projects_repo.list_by_user(user_id)
        results = []
        for p in projects:
            ws = self.workspaces_repo.get_by_project_id(p.id, user_id)
            results.append({
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "workspace_id": str(ws.id) if ws else None,
            })
        return results

    def get_project(self, project_id: UUID, user_id: Optional[UUID] = None) -> Optional[Project]:
        """Fetch project with optional ownership verification."""
        return self.projects_repo.get_by_id(project_id, user_id)

    def delete_project(self, project_id: UUID, user_id: Optional[UUID] = None) -> bool:
        """Delete project and associated workspace."""
        project = self.projects_repo.get_by_id(project_id, user_id)
        if not project:
            return False
        self.projects_repo.delete(project)
        self.db.commit()
        return True

    def resolve_workspace(
        self,
        workspace_id: UUID | str,
        user_id: Optional[UUID] = None,
    ) -> Optional[Workspace]:
        """Resolve workspace by ID, auto-recovering transient disk directories if needed."""
        ws_uuid = None
        if isinstance(workspace_id, UUID):
            ws_uuid = workspace_id
        else:
            try:
                ws_uuid = UUID(str(workspace_id))
            except (ValueError, AttributeError):
                ws_uuid = None

        workspace = None
        if ws_uuid:
            workspace = self.workspaces_repo.get_by_id(ws_uuid, user_id)

        if not workspace:
            # Check if directory exists on disk for default/demo workspace
            ws_path = get_workspace_dir(str(workspace_id))
            if ws_path.exists():
                effective_user_id = user_id or GUEST_FALLBACK_UUID
                dummy_proj = Project(
                    name="Agent Workspace",
                    description="Auto-created workspace project",
                    user_id=effective_user_id,
                )
                self.projects_repo.create(dummy_proj)
                workspace = Workspace(
                    id=ws_uuid or uuid4(),
                    project_id=dummy_proj.id,
                    user_id=effective_user_id,
                    storage_path=str(ws_path),
                )
                self.workspaces_repo.create(workspace)
                self.db.commit()
                return workspace
        return workspace

    def create_agent_run(
        self,
        workspace: Workspace,
        objective: str,
        task_type: str = "general",
    ) -> AgentRun:
        """Initialize and persist a new AgentRun in PENDING state."""
        run = AgentRun(
            id=uuid4(),
            workspace_id=workspace.id,
            project_id=workspace.project_id,
            user_id=workspace.user_id,
            objective=objective,
            task_type=task_type,
            execution_status="RUNNING",
            objective_status="PENDING",
        )
        self.runs_repo.create(run)
        self.db.commit()
        return run

    def update_agent_run_completion(
        self,
        run_id: UUID,
        execution_status: str,
        deliverable_status: Optional[str] = None,
        source_verification_status: Optional[str] = None,
        objective_status: str = "PENDING",
        evidence_summary: Optional[str] = None,
        final_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        plan_json: Optional[Any] = None,
    ) -> Optional[AgentRun]:
        """Update agent run completion results, summaries, and verified outcomes."""
        run = self.runs_repo.get_by_id(run_id)
        if not run:
            return None

        run.execution_status = execution_status
        run.deliverable_status = deliverable_status
        run.source_verification_status = source_verification_status
        run.objective_status = objective_status
        if evidence_summary:
            run.evidence_summary = evidence_summary
        if final_summary:
            run.final_summary = final_summary
        if error_message:
            run.error_message = error_message
        if plan_json:
            run.plan_json = plan_json
        run.completed_at = datetime.now(timezone.utc)
        self.runs_repo.update(run)
        self.db.commit()
        return run

    def record_action(
        self,
        run_id: UUID,
        step_id: str,
        tool_name: str,
        tool_args: Optional[dict[str, Any]] = None,
        tool_result: Optional[dict[str, Any]] = None,
        status: str = "pending",
        duration_ms: int = 0,
        retry_count: int = 0,
        error_details: Optional[str] = None,
    ) -> ExecutionAction:
        """Persist an individual tool execution step in PostgreSQL."""
        action = ExecutionAction(
            id=uuid4(),
            run_id=run_id,
            step_id=step_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            status=status,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error_details=error_details,
            completed_at=datetime.now(timezone.utc) if status in ("success", "failed") else None,
        )
        self.runs_repo.record_action(action)
        self.db.commit()
        return action

    def record_artifact(
        self,
        workspace_id: UUID,
        run_id: Optional[UUID],
        file_path: str,
        file_size: int = 0,
        mime_type: str = "text/plain",
    ) -> WorkspaceArtifact:
        """Record an artifact generated by an agent run."""
        artifact = WorkspaceArtifact(
            id=uuid4(),
            workspace_id=workspace_id,
            run_id=run_id,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
        )
        self.workspaces_repo.create_artifact(artifact)
        self.db.commit()
        return artifact

    def list_workspace_runs(self, workspace_id: UUID) -> list[dict[str, Any]]:
        """List execution history and past runs for a workspace."""
        runs = self.runs_repo.list_by_workspace(workspace_id)
        results = []
        for r in runs:
            results.append({
                "id": str(r.id),
                "workspace_id": str(r.workspace_id),
                "project_id": str(r.project_id),
                "objective": r.objective,
                "task_type": r.task_type,
                "execution_status": r.execution_status,
                "deliverable_status": r.deliverable_status,
                "source_verification_status": r.source_verification_status,
                "objective_status": r.objective_status,
                "evidence_summary": r.evidence_summary,
                "final_summary": r.final_summary,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            })
        return results
