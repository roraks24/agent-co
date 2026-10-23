"""Database models for persistent state: auth, run history, audit logs, and prompt presets.

These tables complement the existing ephemeral workspace filesystem
(agent/workspace.py) without replacing it.  Generated project files still
live on the local temp filesystem and are downloadable as ZIP; these models
store *metadata* around users, execution history, and configuration.

Tables
------
users             – Registered user accounts.
api_keys          – Encrypted LLM provider credentials per user.
workflow_runs     – One row per /generate or /stream invocation.
saved_plans       – Planner + Architect output snapshot per run.
execution_records – Immutable audit log of every tool call the coder makes.
prompt_templates  – User-defined prompt overrides for planner/architect/coder.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

# Dialect-agnostic JSON column: JSONB on PostgreSQL, JSON on SQLite
JsonType = JSON().with_variant(JSONB, "postgresql")


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all models."""
    pass


# ---------------------------------------------------------------------------
# 1. Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_new_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    tier = Column(String(50), nullable=False, default="free")  # free | pro
    daily_generation_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    api_keys = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    runs = relationship(
        "WorkflowRun", back_populates="user", cascade="all, delete-orphan"
    )
    prompt_templates = relationship(
        "PromptTemplate", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} tier={self.tier!r}>"


# ---------------------------------------------------------------------------
# 2. API Keys (encrypted LLM provider credentials)
# ---------------------------------------------------------------------------

class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_user_provider", "user_id", "provider"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider = Column(String(50), nullable=False, default="groq")
    encrypted_key = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return (
            f"<ApiKey id={self.id!r} provider={self.provider!r} "
            f"active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# 3. Workflow Runs (prompt + execution metadata)
# ---------------------------------------------------------------------------

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_user_created", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Input
    user_prompt = Column(Text, nullable=False)

    # Runtime
    status = Column(
        String(50), nullable=False, default="PENDING"
    )  # PENDING | PLANNING | ARCHITECTING | CODING | DONE | FAILED
    provider = Column(String(50), nullable=False, default="groq")
    model_name = Column(String(100), nullable=True)

    # Metrics
    duration_ms = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # Error
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="runs")
    plan = relationship(
        "SavedPlan",
        back_populates="run",
        uselist=False,
        cascade="all, delete-orphan",
    )
    execution_records = relationship(
        "ExecutionRecord", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowRun id={self.id!r} status={self.status!r} "
            f"prompt={self.user_prompt[:40]!r}>"
        )


# ---------------------------------------------------------------------------
# 4. Saved Plans (planner + architect output snapshot)
# ---------------------------------------------------------------------------

class SavedPlan(Base):
    """Persists the Plan and TaskPlan generated by the planner and architect
    nodes so users can review past outputs without re-running.

    Maps to ``state.Plan`` and ``state.TaskPlan``.
    """

    __tablename__ = "saved_plans"

    id = Column(String(36), primary_key=True, default=_new_id)
    run_id = Column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # From Plan
    app_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    techstack = Column(String(255), nullable=True)
    features = Column(JsonType, nullable=True)       # list[str]

    # From TaskPlan
    task_steps = Column(JsonType, nullable=True)      # list[ImplementationStep dict]

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    run = relationship("WorkflowRun", back_populates="plan")

    def __repr__(self) -> str:
        return f"<SavedPlan id={self.id!r} app={self.app_name!r}>"


# ---------------------------------------------------------------------------
# 5. Execution Records (immutable tool-call audit log)
# ---------------------------------------------------------------------------

class ExecutionRecord(Base):
    """Immutable audit row for every tool invocation the coder agent makes.

    Maps to ``state.ActionExecutionRecord``.
    """

    __tablename__ = "execution_records"
    __table_args__ = (
        Index("ix_execution_records_run_id", "run_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    run_id = Column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    step_id = Column(String(50), nullable=True)  # e.g. "step-1"
    tool_name = Column(String(100), nullable=False)
    tool_args = Column(JsonType, nullable=True)
    tool_result = Column(Text, nullable=True)

    duration_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="success")  # success | failed | error
    error = Column(Text, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    run = relationship("WorkflowRun", back_populates="execution_records")

    def __repr__(self) -> str:
        return (
            f"<ExecutionRecord id={self.id!r} tool={self.tool_name!r} "
            f"status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# 6. Prompt Templates (user-defined prompt overrides)
# ---------------------------------------------------------------------------

class PromptTemplate(Base):
    """User-customised prompt overrides targeting a specific workflow node.

    Maps to the mutable prompt override concept in ``agent/prompts.py``.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index("ix_prompt_templates_user_node", "user_id", "node_target"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title = Column(String(255), nullable=False)
    node_target = Column(
        String(50), nullable=False, default="global"
    )  # planner | architect | coder | global
    prompt_override = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="prompt_templates")

    def __repr__(self) -> str:
        return (
            f"<PromptTemplate id={self.id!r} title={self.title!r} "
            f"node={self.node_target!r}>"
        )
