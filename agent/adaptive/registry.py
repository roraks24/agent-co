"""Registry of AI models, providers, capability tiers, and credential resolution."""

from __future__ import annotations

import os
from typing import Optional
from .models import (
    ApiRegistryEntry,
    CostTier,
    LatencyTier,
    Modality,
    TaskTier,
)


def _get_default_registry_entries() -> list[ApiRegistryEntry]:
    """Pre-configured model profiles with capability ratings, cost, and latency tiers."""
    return [
        # ─────────────────────────────────────────────────────────────────────
        # LOW / LIGHTWEIGHT TIER
        # ─────────────────────────────────────────────────────────────────────
        ApiRegistryEntry(
            id="groq/llama-3.1-8b-instant",
            provider="groq",
            model_name="llama-3.1-8b-instant",
            capability_tier=TaskTier.LOW,
            context_window=131072,
            max_output_tokens=8192,
            supported_modalities=[Modality.TEXT, Modality.TOOLS],
            cost_tier=CostTier.VERY_LOW,
            latency_tier=LatencyTier.ULTRA_FAST,
            cost_per_m_input=0.05,
            cost_per_m_output=0.08,
            rate_limit_rpm=30,
            required_env_vars=["GROQ_API_KEY"],
            description="Ultra-fast, cost-effective model for lightweight tasks, formatting, and classification.",
        ),
        ApiRegistryEntry(
            id="groq/gemma2-9b-it",
            provider="groq",
            model_name="gemma2-9b-it",
            capability_tier=TaskTier.LOW,
            context_window=8192,
            max_output_tokens=4096,
            supported_modalities=[Modality.TEXT],
            cost_tier=CostTier.VERY_LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.08,
            cost_per_m_output=0.10,
            rate_limit_rpm=30,
            required_env_vars=["GROQ_API_KEY"],
            description="Compact, fast lightweight model for concise summaries and basic editing.",
        ),
        ApiRegistryEntry(
            id="openai/gpt-4o-mini",
            provider="openai",
            model_name="gpt-4o-mini",
            capability_tier=TaskTier.LOW,
            context_window=128000,
            max_output_tokens=16384,
            supported_modalities=[Modality.TEXT, Modality.VISION, Modality.TOOLS],
            cost_tier=CostTier.LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.15,
            cost_per_m_output=0.60,
            rate_limit_rpm=500,
            required_env_vars=["OPENAI_API_KEY"],
            description="Highly capable lightweight model with multimodal support and low latency.",
        ),
        ApiRegistryEntry(
            id="deepseek/deepseek-chat",
            provider="deepseek",
            model_name="deepseek-chat",
            capability_tier=TaskTier.LOW,
            context_window=64000,
            max_output_tokens=4096,
            supported_modalities=[Modality.TEXT, Modality.TOOLS],
            cost_tier=CostTier.VERY_LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.14,
            cost_per_m_output=0.28,
            rate_limit_rpm=60,
            required_env_vars=["DEEPSEEK_API_KEY", "OPENAI_API_KEY"],
            base_url="https://api.deepseek.com/v1",
            description="Low-cost, high-speed coding and language model.",
        ),
        ApiRegistryEntry(
            id="local/llama3.2:3b",
            provider="local",
            model_name="llama3.2:3b",
            capability_tier=TaskTier.LOW,
            context_window=8192,
            max_output_tokens=2048,
            supported_modalities=[Modality.TEXT],
            cost_tier=CostTier.FREE,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.0,
            cost_per_m_output=0.0,
            rate_limit_rpm=1000,
            required_env_vars=[],
            base_url="http://localhost:11434/v1",
            description="Local offline lightweight model for air-gapped or zero-cost execution.",
        ),

        # ─────────────────────────────────────────────────────────────────────
        # MEDIUM / BALANCED TIER
        # ─────────────────────────────────────────────────────────────────────
        ApiRegistryEntry(
            id="groq/llama-3.3-70b-versatile",
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            capability_tier=TaskTier.MEDIUM,
            context_window=131072,
            max_output_tokens=32768,
            supported_modalities=[Modality.TEXT, Modality.TOOLS, Modality.WEB_SEARCH],
            cost_tier=CostTier.LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.59,
            cost_per_m_output=0.79,
            rate_limit_rpm=30,
            required_env_vars=["GROQ_API_KEY"],
            description="High-throughput 70B open-weights model for general agent workflows and coding.",
        ),
        ApiRegistryEntry(
            id="groq/openai/gpt-oss-120b",
            provider="groq",
            model_name="openai/gpt-oss-120b",
            capability_tier=TaskTier.MEDIUM,
            context_window=131072,
            max_output_tokens=16384,
            supported_modalities=[Modality.TEXT, Modality.TOOLS, Modality.WEB_SEARCH],
            cost_tier=CostTier.LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.60,
            cost_per_m_output=0.90,
            rate_limit_rpm=30,
            required_env_vars=["GROQ_API_KEY"],
            description="Balanced versatile model for agentic workflow planning and tool invocation.",
        ),
        ApiRegistryEntry(
            id="deepseek/deepseek-reasoner",
            provider="deepseek",
            model_name="deepseek-reasoner",
            capability_tier=TaskTier.MEDIUM,
            context_window=64000,
            max_output_tokens=8192,
            supported_modalities=[Modality.TEXT, Modality.TOOLS],
            cost_tier=CostTier.LOW,
            latency_tier=LatencyTier.MODERATE,
            cost_per_m_input=0.55,
            cost_per_m_output=2.19,
            rate_limit_rpm=60,
            required_env_vars=["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1",
            description="Reasoning-focused model for analytical breakdown and mathematical logic.",
        ),
        ApiRegistryEntry(
            id="google/gemini-1.5-flash",
            provider="google",
            model_name="gemini-1.5-flash",
            capability_tier=TaskTier.MEDIUM,
            context_window=1000000,
            max_output_tokens=8192,
            supported_modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO, Modality.TOOLS],
            cost_tier=CostTier.VERY_LOW,
            latency_tier=LatencyTier.FAST,
            cost_per_m_input=0.075,
            cost_per_m_output=0.30,
            rate_limit_rpm=1000,
            required_env_vars=["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            description="Fast, massive context (1M tokens) multimodal model with high rate limits.",
        ),

        # ─────────────────────────────────────────────────────────────────────
        # HIGH / FRONTIER TIER
        # ─────────────────────────────────────────────────────────────────────
        ApiRegistryEntry(
            id="openai/gpt-4o",
            provider="openai",
            model_name="gpt-4o",
            capability_tier=TaskTier.HIGH,
            context_window=128000,
            max_output_tokens=16384,
            supported_modalities=[Modality.TEXT, Modality.VISION, Modality.TOOLS, Modality.WEB_SEARCH],
            cost_tier=CostTier.MEDIUM,
            latency_tier=LatencyTier.MODERATE,
            cost_per_m_input=2.50,
            cost_per_m_output=10.00,
            rate_limit_rpm=500,
            required_env_vars=["OPENAI_API_KEY"],
            description="Frontier multimodal model for complex system design, full-stack generation, and research.",
        ),
        ApiRegistryEntry(
            id="anthropic/claude-3-5-sonnet",
            provider="anthropic",
            model_name="claude-3-5-sonnet-20241022",
            capability_tier=TaskTier.HIGH,
            context_window=200000,
            max_output_tokens=8192,
            supported_modalities=[Modality.TEXT, Modality.VISION, Modality.TOOLS],
            cost_tier=CostTier.HIGH,
            latency_tier=LatencyTier.MODERATE,
            cost_per_m_input=3.00,
            cost_per_m_output=15.00,
            rate_limit_rpm=50,
            required_env_vars=["ANTHROPIC_API_KEY"],
            description="State-of-the-art reasoning, deep coding, and extensive architectural analysis.",
        ),
        ApiRegistryEntry(
            id="google/gemini-1.5-pro",
            provider="google",
            model_name="gemini-1.5-pro",
            capability_tier=TaskTier.HIGH,
            context_window=2000000,
            max_output_tokens=8192,
            supported_modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO, Modality.TOOLS],
            cost_tier=CostTier.MEDIUM,
            latency_tier=LatencyTier.MODERATE,
            cost_per_m_input=1.25,
            cost_per_m_output=5.00,
            rate_limit_rpm=60,
            required_env_vars=["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            description="Ultra-long context (2M tokens) and multimodal reasoning for deep research and massive codebases.",
        ),
        ApiRegistryEntry(
            id="openai/o1-mini",
            provider="openai",
            model_name="o1-mini",
            capability_tier=TaskTier.HIGH,
            context_window=128000,
            max_output_tokens=65536,
            supported_modalities=[Modality.TEXT, Modality.TOOLS],
            cost_tier=CostTier.MEDIUM,
            latency_tier=LatencyTier.SLOW,
            cost_per_m_input=3.00,
            cost_per_m_output=12.00,
            rate_limit_rpm=100,
            required_env_vars=["OPENAI_API_KEY"],
            description="High-reasoning model optimized for complex STEM, algorithms, and logic problems.",
        ),
    ]


class ApiRegistry:
    """Thread-safe registry for model discovery, capabilities, and credential resolution."""

    def __init__(self, entries: Optional[list[ApiRegistryEntry]] = None):
        self._entries: dict[str, ApiRegistryEntry] = {}
        initial = entries if entries is not None else _get_default_registry_entries()
        for entry in initial:
            self._entries[entry.id] = entry

    def register(self, entry: ApiRegistryEntry) -> None:
        """Register or update a model profile."""
        self._entries[entry.id] = entry

    def unregister(self, model_id: str) -> bool:
        """Remove a model profile."""
        return self._entries.pop(model_id, None) is not None

    def get(self, model_id: str) -> Optional[ApiRegistryEntry]:
        """Fetch model by ID."""
        return self._entries.get(model_id)

    def list_all(self, enabled_only: bool = True) -> list[ApiRegistryEntry]:
        """List registered models."""
        models = list(self._entries.values())
        if enabled_only:
            models = [m for m in models if m.enabled]
        return models

    def filter_by_tier(self, tier: TaskTier) -> list[ApiRegistryEntry]:
        """Retrieve models belonging to a specific capability tier."""
        return [m for m in self.list_all() if m.capability_tier == tier]

    def set_health(self, model_id: str, status: str) -> None:
        """Update model health status ('healthy', 'degraded', 'unavailable')."""
        model = self.get(model_id)
        if model:
            model.health_status = status

    def has_credentials(
        self,
        entry: Optional[ApiRegistryEntry],
        provided_api_key: Optional[str] = None,
    ) -> bool:
        """Check whether valid credentials exist for this model without exposing secrets."""
        if entry is None:
            return False

        # Local models require no external key
        if entry.provider == "local" or not entry.required_env_vars:
            return True

        # Check caller-supplied API key first
        if provided_api_key and provided_api_key.strip():
            key = provided_api_key.strip()
            # Disambiguate provider prefixes to prevent cross-provider credential leakage
            if key.startswith("gsk_") and entry.provider == "groq":
                return True
            elif key.startswith("sk-ant-") and entry.provider == "anthropic":
                return True
            elif key.startswith("AIza") and entry.provider in ("google", "gemini"):
                return True
            elif (key.startswith("sk-") or key.startswith("sess-")) and entry.provider in ("openai", "deepseek", "custom"):
                return True
            elif entry.provider in ("custom", "local", "deepseek") and len(key) >= 8:
                return True

        # Fall back to checking environment variable credentials for this model
        for env_var in entry.required_env_vars:
            val = os.getenv(env_var, "").strip()
            if val:
                return True

        return False

    def resolve_credential_source(
        self,
        entry: Optional[ApiRegistryEntry],
        provided_api_key: Optional[str] = None,
    ) -> str:
        """Identify which credential source will be used without exposing secret."""
        if entry is None:
            return "missing"
        if entry.provider == "local" or not entry.required_env_vars:
            return "none_required (local/offline)"
        if provided_api_key and provided_api_key.strip():
            key = provided_api_key.strip()
            if (
                (key.startswith("gsk_") and entry.provider == "groq")
                or (key.startswith("sk-ant-") and entry.provider == "anthropic")
                or (key.startswith("AIza") and entry.provider in ("google", "gemini"))
                or ((key.startswith("sk-") or key.startswith("sess-")) and entry.provider in ("openai", "deepseek", "custom"))
                or (entry.provider in ("custom", "local", "deepseek") and len(key) >= 8)
            ):
                return "request_payload / header"
        for env_var in entry.required_env_vars:
            if os.getenv(env_var, "").strip():
                return f"environment variable ({env_var})"
        return "missing"
