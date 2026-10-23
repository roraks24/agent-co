"""Unified Adaptive API Selection Pipeline orchestrator."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, Optional, TypeVar
from langchain_core.language_models.chat_models import BaseChatModel

from .classifier import TaskClassifier
from .config import AdaptiveSettings, load_adaptive_settings
from .extractor import RequirementExtractor
from .fallback_handler import ExecutionAndFallbackHandler
from .models import (
    ClassificationResult,
    ExtractedRequirements,
    SelectionDecision,
    TaskIntakeRequest,
    TaskTier,
)
from .observability import build_response_selection_metadata, log_adaptive_decision
from .registry import ApiRegistry

logger = logging.getLogger("rorak.agent.adaptive.pipeline")

T = TypeVar("T")


class AdaptivePipeline:
    """End-to-end adaptive API intake, classification, selection, and fallback pipeline."""

    def __init__(
        self,
        registry: Optional[ApiRegistry] = None,
        settings: Optional[AdaptiveSettings] = None,
    ):
        self.settings = settings or load_adaptive_settings()
        self.registry = registry or ApiRegistry()
        self.classifier = TaskClassifier(default_tier=self.settings.default_tier)
        self.extractor = RequirementExtractor()
        
        from .selector import SelectionEngine
        self.selector = SelectionEngine(registry=self.registry, settings=self.settings)
        self.fallback_handler = ExecutionAndFallbackHandler(registry=self.registry)

    def route(
        self,
        request: TaskIntakeRequest,
    ) -> tuple[SelectionDecision, ExtractedRequirements]:
        """Classify, extract requirements, and select the optimal model and fallback chain."""
        t_start = perf_counter()

        # 1. Classify Task Tier
        classification = self.classifier.classify(request)

        # 2. Extract Operational Requirements
        requirements = self.extractor.extract(request, classification)

        # 3. Select Optimal API / Model Key
        decision = self.selector.select(request, classification, requirements)

        duration_ms = (perf_counter() - t_start) * 1000
        log_adaptive_decision(decision, requirements, latency_ms=duration_ms)

        return decision, requirements

    def resolve_chat_model(
        self,
        decision: SelectionDecision,
        user_api_key: Optional[str] = None,
        temperature: float = 0.2,
    ) -> BaseChatModel:
        """Instantiate LangChain BaseChatModel for the selected model using llm_factory."""
        from agent.llm_factory import build_chat_model

        entry = self.registry.get(decision.selected_api)
        base_url = entry.base_url if entry else None

        return build_chat_model(
            api_key=user_api_key,
            model=decision.model,
            temperature=temperature,
            provider=decision.provider,
            base_url=base_url,
        )

    def execute_with_adaptive_fallback(
        self,
        request: TaskIntakeRequest,
        workflow_executor: Callable[[BaseChatModel], T],
        temperature: float = 0.2,
    ) -> tuple[T, SelectionDecision, dict[str, Any]]:
        """Run workflow with automatic fallback to next-best candidate model on failure."""
        t_start = perf_counter()
        decision, requirements = self.route(request)
        user_key = request.api_key

        def _step_executor(provider: str, model_name: str, base_url: Optional[str]) -> T:
            from agent.llm_factory import build_chat_model
            llm = build_chat_model(
                api_key=user_key,
                model=model_name,
                temperature=temperature,
                provider=provider,
                base_url=base_url,
            )
            return workflow_executor(llm)

        result, final_decision = self.fallback_handler.execute_with_fallback(
            decision=decision,
            executor_fn=_step_executor,
            user_api_key=user_key,
        )

        total_latency_ms = (perf_counter() - t_start) * 1000
        metadata = build_response_selection_metadata(
            final_decision,
            latency_ms=total_latency_ms,
        )
        return result, final_decision, metadata


# Global singleton instance
GLOBAL_ADAPTIVE_PIPELINE = AdaptivePipeline()
