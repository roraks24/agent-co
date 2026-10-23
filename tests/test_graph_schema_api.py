from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from agent.api import app


class GraphSchemaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_graph_schema_shape(self) -> None:
        response = self.client.get("/graph/schema")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("graph_id", payload)
        self.assertIn("nodes", payload)
        self.assertIn("edges", payload)
        self.assertIn("state_model", payload)
        self.assertIn("activity_model", payload)

        node_ids = {node["id"] for node in payload["nodes"]}
        self.assertEqual(node_ids, {"planner", "architect", "coder"})

        edges = {(edge["source"], edge["target"]) for edge in payload["edges"]}
        self.assertIn(("planner", "architect"), edges)
        self.assertIn(("architect", "coder"), edges)
        self.assertIn(("coder", "coder"), edges)

    def test_graph_schema_models(self) -> None:
        response = self.client.get("/graph/schema")
        payload = response.json()

        self.assertEqual(payload["state_model"], ["idle", "active", "completed", "error"])
        self.assertEqual(payload["activity_model"]["min"], 0.0)
        self.assertEqual(payload["activity_model"]["max"], 1.0)


if __name__ == "__main__":
    unittest.main()
