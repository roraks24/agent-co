"""Weighted selection engine and routing rules for adaptive API selection."""

from __future__ import annotations

import logging
from typing import Optional
from .config import AdaptiveSettings, load_adaptive_settings
from .models import (
    ApiRegistryEntry,
    CandidateScore,
    ClassificationResult,
    CostTier,
    ExtractedRequirements,
    LatencyTier,
    Modality,
    SelectionDecision,
    TaskIntakeRequest,
    TaskTier,
)
from .registry import ApiRegistry

logger = logging.getLogger("rorak.agent.adaptive.selector")


class SelectionEngine:
    """Scores candidate models and applies strict routing rules."""

    def __init__(
        self,
        registry: Optional[ApiRegistry] = None,
        settings: Optional[AdaptiveSettings] = None,
    ):
        self.registry = registry or ApiRegistry()
        self.settings = settings or load_adaptive_settings()

    def select(
        self,
        request: TaskIntakeRequest,
        classification: ClassificationResult,
        requirements: ExtractedRequirements,
    ) -> SelectionDecision:
        """Score eligible candidate models and select the optimal model with fallback chain."""
        models = self.registry.list_all(enabled_only=True)
        tier = classification.task_tier

        candidate_scores: list[CandidateScore] = []
        user_key = (request.api_key or "").strip() or None

        for model in models:
            score_item = self._evaluate_model(
                model=model,
                request=request,
                classification=classification,
                requirements=requirements,
                user_key=user_key,
            )
            candidate_scores.append(score_item)

        # Separate eligible and credentialed candidates
        eligible = [c for c in candidate_scores if c.eligible]

        # Check if caller has credentials for candidates
        with_creds = [
            c for c in eligible
            if self.registry.has_credentials(self.registry.get(c.model_id), user_key)
        ]

        tradeoff_notes: Optional[str] = None
        candidates_pool = with_creds if with_creds else eligible

        if not candidates_pool:
            # Fallback relaxation: If no candidate qualifies strictly, find best closest model
            tradeoff_notes = "No candidate strictly satisfied all criteria with credentials; selected closest available model."
            logger.warning("Adaptive routing tradeoff: %s", tradeoff_notes)
            candidates_pool = candidate_scores

        # Sort primarily by total_score descending
        # Secondary tie-breaker: cost efficiency (higher cost_score = cheaper)
        candidates_pool.sort(key=lambda c: (c.total_score, c.cost_score), reverse=True)

        # Primary selection
        top_candidate = candidates_pool[0]
        selected_entry = self.registry.get(top_candidate.model_id)

        # Construct fallback chain from remaining ranked candidates
        fallback_chain: list[str] = []
        for cand in candidates_pool[1 : 1 + self.settings.fallback_max_retries]:
            if cand.model_id != top_candidate.model_id:
                fallback_chain.append(cand.model_id)

        # Explain selection rationale
        reason = self._generate_selection_reason(
            selected_entry=selected_entry,
            classification=classification,
            top_candidate=top_candidate,
            tradeoff_notes=tradeoff_notes,
        )

        cred_source = self.registry.resolve_credential_source(selected_entry, user_key)

        return SelectionDecision(
            selected_api=selected_entry.id,
            provider=selected_entry.provider,
            model=selected_entry.model_name,
            task_tier=tier,
            reason=reason,
            confidence=classification.confidence,
            candidate_rankings=candidate_scores,
            fallback_chain=fallback_chain,
            fallback_used=False,
            latency_tier=selected_entry.latency_tier,
            estimated_cost_tier=selected_entry.cost_tier,
            resolved_api_key_source=cred_source,
            tradeoff_notes=tradeoff_notes,
        )

    def _evaluate_model(
        self,
        model: ApiRegistryEntry,
        request: TaskIntakeRequest,
        classification: ClassificationResult,
        requirements: ExtractedRequirements,
        user_key: Optional[str],
    ) -> CandidateScore:
        """Score an individual model across tier match, capabilities, latency, cost, and health."""
        ineligible_reasons: list[str] = []

        # 1. Health check
        if model.health_status == "unavailable":
            ineligible_reasons.append("Model marked unavailable")

        # 2. Modality check
        for req_mod in requirements.modal_requirements:
            if req_mod not in model.supported_modalities:
                ineligible_reasons.append(f"Missing required modality: {req_mod.value}")

        # 3. Context window check
        if model.context_window < requirements.required_context_window:
            ineligible_reasons.append(
                f"Context window insufficient ({model.context_window} < {requirements.required_context_window})"
            )

        # 4. Strict tier routing guards
        if self.settings.strict_tier_routing:
            # Prevent using HIGH tier models for simple LOW tier tasks
            if classification.task_tier == TaskTier.LOW and model.capability_tier == TaskTier.HIGH:
                ineligible_reasons.append(
                    "Strict routing guard: Frontier HIGH model forbidden for simple LOW task."
                )
            # Prevent using LOW tier models for complex HIGH tier tasks
            elif classification.task_tier == TaskTier.HIGH and model.capability_tier == TaskTier.LOW:
                ineligible_reasons.append(
                    "Strict routing guard: Lightweight API forbidden for complex HIGH task."
                )

        # 5. Component scoring
        # Tier Match Score
        if model.capability_tier == classification.task_tier:
            tier_match_score = 1.0
        elif (
            (classification.task_tier == TaskTier.MEDIUM and model.capability_tier in (TaskTier.LOW, TaskTier.HIGH))
            or (classification.task_tier == TaskTier.LOW and model.capability_tier == TaskTier.MEDIUM)
            or (classification.task_tier == TaskTier.HIGH and model.capability_tier == TaskTier.MEDIUM)
        ):
            tier_match_score = 0.60
        else:
            tier_match_score = 0.0

        # Capability / Modality Score
        cap_score = 1.0 if not any("modality" in r.lower() for r in ineligible_reasons) else 0.2

        # Context Fit Score
        if model.context_window >= requirements.required_context_window:
            context_fit_score = min(1.0, 0.7 + (model.context_window / (requirements.required_context_window * 4)))
        else:
            context_fit_score = 0.1

        # Latency Score
        latency_map = {
            LatencyTier.ULTRA_FAST: 1.0,
            LatencyTier.FAST: 0.85,
            LatencyTier.MODERATE: 0.60,
            LatencyTier.SLOW: 0.35,
        }
        latency_score = latency_map.get(model.latency_tier, 0.7)
        if requirements.latency_sensitivity == "high":
            # Boost fast models further
            latency_score = latency_score ** 0.8

        # Cost Score (cheaper = higher score)
        cost_map = {
            CostTier.FREE: 1.0,
            CostTier.VERY_LOW: 0.90,
            CostTier.LOW: 0.75,
            CostTier.MEDIUM: 0.50,
            CostTier.HIGH: 0.25,
        }
        cost_score = cost_map.get(model.cost_tier, 0.5)
        if requirements.cost_sensitivity == "high":
            # Favor low-cost/free
            cost_score = min(1.0, cost_score * 1.2)

        # Health Score
        health_score = 1.0 if model.health_status == "healthy" else (0.5 if model.health_status == "degraded" else 0.0)

        # User Preference Score
        preference_score = 0.0
        if request.preferred_model and (
            request.preferred_model.lower() in model.id.lower()
            or request.preferred_model.lower() == model.model_name.lower()
        ):
            preference_score = 1.0
        elif request.preferred_provider and request.preferred_provider.lower() == model.provider.lower():
            preference_score = 0.6

        # Credential penalty if credentials missing
        has_creds = self.registry.has_credentials(model, user_key)
        cred_penalty = 0.0 if has_creds else -0.30

        # Weighted calculation
        total_score = (
            (tier_match_score * self.settings.weight_tier)
            + (cap_score * self.settings.weight_capability)
            + (context_fit_score * self.settings.weight_context)
            + (cost_score * self.settings.weight_cost)
            + (latency_score * self.settings.weight_latency)
            + (health_score * self.settings.weight_health)
            + (preference_score * 0.15)
            + cred_penalty
        )
        total_score = max(0.0, min(1.0, total_score))

        is_eligible = len(ineligible_reasons) == 0

        return CandidateScore(
            model_id=model.id,
            provider=model.provider,
            model_name=model.model_name,
            capability_tier=model.capability_tier,
            total_score=round(total_score, 4),
            eligible=is_eligible,
            tier_match_score=round(tier_match_score, 2),
            capability_score=round(cap_score, 2),
            context_fit_score=round(context_fit_score, 2),
            latency_score=round(latency_score, 2),
            cost_score=round(cost_score, 2),
            health_score=round(health_score, 2),
            preference_score=round(preference_score, 2),
            ineligibility_reason="; ".join(ineligible_reasons) if ineligible_reasons else None,
        )

    def _generate_selection_reason(
        self,
        selected_entry: ApiRegistryEntry,
        classification: ClassificationResult,
        top_candidate: CandidateScore,
        tradeoff_notes: Optional[str],
    ) -> str:
        tier = classification.task_tier.value
        tier_str = "lightweight/cost-effective" if tier == "LOW" else ("balanced multi-step" if tier == "MEDIUM" else "high-performance reasoning")
        
        base_reason = (
            f"Routed to {selected_entry.id} ({tier_str}) matching classified {tier} tier "
            f"(confidence {classification.confidence:.2f}, score {top_candidate.total_score:.2f})."
        )
        if tradeoff_notes:
            base_reason += f" Tradeoff: {tradeoff_notes}"
        return base_reason
