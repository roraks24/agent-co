"""Add agent workspace, projects, runs, and execution action entities

Revision ID: e7a2b91c045f
Revises: 47830d97fbcc
Create Date: 2026-10-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "e7a2b91c045f"
down_revision: Union[str, None] = "47830d97fbcc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Projects
    op.create_table(
        "projects",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # 2. Workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workspaces_project_id", "workspaces", ["project_id"])
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])

    # 3. Agent Runs
    op.create_table(
        "agent_runs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PG_UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False, server_default="general"),
        sa.Column("plan_json", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("execution_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("deliverable_status", sa.String(50), nullable=True),
        sa.Column("source_verification_status", sa.String(50), nullable=True),
        sa.Column("objective_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("final_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_workspace_id", "agent_runs", ["workspace_id"])
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])

    # 4. Execution Actions
    op.create_table(
        "execution_actions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_args", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("tool_result", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("duration_ms", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_execution_actions_run_id", "execution_actions", ["run_id"])

    # 5. Workspace Artifacts
    op.create_table(
        "workspace_artifacts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PG_UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="text/plain"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workspace_artifacts_workspace_id", "workspace_artifacts", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("workspace_artifacts")
    op.drop_table("execution_actions")
    op.drop_table("agent_runs")
    op.drop_table("workspaces")
    op.drop_table("projects")
