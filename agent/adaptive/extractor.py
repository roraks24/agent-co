"""Requirement extraction from intake requests and classification results."""

from __future__ import annotations

import re
from typing import Optional
from .models import (
    ClassificationResult,
    ExtractedRequirements,
    Modality,
    QualityTier,
    TaskIntakeRequest,
    TaskTier,
)


class RequirementExtractor:
    """Extracts operational, resource, modality, and compliance requirements."""

    def extract(
        self,
        request: TaskIntakeRequest,
        classification: Optional[ClassificationResult] = None,
    ) -> ExtractedRequirements:
        prompt = request.user_prompt.strip()
        p_lower = prompt.lower()
        word_count = len(prompt.split())

        # 1. Context window & output estimation
        # Rough token estimate: ~1.3 tokens per word
        input_token_estimate = int(word_count * 1.3)
        if request.context_length:
            input_token_estimate = max(input_token_estimate, request.context_length)

        # Expected output tokens based on task tier
        tier = classification.task_tier if classification else TaskTier.MEDIUM
        if tier == TaskTier.LOW:
            expected_output_tokens = 512
            required_context = max(4096, input_token_estimate + expected_output_tokens + 1024)
        elif tier == TaskTier.MEDIUM:
            expected_output_tokens = 2048
            required_context = max(8192, input_token_estimate + expected_output_tokens + 2048)
        else:  # HIGH
            expected_output_tokens = 4096
            # If long context analysis or full repository
            if input_token_estimate > 4000:
                expected_output_tokens = 8192
            required_context = max(16384, input_token_estimate + expected_output_tokens + 4096)

        # 2. Latency Sensitivity
        latency_sensitivity = "medium"
        if request.max_latency is not None:
            if request.max_latency < 3.0:
                latency_sensitivity = "high"
            elif request.max_latency > 15.0:
                latency_sensitivity = "low"
        elif any(w in p_lower for w in ("asap", "fast", "quick", "instant", "real-time", "interactive")):
            latency_sensitivity = "high"
        elif tier == TaskTier.HIGH and any(w in p_lower for w in ("deep research", "comprehensive", "thorough")):
            latency_sensitivity = "low"

        # 3. Cost Sensitivity
        cost_sensitivity = "medium"
        if request.budget is not None:
            b_str = str(request.budget).lower()
            if b_str in ("free", "0", "zero", "low", "minimal"):
                cost_sensitivity = "high"
            elif b_str in ("high", "unlimited", "maximum"):
                cost_sensitivity = "low"
            else:
                try:
                    num_budget = float(request.budget)
                    if num_budget < 0.01:
                        cost_sensitivity = "high"
                    elif num_budget > 0.50:
                        cost_sensitivity = "low"
                except ValueError:
                    pass
        elif tier == TaskTier.LOW:
            cost_sensitivity = "high"  # prefer cheap/free for simple tasks

        # 4. Accuracy / Quality Requirement
        if request.desired_quality:
            dq = request.desired_quality.lower()
            if dq in ("maximum", "high"):
                accuracy_req = QualityTier.MAXIMUM if dq == "maximum" else QualityTier.HIGH
            elif dq == "low":
                accuracy_req = QualityTier.LOW
            else:
                accuracy_req = QualityTier.BALANCED
        else:
            if tier == TaskTier.HIGH:
                accuracy_req = QualityTier.HIGH
            elif tier == TaskTier.LOW:
                accuracy_req = QualityTier.LOW
            else:
                accuracy_req = QualityTier.BALANCED

        # 5. Modal requirements
        modal_requirements: list[Modality] = [Modality.TEXT]

        if request.modalities:
            for m in request.modalities:
                m_upper = m.strip().upper()
                if m_upper in Modality.__members__:
                    mod_enum = Modality(m_upper)
                    if mod_enum not in modal_requirements:
                        modal_requirements.append(mod_enum)

        # Vision checks
        if request.file_inputs or any(w in p_lower for w in ("image", "screenshot", "diagram", "photo", "picture", "visual", "chart")):
            if Modality.VISION not in modal_requirements:
                modal_requirements.append(Modality.VISION)

        # Tool & Web search checks
        if any(w in p_lower for w in ("search the web", "search online", "latest", "news", "current")):
            if Modality.WEB_SEARCH not in modal_requirements:
                modal_requirements.append(Modality.WEB_SEARCH)
        if any(w in p_lower for w in ("file", "workspace", "directory", "read", "write", "list", "run")):
            if Modality.TOOLS not in modal_requirements:
                modal_requirements.append(Modality.TOOLS)

        # 6. Safety or compliance constraints
        compliance_constraints: list[str] = []
        if any(w in p_lower for w in ("offline", "local only", "air-gapped", "no internet")):
            compliance_constraints.append("offline_local_only")
        if any(w in p_lower for w in ("hipaa", "phi", "medical data", "patient record")):
            compliance_constraints.append("hipaa_compliant")
        if any(w in p_lower for w in ("gdpr", "pii", "personal data", "private")):
            compliance_constraints.append("privacy_sensitive")

        return ExtractedRequirements(
            required_context_window=required_context,
            expected_output_tokens=expected_output_tokens,
            latency_sensitivity=latency_sensitivity,
            cost_sensitivity=cost_sensitivity,
            accuracy_requirement=accuracy_req,
            modal_requirements=modal_requirements,
            compliance_constraints=compliance_constraints,
        )
