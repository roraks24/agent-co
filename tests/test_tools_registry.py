"""Tests for Agent Co Tool Registry, argument validation, and secret redaction."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from agent.tools_registry import (
    GLOBAL_TOOL_REGISTRY,
    ToolRegistry,
    execute_web_search,
    redact_sensitive_data,
)
from agent.workspace import workspace_context


class ToolRegistryTests(unittest.TestCase):
    def test_registered_default_tools(self) -> None:
        tools = GLOBAL_TOOL_REGISTRY.list_tools()
        names = {t["name"] for t in tools}
        self.assertIn("web_search", names)
        self.assertIn("fetch_url_content", names)
        self.assertIn("write_file", names)
        self.assertIn("read_file", names)
        self.assertIn("list_files", names)

    def test_invalid_tool_arguments_rejected(self) -> None:
        # web_search requires query
        result = GLOBAL_TOOL_REGISTRY.execute("web_search", {})
        self.assertFalse(result["success"])
        self.assertIn("ValidationError", result["error"])

        # write_file requires path and content
        result = GLOBAL_TOOL_REGISTRY.execute("write_file", {"path": "test.txt"})
        self.assertFalse(result["success"])
        self.assertIn("ValidationError", result["error"])

    def test_unknown_tool_returns_error(self) -> None:
        result = GLOBAL_TOOL_REGISTRY.execute("non_existent_tool", {})
        self.assertFalse(result["success"])
        self.assertIn("is not registered", result["error"])

    def test_file_tools_execution_in_workspace(self) -> None:
        with workspace_context("test-tool-workspace"):
            # Write file
            write_res = GLOBAL_TOOL_REGISTRY.execute(
                "write_file",
                {"path": "report.md", "content": "# Research Report\nContent here."},
            )
            self.assertTrue(write_res["success"])
            self.assertEqual(write_res["data"]["path"], "report.md")

            # Read file
            read_res = GLOBAL_TOOL_REGISTRY.execute("read_file", {"path": "report.md"})
            self.assertTrue(read_res["success"])
            self.assertIn("Research Report", read_res["data"]["content"])

            # List files
            list_res = GLOBAL_TOOL_REGISTRY.execute("list_files", {"directory": "."})
            self.assertTrue(list_res["success"])
            self.assertIn("report.md", list_res["data"]["files"])

    def test_secret_redaction(self) -> None:
        sensitive_payload = {
            "query": "search query",
            "api_key": "gsk_secret12345678901234567890",
            "token": "bearer secret-token-xyz",
            "headers": {"Authorization": "Bearer super-secret-token"},
            "nested": {"user_password": "my_password_123"},
        }
        sanitized = redact_sensitive_data(sensitive_payload)
        self.assertEqual(sanitized["query"], "search query")
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["user_password"], "[REDACTED]")

    def test_private_ssrf_blocked_in_fetch_url(self) -> None:
        # Loopback URL
        result = GLOBAL_TOOL_REGISTRY.execute("fetch_url_content", {"url": "http://127.0.0.1:8000/internal"})
        self.assertFalse(result["success"])
        self.assertIn("PermissionError", result["error"])

        # Private IP URL
        result = GLOBAL_TOOL_REGISTRY.execute("fetch_url_content", {"url": "http://192.168.1.1/admin"})
        self.assertFalse(result["success"])
        self.assertIn("PermissionError", result["error"])


class WebSearchTests(unittest.TestCase):
    def test_empty_query_rejected(self) -> None:
        with self.assertRaises(ValueError):
            execute_web_search("")

    def test_mocked_ddgs_search_execution(self) -> None:
        fake_results = [
            {"title": "LangGraph Overview", "href": "https://langchain.com", "body": "Agent orchestration framework."},
            {"title": "CrewAI Agents", "href": "https://crewai.com", "body": "Role-playing agents."},
        ]

        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def text(self, *args, **kwargs):
                return fake_results

        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}), patch("ddgs.DDGS", return_value=FakeDDGS()):
            result = execute_web_search("AI agent frameworks", max_results=2)
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["results"][0]["title"], "LangGraph Overview")
            self.assertEqual(result["results"][1]["title"], "CrewAI Agents")

    def test_tavily_search_execution(self) -> None:
        fake_tavily = MagicMock()
        fake_tavily.search.return_value = {
            "results": [
                {"title": "Tavily LangGraph", "url": "https://langchain.com", "content": "Search result"}
            ]
        }
        with patch.dict(os.environ, {"TAVILY_API_KEY": "fake-tavily-key"}), patch(
            "tavily.TavilyClient", return_value=fake_tavily
        ):
            result = execute_web_search("test query", max_results=1)
            self.assertEqual(result["provider"], "tavily")
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["results"][0]["title"], "Tavily LangGraph")


if __name__ == "__main__":
    unittest.main()
