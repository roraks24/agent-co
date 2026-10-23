from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from agent.api import app


class PromptSchemaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_schema_endpoints_return_same_payload(self) -> None:
        response_api = self.client.get("/api/prompts")
        response_public = self.client.get("/prompts/schema")
        response_versioned = self.client.get("/v1/prompts/schema")

        self.assertEqual(response_api.status_code, 200)
        self.assertEqual(response_public.status_code, 200)
        self.assertEqual(response_versioned.status_code, 200)
        self.assertEqual(response_api.json(), response_public.json())
        self.assertEqual(response_public.json(), response_versioned.json())

    def test_schema_payload_shape(self) -> None:
        response = self.client.get("/api/prompts")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("nodes", payload)
        self.assertIn("policy", payload)
        self.assertTrue({"planner", "architect", "coder"}.issubset(set(payload["nodes"].keys())))
        self.assertIn("immutable_rules", payload["policy"])
        self.assertIn("max_mutable_prompt_chars", payload["policy"])


if __name__ == "__main__":
    unittest.main()
