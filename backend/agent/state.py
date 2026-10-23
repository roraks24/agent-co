"""State models and Pydantic schemas for Agent Co execution engine."""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class FileSpec(BaseModel):
    path: str
    purpose: str


class Plan(BaseModel):
    name: str = ""
    description: str = ""
    techstack: str = ""
    features: list[str] = Field(default_factory=list)
    files: list[FileSpec] = Field(default_factory=list)


class TaskStep(BaseModel):
    id: int
    file_path: str
    description: str
    dependencies: list[int] = Field(default_factory=list)


class TaskPlan(BaseModel):
    implementation_steps: list[TaskStep] = Field(default_factory=list)


class StepReview(BaseModel):
    status: Literal["PASS", "FAIL", "RETRY"]
    feedback: str = ""


class ActionStep(BaseModel):
    id: str
    title: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    expected_outcome: str = ""
    success_criteria: str = ""
    status: Literal["pending", "running", "completed", "failed", "retried"] = "pending"
    retry_count: int = 0
    error_details: Optional[str] = None


class ActionExecutionRecord(BaseModel):
    step_id: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    tool_result: Optional[Any] = None
    status: Literal["success", "failed", "retried", "error"] = "success"
    error: Optional[str] = None
    retry_count: int = 0
    run_id: Optional[str] = None


class GoalPlan(BaseModel):
    objective: str
    task_type: Literal["research", "coding", "data_analysis", "general"] = "general"
    expected_outcome: str = ""
    steps: list[ActionStep] = Field(default_factory=list)


class SourceEvidence(BaseModel):
    url: str
    title: Optional[str] = None
    status: Literal["retrieved", "failed", "unverified"] = "retrieved"
    observation_date: str = ""
    relevant_excerpt: str = ""
    claim_topics: list[str] = Field(default_factory=list)
    is_official_source: bool = False


class VerificationResult(BaseModel):
    objective_status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    execution_status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    deliverable_status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    source_verification_status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    functional_verification_status: Optional[str] = None
    criteria_evaluated: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    unverified_claims: list[str] = Field(default_factory=list)
    verified_sources: list[str] = Field(default_factory=list)
    feedback: Optional[str] = None


class AgentState(TypedDict, total=False):
    user_prompt: str
    mutable_prompt: Optional[str]
    prompt_overrides: dict[str, str]
    workspace_id: Optional[str]
    user_id: Optional[str]
    plan: Optional[Plan]
    detailed_ins: Optional[TaskPlan]
    goal_plan: Optional[GoalPlan]
    execution_records: list[ActionExecutionRecord]
    source_evidence: list[SourceEvidence]
    current_step_idx: int
    current_execution: Optional[dict[str, Any]]
    verification: Optional[VerificationResult]
    objective_status: Optional[str]
    final_summary: Optional[str]
    status: Optional[str]
    error_message: Optional[str]
    messages: list[Any]
