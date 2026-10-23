"""Database models and DTO schemas for API providers and configurations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from agent.adaptive.models import TaskTier, CostTier, LatencyTier, Modality
from agent.db.crypto import mask_secret


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiProviderBase(BaseModel):
    """Base fields for an API provider record."""
    provider_name: str = Field(..., description="Provider name: groq, openai, anthropic, deepseek, ollama, custom, etc.")
    display_name: str = Field(..., description="Human-readable label, e.g. 'Groq Llama 3.1 8B Instant'.")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL endpoint.")
    model_name: str = Field(..., description="Model identifier passed to provider API, e.g. 'llama-3.1-8b-instant'.")
    capability_tier: TaskTier = Field(default=TaskTier.MEDIUM, description="Tier: LOW, MEDIUM, or HIGH.")
    supported_tasks: list[str] = Field(
        default_factory=lambda: ["text", "code"],
        description="Supported tasks/modalities: text, code, vision, audio, long_context, tools, etc."
    )
    context_window: int = Field(default=8192, description="Maximum context window tokens.")
    max_output_tokens: int = Field(default=4096, description="Maximum output tokens.")
    latency_tier: str = Field(default="balanced", description="fast, balanced, slow.")
    cost_tier: str = Field(default="medium", description="free, low, medium, high.")
    is_active: bool = Field(default=True, description="Whether the provider is currently active.")
    is_default: bool = Field(default=False, description="Whether this is the default fallback provider.")
    priority: int = Field(default=50, description="Priority integer (higher = preferred when scoring).")
    health_status: str = Field(default="healthy", description="Status: healthy, degraded, down, unknown.")

    model_config = ConfigDict(extra="allow")


class ApiProviderCreate(ApiProviderBase):
    """Payload for registering a new provider."""
    id: Optional[str] = Field(default=None, description="Optional explicit ID; generated if omitted.")
    api_key: Optional[str] = Field(
        default=None,
        description="Raw API key or secret reference (e.g. 'env:GROQ_API_KEY'). Will be encrypted at rest."
    )


class ApiProviderUpdate(BaseModel):
    """Payload for updating an existing provider."""
    provider_name: Optional[str] = None
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    capability_tier: Optional[TaskTier] = None
    supported_tasks: Optional[list[str]] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    latency_tier: Optional[str] = None
    cost_tier: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None
    health_status: Optional[str] = None
    api_key: Optional[str] = Field(
        default=None,
        description="If provided, replaces existing encrypted API key."
    )

    model_config = ConfigDict(extra="allow")


class ApiProviderRecord(ApiProviderBase):
    """Full database record including stored encrypted key/secret reference."""
    id: str
    api_key_encrypted: str = Field(default="", description="Encrypted API key ('enc:...') or env reference ('env:...').")
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def to_public(self) -> ApiProviderPublic:
        """Convert to safe public representation for API clients without leaking secret."""
        return ApiProviderPublic(
            id=self.id,
            provider_name=self.provider_name,
            display_name=self.display_name,
            base_url=self.base_url,
            model_name=self.model_name,
            capability_tier=self.capability_tier,
            supported_tasks=self.supported_tasks,
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
            latency_tier=self.latency_tier,
            cost_tier=self.cost_tier,
            is_active=self.is_active,
            is_default=self.is_default,
            priority=self.priority,
            health_status=self.health_status,
            has_api_key=bool(self.api_key_encrypted and self.api_key_encrypted.strip()),
            api_key_masked=mask_secret(self.api_key_encrypted),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ApiProviderPublic(BaseModel):
    """Safe, non-secret public API model for frontend consumption."""
    id: str
    provider_name: str
    display_name: str
    base_url: Optional[str] = None
    model_name: str
    capability_tier: TaskTier
    supported_tasks: list[str]
    context_window: int
    max_output_tokens: int
    latency_tier: str
    cost_tier: str
    is_active: bool
    is_default: bool
    priority: int
    health_status: str
    has_api_key: bool
    api_key_masked: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="allow")
