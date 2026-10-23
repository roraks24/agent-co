"""ExecutionAction persistence repository with sensitive data redaction."""

from datetime import datetime, timezone
import json
import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.db.models.execution_action import ExecutionAction

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|bearer|authorization|groq_api_key|tavily_api_key)"
)
MAX_ACTION_OUTPUT_CHARS = 50_000


def _sanitize_data(data: Any, depth: int = 0) -> Any:
    """Recursively sanitize credentials and bounded payload size."""
    if depth > 5:
        return "<max_depth_reached>"
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if _SECRET_PATTERN.search(str(k)):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = _sanitize_data(v, depth + 1)
        return sanitized
    if isinstance(data, list):
        return [_sanitize_data(item, depth + 1) for item in data[:50]]
    if isinstance(data, str) and len(data) > MAX_ACTION_OUTPUT_CHARS:
        return data[:MAX_ACTION_OUTPUT_CHARS] + f"... [truncated {len(data) - MAX_ACTION_OUTPUT_CHARS} chars]"
    return data


class ExecutionActionRepository:
    """Repository handling ExecutionAction audit records."""

    @staticmethod
    def record_action(
        db: Session,
        run_id: UUID,
        step_id: str,
        tool_name: str,
        tool_args: Optional[Any] = None,
        tool_result: Optional[Any] = None,
        status: str = "pending",
        duration_ms: int = 0,
        retry_count: int = 0,
        error_details: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> ExecutionAction:
        safe_args = _sanitize_data(tool_args)
        safe_result = _sanitize_data(tool_result)

        action = ExecutionAction(
            run_id=run_id,
            step_id=step_id,
            tool_name=tool_name,
            tool_args=safe_args,
            tool_result=safe_result,
            status=status,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error_details=error_details,
            started_at=started_at or datetime.now(timezone.utc),
            completed_at=completed_at,
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        return action

    @staticmethod
    def list_by_run(db: Session, run_id: UUID) -> list[ExecutionAction]:
        stmt = (
            select(ExecutionAction)
            .where(ExecutionAction.run_id == run_id)
            .order_by(ExecutionAction.started_at.asc())
        )
        return list(db.execute(stmt).scalars().all())
