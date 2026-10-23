"""Task complexity classification engine for adaptive API routing."""

from __future__ import annotations

import re
from typing import Optional
from .models import ClassificationResult, TaskIntakeRequest, TaskTier


class TaskClassifier:
    """Classifies user requests into LOW, MEDIUM, or HIGH complexity tiers."""

    # Explicit keyword and pattern indicators for LOW tier
    LOW_PATTERNS = [
        r"\b(?:what is|who is|when was|where is|define|definition of)\b",
        r"\b(?:fix typo|spelling|grammar|proofread)\b",
        r"\b(?:format json|pretty print|beautify|indent|minify)\b",
        r"\b(?:summarize in \d+ (?:sentences?|words?)|one-sentence summary|tldr)\b",
        r"\b(?:translate\b.*?\bto \w+)\b",
        r"\b(?:convert (?:to uppercase|to lowercase|to title case))\b",
        r"\b(?:simple regex|regex to match)\b",
        r"\b(?:hello|hi|hey|greetings|howdy)\b",
        r"\b(?:list \d+ (?:names|items|examples|ideas|keywords))\b",
        r"\b(?:explain (?:simply|like i'm 5|eli5))\b",
        r"\b(?:classification|categorize this)\b",
    ]

    # Explicit keyword and pattern indicators for HIGH tier
    HIGH_PATTERNS = [
        r"\b(?:deep research|comprehensive (?:analysis|report|study))\b",
        r"\b(?:system design|enterprise architecture|distributed system)\b",
        r"\b(?:full-?stack|microservices?|monorepo)\b",
        r"\b(?:refactor (?:entire|whole|codebase|repository|project))\b",
        r"\b(?:security (?:audit|vulnerability assessment|penetration test))\b",
        r"\b(?:multimodal|image analysis|diagram generation|chart analysis)\b",
        r"\b(?:multi-?file|across multiple files|entire directory)\b",
        r"\b(?:comparative benchmark|cross-framework comparison)\b",
        r"\b(?:formal verification|mathematical proof|high-accuracy)\b",
        r"\b(?:legal compliance|financial modeling|regulatory analysis)\b",
        r"\b(?:end-to-end implementation|production-ready platform)\b",
    ]

    # Explicit keyword and pattern indicators for MEDIUM tier
    MEDIUM_PATTERNS = [
        r"\b(?:write a (?:script|module|class|function|program|tool))\b",
        r"\b(?:build a (?:minimal|simple|basic) (?:app|cli|api|fastapi|express))\b",
        r"\b(?:parse and (?:extract|calculate|plot|analyze))\b",
        r"\b(?:implement|implementation step|unit tests?|integration tests?)\b",
        r"\b(?:search (?:the web|online|github)|fetch (?:data|url))\b",
        r"\b(?:data analysis|descriptive statistics|csv analysis)\b",
        r"\b(?:create (?:an? )?endpoint|rest api|crud)\b",
    ]

    def __init__(self, default_tier: str = "MEDIUM"):
        self.default_tier = TaskTier(default_tier.upper()) if default_tier.upper() in TaskTier.__members__ else TaskTier.MEDIUM

    def classify(self, request: TaskIntakeRequest) -> ClassificationResult:
        """Classify intake request based on prompt text, metadata, and multimodal inputs."""
        prompt = request.user_prompt.strip()
        p_lower = prompt.lower()
        signals: list[str] = []

        # 1. Metadata overrides and explicit cues
        if request.task_type:
            tt_norm = request.task_type.lower()
            if any(k in tt_norm for k in ("research", "architecture", "audit", "high", "complex")):
                signals.append(f"metadata:task_type='{request.task_type}' indicates HIGH complexity")
                return ClassificationResult(
                    task_tier=TaskTier.HIGH,
                    confidence=0.92,
                    signals=signals,
                    reason=f"Task type explicitly set to '{request.task_type}'.",
                )
            if any(k in tt_norm for k in ("simple", "format", "grammar", "low")):
                signals.append(f"metadata:task_type='{request.task_type}' indicates LOW complexity")
                return ClassificationResult(
                    task_tier=TaskTier.LOW,
                    confidence=0.90,
                    signals=signals,
                    reason=f"Task type explicitly set to '{request.task_type}'.",
                )

        # 2. Multimodal inputs (file/images attached)
        if request.file_inputs or (request.modalities and "vision" in [m.lower() for m in request.modalities]):
            signals.append("multimodal: file inputs or vision modality required")
            return ClassificationResult(
                task_tier=TaskTier.HIGH,
                confidence=0.95,
                signals=signals,
                reason="Task requires multimodal perception and file/vision processing.",
            )

        # 3. Context length cues
        prompt_words = len(prompt.split())
        approx_tokens = int(prompt_words * 1.3)
        if approx_tokens > 6000 or (request.context_length and request.context_length > 8000):
            signals.append(f"context: massive input context (~{approx_tokens} tokens)")
            return ClassificationResult(
                task_tier=TaskTier.HIGH,
                confidence=0.92,
                signals=signals,
                reason="Input context exceeds standard lightweight window; requires large-context model.",
            )

        # 4. Pattern matching scoring
        low_score = 0
        med_score = 0
        high_score = 0

        for pat in self.HIGH_PATTERNS:
            if re.search(pat, p_lower):
                high_score += 3
                matched = re.search(pat, p_lower).group(0)
                signals.append(f"high_indicator: '{matched}'")

        for pat in self.MEDIUM_PATTERNS:
            if re.search(pat, p_lower):
                med_score += 2
                matched = re.search(pat, p_lower).group(0)
                signals.append(f"med_indicator: '{matched}'")

        for pat in self.LOW_PATTERNS:
            if re.search(pat, p_lower):
                low_score += 3
                matched = re.search(pat, p_lower).group(0)
                signals.append(f"low_indicator: '{matched}'")

        # 5. Structural and linguistic cues
        # Multi-step instructions (e.g. 1., 2., 3., 4.)
        numbered_steps = len(re.findall(r"^\s*\d+[\.\)]\s+", prompt, re.MULTILINE))
        if numbered_steps >= 3:
            high_score += 2
            signals.append(f"multi_step: {numbered_steps} numbered steps detected")
        elif numbered_steps >= 1:
            med_score += 1
            signals.append("multi_step: numbered instruction step detected")

        # Multi-file references (e.g. file.py, style.css, index.html)
        file_refs = len(re.findall(r"\b[\w-]+\.(?:py|html|css|js|ts|json|md|sql|yaml|sh)\b", p_lower))
        if file_refs >= 3:
            high_score += 3
            signals.append(f"file_refs: {file_refs} distinct file references")
        elif file_refs >= 1:
            med_score += 1
            signals.append(f"file_refs: {file_refs} file reference")

        # Code block presence
        code_blocks = len(re.findall(r"```[\s\S]*?```", prompt))
        if code_blocks >= 2:
            med_score += 2
            signals.append(f"code_blocks: {code_blocks} markdown code blocks")
        elif code_blocks == 1:
            med_score += 1

        # Length heuristics
        if low_score > 0 and prompt_words < 12:
            low_score += 1
            signals.append("brevity: concise prompt (<12 words)")
        elif prompt_words > 180:
            high_score += 1
            signals.append("verbosity: extensive prompt length (>180 words)")

        # Desired quality override
        if request.desired_quality:
            dq = request.desired_quality.lower()
            if dq in ("maximum", "high"):
                high_score += 3
                signals.append(f"metadata:desired_quality='{dq}'")
            elif dq == "low":
                low_score += 2
                signals.append(f"metadata:desired_quality='{dq}'")

        # 6. Adjudication & Confidence Calculation
        total_score = low_score + med_score + high_score
        
        if high_score > 0 and high_score >= med_score and high_score > low_score:
            confidence = min(0.98, 0.65 + (high_score * 0.06))
            return ClassificationResult(
                task_tier=TaskTier.HIGH,
                confidence=round(confidence, 2),
                signals=signals,
                reason="Complex multi-step requirements, architectural depth, or high-accuracy requirements detected.",
            )

        if low_score > 0 and low_score > high_score and low_score >= med_score:
            confidence = min(0.98, 0.65 + (low_score * 0.07))
            return ClassificationResult(
                task_tier=TaskTier.LOW,
                confidence=round(confidence, 2),
                signals=signals,
                reason="Lightweight formatting, single question, brief summary, or basic text manipulation detected.",
            )

        if med_score > 0:
            confidence = min(0.95, 0.60 + (med_score * 0.06))
            return ClassificationResult(
                task_tier=TaskTier.MEDIUM,
                confidence=round(confidence, 2),
                signals=signals,
                reason="Moderate implementation, script generation, structured tool use, or data analysis detected.",
            )

        # Ambiguous request handling - sensible default with transparent signal
        signals.append("neutral: no strong complexity or simplicity indicators")
        return ClassificationResult(
            task_tier=self.default_tier,
            confidence=0.55,
            signals=signals,
            reason=f"Ambiguous request without dominant complexity signals; defaulted to balanced {self.default_tier.value} tier.",
        )
