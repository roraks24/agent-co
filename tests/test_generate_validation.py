from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import agent.api as api_module
from agent.api import app
from agent.prompts import MAX_MUTABLE_PROMPT_CHARS


class GenerateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_oversized_prompt_override_returns_422(self) -> None:
        oversized = "x" * (MAX_MUTABLE_PROMPT_CHARS + 1)
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
            "prompt_overrides": {"planner": oversized},
        }

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        mock_build.assert_not_called()
        mock_run.assert_not_called()

    def test_oversized_legacy_mutable_prompt_returns_422(self) -> None:
        oversized = "x" * (MAX_MUTABLE_PROMPT_CHARS + 1)
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
            "mutable_prompt": oversized,
        }

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        mock_build.assert_not_called()
        mock_run.assert_not_called()

    def test_unknown_override_node_returns_422(self) -> None:
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
            "prompt_overrides": {"reviewer": "invalid"},
        }

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        mock_build.assert_not_called()
        mock_run.assert_not_called()

    def test_valid_payload_passes_exact_overrides_to_workflow(self) -> None:
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
            "prompt_overrides": {
                "planner": "planner mutable",
                "architect": "architect mutable",
                "coder": "coder mutable",
            },
            "mutable_prompt": "legacy mutable",
            "recursion_limit": 55,
        }

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            mock_build.return_value = object()
            mock_run.return_value = {"status": "DONE", "plan": None, "detailed_ins": None}

            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "DONE")
        self.assertTrue(mock_build.called)
        self.assertTrue(mock_run.called)

        run_args = mock_run.call_args.args
        self.assertEqual(run_args[0], payload["user_prompt"])
        self.assertEqual(run_args[2], payload["recursion_limit"])
        self.assertEqual(run_args[3], payload["mutable_prompt"])
        self.assertEqual(run_args[4], payload["prompt_overrides"])

    def test_api_key_header_fallback_is_supported(self) -> None:
        payload = {"user_prompt": "Build a todo app"}
        headers = {"X-API-KEY": "header-key"}

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            mock_build.return_value = object()
            mock_run.return_value = {"status": "DONE", "plan": None, "detailed_ins": None}

            response = self.client.post("/generate", json=payload, headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_build.called)
        self.assertEqual(mock_build.call_args.kwargs["api_key"], "header-key")

    def test_missing_api_key_body_and_header_returns_422(self) -> None:
        payload = {"user_prompt": "Build a todo app"}

        with patch("agent.api.build_chat_model") as mock_build, patch(
            "agent.api.run_workflow"
        ) as mock_run:
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        mock_build.assert_not_called()
        mock_run.assert_not_called()

    def test_generate_hides_exception_details_when_verbose_errors_disabled(self) -> None:
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
        }

        with patch.object(api_module.SECURITY_CONFIG, "expose_verbose_errors", False), patch(
            "agent.api.build_chat_model"
        ) as mock_build, patch(
            "agent.api.run_workflow",
            side_effect=RuntimeError("sensitive-debug-message"),
        ):
            mock_build.return_value = object()
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "workflow_error")
        self.assertNotIn("sensitive-debug-message", payload["error"]["message"])
        details = payload["error"].get("details") or {}
        self.assertIn("run_id", details)
        self.assertEqual(details.get("error_type"), "unknown_error")
        self.assertTrue(isinstance(details.get("hint"), str))
        self.assertNotIn("exception_chain", details)

    def test_generate_classifies_connection_failure(self) -> None:
        payload = {
            "user_prompt": "Build a todo app",
            "api_key": "test-key",
        }

        with patch.object(api_module.SECURITY_CONFIG, "expose_verbose_errors", False), patch(
            "agent.api.build_chat_model"
        ) as mock_build, patch(
            "agent.api.run_workflow",
            side_effect=RuntimeError("connection refused by upstream"),
        ):
            mock_build.return_value = object()
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["error"]["code"], "workflow_error")
        details = body["error"].get("details") or {}
        self.assertEqual(details.get("error_type"), "connection_error")
        self.assertTrue(isinstance(details.get("hint"), str))
        self.assertIn("run_id", details)


if __name__ == "__main__":
    unittest.main()
