"""AgentRun orchestration and audit trail business service."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from agent.db.models.agent_run import AgentRun
from agent.db.models.execution_action import ExecutionAction
from agent.db.models.workspace_artifact import WorkspaceArtifact
from agent.db.repositories.agent_run_repository import AgentRunRepository
from agent.db.repositories.execution_action_repository import ExecutionActionRepository
from agent.db.repositories.workspace_artifact_repository import WorkspaceArtifactRepository


class AgentRunService:
    """Business service coordinating workflow run persistence and action audit logs."""

    @staticmethod
    def start_run(
        db: Session,
        workspace_id: UUID,
        project_id: UUID,
        user_id: UUID,
        objective: str,
        task_type: str = "general",
        plan_json: Optional[Any] = None,
        run_id: Optional[UUID] = None,
    ) -> AgentRun:
        """Initialize an agent run record."""
        return AgentRunRepository.create_run(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
            objective=objective,
            task_type=task_type,
            plan_json=plan_json,
            run_id=run_id,
        )

    @staticmethod
    def record_action_step(
        db: Session,
        run_id: UUID,
        step_id: str,
        tool_name: str,
        tool_args: Optional[Any] = None,
        tool_result: Optional[Any] = None,
        status: str = "success",
        duration_ms: int = 0,
        retry_count: int = 0,
        error_details: Optional[str] = None,
    ) -> ExecutionAction:
        """Record a single tool execution action step with sanitized arguments."""
        return ExecutionActionRepository.record_action(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            status=status,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error_details=error_details,
        )

    @staticmethod
    def complete_run(
        db: Session,
        run_id: UUID,
        execution_status: str,
        objective_status: str,
        deliverable_status: Optional[str] = None,
        source_verification_status: Optional[str] = None,
        evidence_summary: Optional[str] = None,
        final_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        plan_json: Optional[Any] = None,
    ) -> Optional[AgentRun]:
        """Finalize an agent run record with comprehensive verification results."""
        return AgentRunRepository.update_status(
            db,
            run_id=run_id,
            execution_status=execution_status,
            objective_status=objective_status,
            deliverable_status=deliverable_status,
            source_verification_status=source_verification_status,
            evidence_summary=evidence_summary,
            final_summary=final_summary,
            error_message=error_message,
            plan_json=plan_json,
            completed=True,
        )

    @staticmethod
    def register_artifact(
        db: Session,
        workspace_id: UUID,
        file_path: str,
        file_size: int = 0,
        mime_type: str = "text/plain",
        run_id: Optional[UUID] = None,
    ) -> WorkspaceArtifact:
        """Record artifact metadata generated during task execution."""
        return WorkspaceArtifactRepository.record_artifact(
            db,
            workspace_id=workspace_id,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            run_id=run_id,
        )
