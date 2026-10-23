"""Data models and schemas for the Adaptive API Selection Pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class TaskTier(str, Enum):
    """Complexity tiers for user tasks."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class QualityTier(str, Enum):
    """Quality / Accuracy requirements."""
    LOW = "LOW"
    BALANCED = "BALANCED"
    HIGH = "HIGH"
    MAXIMUM = "MAXIMUM"


class CostTier(str, Enum):
    """Relative cost tiers."""
    FREE = "FREE"
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LatencyTier(str, Enum):
    """Latency characteristics."""
    ULTRA_FAST = "ULTRA_FAST"
    FAST = "FAST"
    MODERATE = "MODERATE"
    SLOW = "SLOW"


class Modality(str, Enum):
    """Supported input/output modalities."""
    TEXT = "TEXT"
    VISION = "VISION"
    AUDIO = "AUDIO"
    CODE_EXECUTION = "CODE_EXECUTION"
    TOOLS = "TOOLS"
    WEB_SEARCH = "WEB_SEARCH"


class TaskIntakeRequest(BaseModel):
    """User request and optional performance/cost metadata."""
    user_prompt: str = Field(..., min_length=1, description="Raw user prompt or instructions.")
    task_type: Optional[str] = Field(default=None, description="Optional task type override.")
    desired_quality: Optional[str] = Field(default=None, description="Quality tier: low, balanced, high, maximum.")
    max_latency: Optional[float] = Field(default=None, description="Maximum acceptable latency in seconds.")
    budget: Optional[str | float] = Field(default=None, description="Budget constraint: free, low, medium, or USD cap.")
    context_length: Optional[int] = Field(default=None, description="Estimated prompt context size.")
    file_inputs: Optional[list[Any]] = Field(default=None, description="Uploaded files, attachments, or image paths.")
    modalities: Optional[list[str]] = Field(default=None, description="Requested modalities: text, vision, etc.")
    preferred_provider: Optional[str] = Field(default=None, description="User preferred provider: groq, openai, etc.")
    preferred_model: Optional[str] = Field(default=None, description="Explicit user model choice.")
    selected_api_id: Optional[str] = Field(default=None, description="Explicit database API provider ID for manual selection.")
    api_key: Optional[str] = Field(default=None, description="Optional caller-provided API key.")

    model_config = ConfigDict(extra="allow")


class ClassificationResult(BaseModel):
    """Result of classifying task complexity."""
    task_tier: TaskTier
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    signals: list[str] = Field(default_factory=list, description="Heuristic and linguistic signals used.")
    reason: str = Field(description="Explanation of classification rationale.")

    model_config = ConfigDict(extra="allow")


class ExtractedRequirements(BaseModel):
    """Derived resource and operational requirements for routing."""
    required_context_window: int = Field(default=4096, description="Estimated required context tokens.")
    expected_output_tokens: int = Field(default=1024, description="Expected generation length.")
    latency_sensitivity: str = Field(default="medium", description="Latency sensitivity: high, medium, low.")
    cost_sensitivity: str = Field(default="medium", description="Cost sensitivity: high, medium, low.")
    accuracy_requirement: QualityTier = Field(default=QualityTier.BALANCED)
    modal_requirements: list[Modality] = Field(default_factory=lambda: [Modality.TEXT])
    compliance_constraints: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApiRegistryEntry(BaseModel):
    """Specification of an API provider and model profile."""
    id: str = Field(..., description="Unique model identifier, e.g. 'groq/llama-3.1-8b-instant'.")
    provider: str = Field(..., description="Provider name: groq, openai, anthropic, deepseek, local, etc.")
    model_name: str = Field(..., description="Model string passed to provider API.")
    capability_tier: TaskTier = Field(..., description="Capability tier: LOW, MEDIUM, or HIGH.")
    context_window: int = Field(default=8192, description="Maximum context window tokens.")
    max_output_tokens: int = Field(default=4096, description="Maximum completion tokens.")
    supported_modalities: list[Modality] = Field(default_factory=lambda: [Modality.TEXT])
    cost_tier: CostTier = Field(default=CostTier.LOW)
    latency_tier: LatencyTier = Field(default=LatencyTier.FAST)
    cost_per_m_input: float = Field(default=0.0, description="USD per million input tokens.")
    cost_per_m_output: float = Field(default=0.0, description="USD per million output tokens.")
    rate_limit_rpm: int = Field(default=60, description="Requests per minute rate limit.")
    required_env_vars: list[str] = Field(default_factory=list, description="Environment variables needed for key.")
    base_url: Optional[str] = Field(default=None, description="Custom endpoint URL for compatible providers.")
    health_status: str = Field(default="healthy", description="Status: healthy, degraded, unavailable.")
    enabled: bool = Field(default=True, description="Whether this model is active in selection.")
    description: str = Field(default="")

    model_config = ConfigDict(extra="allow")


class CandidateScore(BaseModel):
    """Scoring breakdown for an evaluated candidate model."""
    model_id: str
    provider: str
    model_name: str
    capability_tier: TaskTier
    total_score: float
    eligible: bool
    tier_match_score: float = 0.0
    capability_score: float = 0.0
    context_fit_score: float = 0.0
    latency_score: float = 0.0
    cost_score: float = 0.0
    health_score: float = 0.0
    preference_score: float = 0.0
    ineligibility_reason: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class FallbackEvent(BaseModel):
    """Audit record of a fallback invocation."""
    attempt: int
    failed_api: str
    error_type: str
    error_message_sanitized: str
    timestamp: str
    recovered_with: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class SelectionDecision(BaseModel):
    """The final outcome of the selection engine."""
    selected_api: str = Field(..., description="Chosen model ID.")
    provider: str = Field(..., description="Provider name.")
    model: str = Field(..., description="Model string.")
    task_tier: TaskTier = Field(..., description="Classified task tier.")
    reason: str = Field(..., description="Detailed rationale for the selection.")
    confidence: float = Field(default=1.0)
    candidate_rankings: list[CandidateScore] = Field(default_factory=list)
    fallback_chain: list[str] = Field(default_factory=list, description="Ordered candidate IDs for fallback.")
    fallback_used: bool = Field(default=False)
    fallback_events: list[FallbackEvent] = Field(default_factory=list)
    latency_tier: LatencyTier = Field(default=LatencyTier.FAST)
    estimated_cost_tier: CostTier = Field(default=CostTier.LOW)
    resolved_api_key_source: str = Field(default="env")
    tradeoff_notes: Optional[str] = Field(default=None)
    selection_mode: str = Field(default="automatic", description="'manual' or 'automatic'")
    selected_api_details: Optional[dict[str, Any]] = Field(default=None, description="Safe details of chosen provider.")

    model_config = ConfigDict(extra="allow")
