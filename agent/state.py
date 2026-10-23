"""State and schema models for the planning/architect/coder graph and general task execution."""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# General-Purpose Task Execution Models
# ─────────────────────────────────────────────────────────────────────────────

class ActionStep(BaseModel):
    """An executable step within a generalized goal plan."""
    id: str = Field(description="Unique step identifier, e.g. 'step-1'.")
    title: str = Field(description="Short human-readable title of the step.")
    tool_name: str = Field(description="Name of the registered tool to execute.")
    tool_args: dict[str, Any] = Field(
        default_factory=dict,
        description="Validated arguments to pass to the tool."
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="IDs of steps that must complete before this step runs."
    )
    expected_outcome: str = Field(
        default="",
        description="Expected result or output from executing this step."
    )
    success_criteria: str = Field(
        default="",
        description="Specific conditions used to verify if this step succeeded."
    )
    status: str = Field(
        default="pending",
        description="Step status: pending, running, completed, failed, retried, skipped."
    )
    retry_count: int = Field(default=0, description="Number of retries attempted.")
    error_details: Optional[str] = Field(default=None, description="Error message if failed.")

    model_config = ConfigDict(extra="allow")


class GoalPlan(BaseModel):
    """Structured general-purpose execution plan decomposed from a user objective."""
    objective: str = Field(description="The user's primary objective.")
    task_type: str = Field(
        default="general",
        description="Category of task: research, analysis, coding, workflow, or general."
    )
    expected_outcome: str = Field(
        description="Description of what successful completion looks like."
    )
    steps: list[ActionStep] = Field(
        description="Ordered action steps with designated tools and criteria."
    )

    model_config = ConfigDict(extra="allow")


class ActionExecutionRecord(BaseModel):
    """Immutable audit record of an actual tool execution."""
    step_id: str = Field(description="Identifier of the associated plan step.")
    tool_name: str = Field(description="Name of the tool executed.")
    tool_args: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized input arguments with secrets redacted."
    )
    started_at: str = Field(description="ISO timestamp when execution started.")
    completed_at: str = Field(description="ISO timestamp when execution finished.")
    duration_ms: int = Field(description="Elapsed duration in milliseconds.")
    tool_result: Any = Field(
        default=None,
        description="Actual result returned by the tool (safely truncated if large)."
    )
    status: str = Field(description="Execution status: success, failed, error.")
    error: Optional[str] = Field(default=None, description="Error message if execution failed.")
    retry_count: int = Field(default=0, description="Retry attempt index.")
    run_id: Optional[str] = Field(default=None, description="Associated workflow run ID.")

    model_config = ConfigDict(extra="allow")


class VerificationResult(BaseModel):
    """Assessment of whether execution evidence satisfies the user's objective."""
    objective_status: str = Field(
        description="Final status: SUCCESS, PARTIAL_SUCCESS, or FAILED."
    )
    criteria_evaluated: list[str] = Field(
        default_factory=list,
        description="Specific success criteria checked against actual evidence."
    )
    evidence_summary: str = Field(
        description="Summary of facts and tool outputs supporting the determination."
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Corrective guidance or failure reasons if incomplete."
    )

    model_config = ConfigDict(extra="allow")


# ─────────────────────────────────────────────────────────────────────────────
# Coding-Specific Models (Preserved for Full Backward Compatibility)
# ─────────────────────────────────────────────────────────────────────────────

class FileSpec(BaseModel):
    path: str = Field(description="Path to the file to be created or modified.")
    purpose: str = Field(description="Short purpose of this file in the project.")


class Plan(BaseModel):
    name: str = Field(description="Short, clear name of the generated application.")
    description: str = Field(description="Two-sentence summary of what will be built.")
    techstack: str = Field(description="Primary technology stack needed for the build.")
    features: list[str] = Field(description="Core features to implement.")
    files: list[FileSpec] = Field(description="Files to generate with their purpose.")


class ImplementationStep(BaseModel):
    file_path: str = Field(description="Path for the file this step targets.")
    task_description: str = Field(description="Single-string task details for this file.")


class TaskPlan(BaseModel):
    implementation_steps: list[ImplementationStep] = Field(
        description="Ordered implementation steps, one per file."
    )
    model_config = ConfigDict(extra="allow")


class CoderState(BaseModel):
    task_plan: TaskPlan = Field(description="Plan containing all coder implementation steps.")
    current_step_idx: int = Field(
        0,
        description="Current index in implementation_steps.",
    )
    current_file_content: Optional[str] = Field(
        None,
        description="Optional in-memory copy of current file content.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph Workflow State
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_prompt: str
    mutable_prompt: str | None
    prompt_overrides: dict[str, str]
    
    # Coding-specific state
    plan: Plan
    detailed_ins: TaskPlan
    coder_state: CoderState
    
    # General-purpose state
    task_type: str
    goal_plan: GoalPlan
    execution_records: list[ActionExecutionRecord]
    current_step_idx: int
    verification: VerificationResult
    objective_status: str
    final_summary: str
    
    # General status
    status: str


# Compatibility aliases for legacy references.
File = FileSpec
impletation = ImplementationStep
Taskplan = TaskPlan
