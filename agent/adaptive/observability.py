"""Observability, sanitization, cost estimation, and audit logging."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from .models import (
    CandidateScore,
    ExtractedRequirements,
    FallbackEvent,
    SelectionDecision,
)

logger = logging.getLogger("rorak.agent.adaptive.observability")

# Regex to detect secret keys and redact them
SECRET_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"sess-[a-zA-Z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"(?:api_key|token|password|secret)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", re.IGNORECASE),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE),
]


def sanitize_secrets(value: Any) -> Any:
    """Recursively scrub API keys and sensitive tokens from strings, dicts, and lists."""
    if isinstance(value, str):
        cleaned = value
        for pattern in SECRET_PATTERNS:
            cleaned = pattern.sub("***REDACTED_SECRET***", cleaned)
        return cleaned
    elif isinstance(value, dict):
        return {k: sanitize_secrets(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_secrets(item) for item in value]
    return value


def log_adaptive_decision(
    decision: SelectionDecision,
    requirements: ExtractedRequirements,
    latency_ms: float = 0.0,
) -> None:
    """Emit structured audit log without exposing credentials."""
    eligible_count = sum(1 for c in decision.candidate_rankings if c.eligible)
    candidate_summary = [
        f"{c.model_id} (score: {c.total_score:.2f}, eligible: {c.eligible})"
        for c in decision.candidate_rankings[:5]
    ]

    log_entry = {
        "event": "adaptive_api_selected",
        "selected_api": decision.selected_api,
        "provider": decision.provider,
        "task_tier": decision.task_tier.value,
        "confidence": decision.confidence,
        "reason": sanitize_secrets(decision.reason),
        "required_context_window": requirements.required_context_window,
        "expected_output_tokens": requirements.expected_output_tokens,
        "latency_sensitivity": requirements.latency_sensitivity,
        "cost_sensitivity": requirements.cost_sensitivity,
        "modalities": [m.value for m in requirements.modal_requirements],
        "top_candidates": candidate_summary,
        "eligible_candidates_count": eligible_count,
        "fallback_chain": decision.fallback_chain,
        "fallback_used": decision.fallback_used,
        "selection_latency_ms": round(latency_ms, 2),
        "credential_source": decision.resolved_api_key_source,
    }
    logger.info("Adaptive API Selection: %s", sanitize_secrets(log_entry))


def build_response_selection_metadata(
    decision: SelectionDecision,
    latency_ms: float = 0.0,
    actual_tokens_in: Optional[int] = None,
    actual_tokens_out: Optional[int] = None,
) -> dict[str, Any]:
    """Build client-facing metadata dictionary conforming to specification."""
    return {
        "selected_api": decision.selected_api,
        "provider": decision.provider,
        "model": decision.model,
        "task_tier": decision.task_tier.value,
        "confidence": decision.confidence,
        "reason": sanitize_secrets(decision.reason),
        "selection_mode": getattr(decision, "selection_mode", "automatic"),
        "selected_api_details": getattr(decision, "selected_api_details", None),
        "fallback_used": decision.fallback_used,
        "fallback_chain": decision.fallback_chain,
        "fallback_events": [evt.model_dump() for evt in decision.fallback_events],
        "estimated_cost_tier": decision.estimated_cost_tier.value,
        "latency_tier": decision.latency_tier.value,
        "latency_ms": round(latency_ms, 2),
        "tokens": {
            "input_tokens": actual_tokens_in,
            "output_tokens": actual_tokens_out,
        } if actual_tokens_in is not None else None,
    }
