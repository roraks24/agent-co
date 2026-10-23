"""Configuration and environment settings for the Adaptive API Selection Pipeline."""

from __future__ import annotations

import os
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AdaptiveSettings(BaseModel):
    """Runtime configuration for adaptive routing and scoring weights."""
    enabled: bool = Field(default=True, description="Enable adaptive API selection.")
    default_tier: str = Field(default="MEDIUM", description="Fallback tier when prompt is ambiguous.")
    
    # Weights for candidate scoring (must sum to ~1.0)
    weight_tier: float = Field(default=0.35, description="Weight for tier alignment.")
    weight_capability: float = Field(default=0.20, description="Weight for capability / modalities.")
    weight_context: float = Field(default=0.15, description="Weight for context window headroom.")
    weight_cost: float = Field(default=0.15, description="Weight for cost efficiency.")
    weight_latency: float = Field(default=0.10, description="Weight for latency / speed.")
    weight_health: float = Field(default=0.05, description="Weight for provider health.")

    # Strict routing guards
    strict_tier_routing: bool = Field(
        default=True,
        description="Prevent routing LOW tasks to HIGH models, and HIGH tasks to LOW models.",
    )
    fallback_max_retries: int = Field(default=3, ge=1, le=10)
    enabled_providers: list[str] = Field(
        default_factory=lambda: ["groq", "openai", "deepseek", "local", "anthropic", "google"]
    )

    model_config = ConfigDict(extra="allow")


def load_adaptive_settings() -> AdaptiveSettings:
    """Load settings from environment variables or use production-grade defaults."""
    enabled_str = os.getenv("ADAPTIVE_ROUTING_ENABLED", "true").lower()
    enabled = enabled_str in ("1", "true", "yes", "on")

    default_tier = os.getenv("ADAPTIVE_DEFAULT_TIER", "MEDIUM").upper()
    if default_tier not in ("LOW", "MEDIUM", "HIGH"):
        default_tier = "MEDIUM"

    def _float_env(key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default

    def _int_env(key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    providers_str = os.getenv("ADAPTIVE_ENABLED_PROVIDERS", "groq,openai,deepseek,local,anthropic,google")
    enabled_providers = [p.strip().lower() for p in providers_str.split(",") if p.strip()]

    strict_str = os.getenv("ADAPTIVE_STRICT_TIER_ROUTING", "true").lower()
    strict_tier_routing = strict_str in ("1", "true", "yes", "on")

    return AdaptiveSettings(
        enabled=enabled,
        default_tier=default_tier,
        weight_tier=_float_env("ADAPTIVE_WEIGHT_TIER", 0.35),
        weight_capability=_float_env("ADAPTIVE_WEIGHT_CAPABILITY", 0.20),
        weight_context=_float_env("ADAPTIVE_WEIGHT_CONTEXT", 0.15),
        weight_cost=_float_env("ADAPTIVE_WEIGHT_COST", 0.15),
        weight_latency=_float_env("ADAPTIVE_WEIGHT_LATENCY", 0.10),
        weight_health=_float_env("ADAPTIVE_WEIGHT_HEALTH", 0.05),
        strict_tier_routing=strict_tier_routing,
        fallback_max_retries=_int_env("ADAPTIVE_FALLBACK_MAX_RETRIES", 3),
        enabled_providers=enabled_providers,
    )
