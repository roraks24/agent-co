"""Adaptive API Selection Pipeline package."""

from .models import (
    ApiRegistryEntry,
    CandidateScore,
    ClassificationResult,
    CostTier,
    ExtractedRequirements,
    FallbackEvent,
    LatencyTier,
    Modality,
    QualityTier,
    SelectionDecision,
    TaskIntakeRequest,
    TaskTier,
)
from .config import AdaptiveSettings, load_adaptive_settings
from .classifier import TaskClassifier
from .extractor import RequirementExtractor
from .registry import ApiRegistry
from .selector import SelectionEngine
from .fallback_handler import AdaptiveExecutionError, ExecutionAndFallbackHandler
from .observability import (
    build_response_selection_metadata,
    log_adaptive_decision,
    sanitize_secrets,
)
from .pipeline import AdaptivePipeline, GLOBAL_ADAPTIVE_PIPELINE

__all__ = [
    "AdaptiveExecutionError",
    "AdaptivePipeline",
    "AdaptiveSettings",
    "ApiRegistry",
    "ApiRegistryEntry",
    "CandidateScore",
    "ClassificationResult",
    "CostTier",
    "ExecutionAndFallbackHandler",
    "ExtractedRequirements",
    "FallbackEvent",
    "GLOBAL_ADAPTIVE_PIPELINE",
    "LatencyTier",
    "Modality",
    "QualityTier",
    "RequirementExtractor",
    "SelectionDecision",
    "SelectionEngine",
    "TaskClassifier",
    "TaskIntakeRequest",
    "TaskTier",
    "build_response_selection_metadata",
    "load_adaptive_settings",
    "log_adaptive_decision",
    "sanitize_secrets",
]
