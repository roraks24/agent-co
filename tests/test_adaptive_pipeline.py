"""Unit and integration tests for the Adaptive API Selection Pipeline."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from agent.adaptive import (
    AdaptiveExecutionError,
    AdaptivePipeline,
    AdaptiveSettings,
    ApiRegistry,
    ApiRegistryEntry,
    CostTier,
    ExecutionAndFallbackHandler,
    GLOBAL_ADAPTIVE_PIPELINE,
    LatencyTier,
    Modality,
    RequirementExtractor,
    SelectionDecision,
    SelectionEngine,
    TaskClassifier,
    TaskIntakeRequest,
    TaskTier,
    build_response_selection_metadata,
    sanitize_secrets,
)
from agent.api import app


class TaskClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = TaskClassifier()

    def test_low_request_classification(self) -> None:
        low_prompts = [
            "What is an abstract base class in Python?",
            "Format json and fix typos in this schema",
            "Summarize in 2 sentences: Artificial intelligence has grown rapidly.",
            "List 5 examples of sorting algorithms",
            "Translate this greeting to Spanish",
        ]
        for prompt in low_prompts:
            req = TaskIntakeRequest(user_prompt=prompt)
            result = self.classifier.classify(req)
            self.assertEqual(
                result.task_tier,
                TaskTier.LOW,
                f"Prompt failed LOW classification: '{prompt}' (got {result.task_tier}, signals={result.signals})",
            )
            self.assertGreater(result.confidence, 0.6)
            self.assertTrue(len(result.signals) > 0)

    def test_high_request_classification(self) -> None:
        high_prompts = [
            "Design an enterprise microservices architecture with comprehensive deep research and security audit.",
            "Refactor entire repository across multiple files with formal verification and comparative benchmark.",
            "Build full-stack production-ready platform with distributed system design and end-to-end implementation.",
        ]
        for prompt in high_prompts:
            req = TaskIntakeRequest(user_prompt=prompt)
            result = self.classifier.classify(req)
            self.assertEqual(
                result.task_tier,
                TaskTier.HIGH,
                f"Prompt failed HIGH classification: '{prompt}' (got {result.task_tier}, signals={result.signals})",
            )
            self.assertGreater(result.confidence, 0.7)
            self.assertTrue(len(result.signals) > 0)

    def test_ambiguous_request_receives_sensible_default(self) -> None:
        ambiguous_prompts = [
            "process data items",
            "run pipeline step",
            "execute action",
        ]
        for prompt in ambiguous_prompts:
            req = TaskIntakeRequest(user_prompt=prompt)
            result = self.classifier.classify(req)
            self.assertEqual(result.task_tier, TaskTier.MEDIUM)
            self.assertIn("neutral", "".join(result.signals).lower())
            self.assertIn("defaulted", result.reason.lower())

    def test_multimodal_file_input_forces_high_tier(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="Inspect this",
            file_inputs=["image.png"],
        )
        result = self.classifier.classify(req)
        self.assertEqual(result.task_tier, TaskTier.HIGH)
        self.assertIn("multimodal", "".join(result.signals).lower())


class SelectionEngineRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ApiRegistry()
        self.engine = SelectionEngine(registry=self.registry)
        self.extractor = RequirementExtractor()
        self.classifier = TaskClassifier()

    def test_low_request_routes_to_lightweight_api(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="What is the definition of polymorphism? Format in 2 sentences.",
            api_key="gsk_test_groq_key_12345678901234567890",
        )
        classification = self.classifier.classify(req)
        requirements = self.extractor.extract(req, classification)
        decision = self.engine.select(req, classification, requirements)

        self.assertEqual(decision.task_tier, TaskTier.LOW)
        selected_model = self.registry.get(decision.selected_api)
        self.assertIsNotNone(selected_model)
        self.assertEqual(selected_model.capability_tier, TaskTier.LOW)
        # Strict rule: high-performance models MUST NOT be selected
        self.assertNotEqual(decision.selected_api, "openai/gpt-4o")
        self.assertNotEqual(decision.selected_api, "anthropic/claude-3-5-sonnet")

    def test_high_request_routes_to_high_performance_api(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="Deep research and full-stack system design for enterprise monorepo with security audit.",
            api_key="sk-test_openai_key_12345678901234567890",
        )
        classification = self.classifier.classify(req)
        requirements = self.extractor.extract(req, classification)
        decision = self.engine.select(req, classification, requirements)

        self.assertEqual(decision.task_tier, TaskTier.HIGH)
        selected_model = self.registry.get(decision.selected_api)
        self.assertIsNotNone(selected_model)
        self.assertEqual(selected_model.capability_tier, TaskTier.HIGH)
        # Strict rule: lightweight models MUST NOT be selected
        self.assertNotEqual(decision.selected_api, "groq/llama-3.1-8b-instant")
        self.assertNotEqual(decision.selected_api, "groq/gemma2-9b-it")

    def test_multimodal_vision_requirement_selects_multimodal_candidate(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="Examine architecture diagram in uploaded image",
            modalities=["VISION"],
            api_key="sk-test_openai_key_12345678901234567890",
        )
        classification = self.classifier.classify(req)
        requirements = self.extractor.extract(req, classification)
        decision = self.engine.select(req, classification, requirements)

        selected_model = self.registry.get(decision.selected_api)
        self.assertIsNotNone(selected_model)
        self.assertIn(Modality.VISION, selected_model.supported_modalities)

    def test_explicit_user_model_preference_honored(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="Write a Python script",
            preferred_model="llama-3.3-70b-versatile",
            api_key="gsk_test_groq_key_12345678901234567890",
        )
        classification = self.classifier.classify(req)
        requirements = self.extractor.extract(req, classification)
        decision = self.engine.select(req, classification, requirements)

        self.assertEqual(decision.model, "llama-3.3-70b-versatile")
        self.assertEqual(decision.provider, "groq")

    def test_fallback_chain_construction(self) -> None:
        req = TaskIntakeRequest(
            user_prompt="Build microservice API endpoint",
            api_key="gsk_test_groq_key_12345678901234567890",
        )
        classification = self.classifier.classify(req)
        requirements = self.extractor.extract(req, classification)
        decision = self.engine.select(req, classification, requirements)

        self.assertGreater(len(decision.fallback_chain), 0)
        self.assertNotIn(decision.selected_api, decision.fallback_chain)


class ExecutionAndFallbackHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ApiRegistry()
        self.handler = ExecutionAndFallbackHandler(registry=self.registry)

    def test_successful_primary_execution(self) -> None:
        decision = SelectionDecision(
            selected_api="groq/llama-3.1-8b-instant",
            provider="groq",
            model="llama-3.1-8b-instant",
            task_tier=TaskTier.LOW,
            reason="Primary test choice",
            fallback_chain=["local/llama3.2:3b"],
        )

        def mock_executor(provider: str, model_name: str, base_url: str | None) -> str:
            return f"Result from {provider}:{model_name}"

        result, final_decision = self.handler.execute_with_fallback(
            decision=decision,
            executor_fn=mock_executor,
            user_api_key="gsk_test_valid_key_12345678901234",
        )

        self.assertEqual(result, "Result from groq:llama-3.1-8b-instant")
        self.assertFalse(final_decision.fallback_used)
        self.assertEqual(len(final_decision.fallback_events), 0)

    def test_fallback_recovery_when_primary_fails(self) -> None:
        decision = SelectionDecision(
            selected_api="groq/llama-3.1-8b-instant",
            provider="groq",
            model="llama-3.1-8b-instant",
            task_tier=TaskTier.LOW,
            reason="Primary test choice",
            fallback_chain=["openai/gpt-4o-mini", "local/llama3.2:3b"],
        )

        attempts: list[str] = []

        def fake_executor(provider: str, model_name: str, base_url: str | None) -> str:
            attempts.append(model_name)
            if model_name == "llama-3.1-8b-instant":
                # Primary fails with rate limit error
                raise RuntimeError("RateLimitError: 429 Too Many Requests with secret key gsk_SECRET123456789")
            # Fallback succeeds
            return f"Success with {model_name}"

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890123456"}):
            result, final_decision = self.handler.execute_with_fallback(
                decision=decision,
                executor_fn=fake_executor,
                user_api_key="gsk_test_key_12345678901234",
            )

        self.assertEqual(result, "Success with gpt-4o-mini")
        self.assertTrue(final_decision.fallback_used)
        self.assertEqual(final_decision.selected_api, "openai/gpt-4o-mini")
        self.assertEqual(len(final_decision.fallback_events), 1)

        # Check secret redaction in logged error
        event = final_decision.fallback_events[0]
        self.assertEqual(event.failed_api, "groq/llama-3.1-8b-instant")
        self.assertNotIn("gsk_SECRET123456789", event.error_message_sanitized)
        self.assertIn("***REDACTED_SECRET***", event.error_message_sanitized)

    def test_all_fallbacks_fail_raises_adaptive_execution_error(self) -> None:
        decision = SelectionDecision(
            selected_api="groq/llama-3.1-8b-instant",
            provider="groq",
            model="llama-3.1-8b-instant",
            task_tier=TaskTier.LOW,
            reason="Primary test choice",
            fallback_chain=["local/llama3.2:3b"],
        )

        def all_fail(provider: str, model_name: str, base_url: str | None) -> str:
            raise ConnectionError(f"Connection failed for {model_name}")

        with self.assertRaises(AdaptiveExecutionError) as ctx:
            self.handler.execute_with_fallback(
                decision,
                all_fail,
                user_api_key="gsk_test_groq_key_1234567890123456",
            )

        self.assertEqual(len(ctx.exception.events), 2)


class SecretSanitizationTests(unittest.TestCase):
    def test_secret_scrubbing(self) -> None:
        raw_text = (
            "Failed with gsk_abcdef123456789012345 and sk-proj-1234567890abcdef1234 "
            "Bearer mysecrettoken123456789"
        )
        sanitized = sanitize_secrets(raw_text)
        self.assertNotIn("gsk_abcdef123456789012345", sanitized)
        self.assertNotIn("sk-proj-1234567890abcdef1234", sanitized)
        self.assertNotIn("mysecrettoken123456789", sanitized)
        self.assertIn("***REDACTED_SECRET***", sanitized)

    def test_missing_api_key_handled_safely(self) -> None:
        registry = ApiRegistry()
        entry = registry.get("openai/gpt-4o")

        with patch.dict(os.environ, {}, clear=True):
            has_creds = registry.has_credentials(entry, provided_api_key=None)
            source = registry.resolve_credential_source(entry, provided_api_key=None)

            self.assertFalse(has_creds)
            self.assertEqual(source, "missing")


class AdaptiveApiEndpointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_classify_endpoint_low_and_high(self) -> None:
        # LOW
        resp_low = self.client.post("/v1/adaptive/classify", json={"user_prompt": "What is a python list?"})
        self.assertEqual(resp_low.status_code, 200)
        data_low = resp_low.json()
        self.assertEqual(data_low["task_tier"], "LOW")
        self.assertGreater(data_low["confidence"], 0.6)

        # HIGH
        resp_high = self.client.post(
            "/v1/adaptive/classify",
            json={"user_prompt": "Deep research comparative benchmark with security audit and full-stack architecture."},
        )
        self.assertEqual(resp_high.status_code, 200)
        data_high = resp_high.json()
        self.assertEqual(data_high["task_tier"], "HIGH")

    def test_select_endpoint(self) -> None:
        payload = {
            "user_prompt": "Format this json payload",
            "desired_quality": "low",
            "api_key": "gsk_test_sample_key_1234567890123456",
        }
        resp = self.client.post("/v1/adaptive/select", json=payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("decision", body)
        self.assertIn("requirements", body)
        self.assertIn("metadata", body)
        self.assertEqual(body["decision"]["task_tier"], "LOW")
        self.assertFalse(body["decision"]["fallback_used"])

    def test_registry_endpoint(self) -> None:
        resp = self.client.get("/v1/adaptive/registry")
        self.assertEqual(resp.status_code, 200)
        models = resp.json()
        self.assertGreater(len(models), 5)
        for m in models:
            self.assertIn("id", m)
            self.assertIn("capability_tier", m)
            self.assertIn("context_window", m)
            self.assertNotIn("required_env_vars", m)  # sensitive keys excluded


class WorkflowAdaptiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("agent.api.run_workflow")
    @patch("agent.api.build_chat_model")
    def test_generate_returns_adaptive_selection_metadata(
        self, mock_build_model: MagicMock, mock_run_wf: MagicMock
    ) -> None:
        mock_build_model.return_value = MagicMock()
        mock_run_wf.return_value = {
            "status": "DONE",
            "objective_status": "SUCCESS",
            "final_summary": "Test completed successfully.",
        }

        resp = self.client.post(
            "/generate",
            json={
                "user_prompt": "What is Python list comprehension?",
                "api_key": "gsk_test_groq_key_1234567890123456",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("adaptive_selection", data)
        self.assertIsNotNone(data["adaptive_selection"])
        self.assertEqual(data["adaptive_selection"]["task_tier"], "LOW")
        self.assertEqual(data["adaptive_selection"]["provider"], "groq")
        self.assertFalse(data["adaptive_selection"]["fallback_used"])

    @patch("agent.api.run_workflow")
    @patch("agent.api.build_chat_model")
    def test_generate_honors_explicit_model_override(
        self, mock_build_model: MagicMock, mock_run_wf: MagicMock
    ) -> None:
        mock_build_model.return_value = MagicMock()
        mock_run_wf.return_value = {
            "status": "DONE",
            "objective_status": "SUCCESS",
        }

        resp = self.client.post(
            "/generate",
            json={
                "user_prompt": "Write a python script",
                "model": "llama-3.3-70b-versatile",
                "api_key": "gsk_test_groq_key_1234567890123456",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Verify build_chat_model was called with the user's explicit model
        mock_build_model.assert_called_once()
        call_kwargs = mock_build_model.call_args.kwargs
        self.assertEqual(call_kwargs.get("model"), "llama-3.3-70b-versatile")

    @patch("agent.api.astream_workflow")
    @patch("agent.api.build_chat_model")
    def test_stream_emits_adaptive_selection_event(
        self, mock_build_model: MagicMock, mock_astream: MagicMock
    ) -> None:
        mock_build_model.return_value = MagicMock()

        async def fake_stream(*args, **kwargs):
            if False:
                yield None

        mock_astream.side_effect = fake_stream

        resp = self.client.post(
            "/stream",
            json={
                "user_prompt": "What is polymorphism in OOP?",
                "api_key": "gsk_test_groq_key_1234567890123456",
            },
        )
        self.assertEqual(resp.status_code, 200)
        sse_text = resp.text
        self.assertIn("event: adaptive_selection", sse_text)
        self.assertIn('"task_tier": "LOW"', sse_text)
        self.assertIn("event: run_started", sse_text)

    def test_cross_provider_credential_safety(self) -> None:
        """Ensure a Groq key is never treated as a valid OpenAI or Anthropic key."""
        registry = ApiRegistry()
        openai_model = registry.get("openai/gpt-4o")
        anthropic_model = registry.get("anthropic/claude-3-5-sonnet")

        with patch.dict(os.environ, {}, clear=True):
            groq_key = "gsk_only_valid_for_groq_12345678901234"
            # OpenAI and Anthropic must reject the Groq key
            self.assertFalse(registry.has_credentials(openai_model, provided_api_key=groq_key))
            self.assertFalse(registry.has_credentials(anthropic_model, provided_api_key=groq_key))


if __name__ == "__main__":
    unittest.main()
