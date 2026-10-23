"""Execution and automatic fallback handler across candidate APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Optional, TypeVar
from .models import FallbackEvent, SelectionDecision
from .observability import sanitize_secrets
from .registry import ApiRegistry

logger = logging.getLogger("rorak.agent.adaptive.fallback")

T = TypeVar("T")


class AdaptiveExecutionError(RuntimeError):
    """Raised when primary and all fallback model attempts fail."""
    def __init__(self, message: str, events: list[FallbackEvent]):
        super().__init__(message)
        self.events = events


class ExecutionAndFallbackHandler:
    """Executes requests with automated graceful fallback over ranked candidate models."""

    def __init__(self, registry: Optional[ApiRegistry] = None):
        self.registry = registry or ApiRegistry()

    def execute_with_fallback(
        self,
        decision: SelectionDecision,
        executor_fn: Callable[[str, str, Optional[str]], T],
        user_api_key: Optional[str] = None,
    ) -> tuple[T, SelectionDecision]:
        """
        Execute request with primary model; on failure, automatically retry with next-best fallback.
        
        executor_fn signature: (provider, model_name, base_url) -> result
        """
        candidate_ids = [decision.selected_api] + [
            m for m in decision.fallback_chain if m != decision.selected_api
        ]

        last_exception: Optional[Exception] = None

        for attempt_idx, candidate_id in enumerate(candidate_ids):
            entry = self.registry.get(candidate_id)
            if not entry:
                continue

            logger.info(
                "Adaptive execution attempt %d/%d using %s (%s)",
                attempt_idx + 1,
                len(candidate_ids),
                entry.id,
                entry.capability_tier.value,
            )

            t_start = perf_counter()
            try:
                result = executor_fn(entry.provider, entry.model_name, entry.base_url)

                if attempt_idx > 0:
                    decision.fallback_used = True
                    decision.selected_api = entry.id
                    decision.provider = entry.provider
                    decision.model = entry.model_name
                    decision.latency_tier = entry.latency_tier
                    decision.estimated_cost_tier = entry.cost_tier
                    logger.info(
                        "Fallback succeeded with %s on attempt %d",
                        entry.id,
                        attempt_idx + 1,
                    )

                return result, decision

            except Exception as exc:
                last_exception = exc
                duration_ms = (perf_counter() - t_start) * 1000
                sanitized_err = sanitize_secrets(str(exc))
                error_type = type(exc).__name__

                next_candidate = (
                    candidate_ids[attempt_idx + 1] if attempt_idx + 1 < len(candidate_ids) else None
                )

                event = FallbackEvent(
                    attempt=attempt_idx + 1,
                    failed_api=entry.id,
                    error_type=error_type,
                    error_message_sanitized=sanitized_err,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    recovered_with=next_candidate,
                )
                decision.fallback_events.append(event)

                logger.warning(
                    "Model %s failed after %.1fms (%s: %s). Next fallback: %s",
                    entry.id,
                    duration_ms,
                    error_type,
                    sanitized_err,
                    next_candidate or "none",
                )

                # Degrade model health temporarily
                self.registry.set_health(entry.id, "degraded")

        msg = (
            f"All {len(candidate_ids)} candidate model attempts failed. "
            f"Primary: {candidate_ids[0]}. Last error: {sanitize_secrets(str(last_exception))}"
        )
        raise AdaptiveExecutionError(msg, decision.fallback_events)
