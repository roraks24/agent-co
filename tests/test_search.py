"""Tests for the search utility module and its integration with Agent Co."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from agent.search import (
    DEFAULT_WIKI_USER_AGENT,
    WIKIPEDIA_SUMMARY_URL,
    get_wiki_headers,
    search_duckduckgo,
    search_wikipedia_summary,
    unified_search,
)
from agent.tools import get_wikipedia_summary, search_web
from agent.tools_registry import GLOBAL_TOOL_REGISTRY


class SearchUtilityTests(unittest.TestCase):
    def test_get_wiki_headers_defaults(self) -> None:
        with patch.dict(os.environ, {"WIKI_USER_AGENT": "", "WIKI_API_KEY": ""}):
            headers = get_wiki_headers()
            self.assertEqual(headers["User-Agent"], DEFAULT_WIKI_USER_AGENT)
            self.assertEqual(headers["Accept"], "application/json")
            self.assertNotIn("Authorization", headers)

    def test_get_wiki_headers_with_env_overrides(self) -> None:
        custom_ua = "CustomResearchAgent/2.0 (test@example.com)"
        custom_key = "test-wiki-token-123"
        with patch.dict(os.environ, {"WIKI_USER_AGENT": custom_ua, "WIKI_API_KEY": custom_key}):
            headers = get_wiki_headers()
            self.assertEqual(headers["User-Agent"], custom_ua)
            self.assertEqual(headers["Authorization"], f"Bearer {custom_key}")

    def test_search_duckduckgo_validation(self) -> None:
        with self.assertRaises(ValueError):
            search_duckduckgo("   ")

    def test_search_duckduckgo_mocked(self) -> None:
        fake_results = [
            {"title": "FastAPI Guide", "href": "https://fastapi.tiangolo.com", "body": "FastAPI framework."},
            {"title": "LangGraph Doc", "href": "https://langchain.com", "body": "Build stateful multi-agent apps."},
        ]

        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def text(self, query, max_results=5):
                return fake_results

        with patch("agent.search.DDGS", return_value=FakeDDGS()):
            results = search_duckduckgo("FastAPI LangGraph", max_results=2)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["title"], "FastAPI Guide")
            self.assertEqual(results[0]["url"], "https://fastapi.tiangolo.com")
            self.assertEqual(results[0]["snippet"], "FastAPI framework.")

    def test_search_wikipedia_summary_validation(self) -> None:
        with self.assertRaises(ValueError):
            search_wikipedia_summary("")

    @patch("agent.search.requests.get")
    def test_search_wikipedia_summary_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Artificial intelligence",
            "description": "Intelligence demonstrated by machines",
            "extract": "Artificial intelligence is the intelligence of machines or software.",
            "content_urls": {
                "desktop": {
                    "page": "https://en.wikipedia.org/wiki/Artificial_intelligence"
                }
            },
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
        }
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("Artificial intelligence")
        self.assertTrue(result["found"])
        self.assertEqual(result["title"], "Artificial intelligence")
        self.assertEqual(result["description"], "Intelligence demonstrated by machines")
        self.assertIn("intelligence of machines", result["extract"])
        self.assertEqual(result["url"], "https://en.wikipedia.org/wiki/Artificial_intelligence")
        self.assertEqual(result["thumbnail"], "https://upload.wikimedia.org/thumb.jpg")

        # Verify URL encoding (spaces become underscores)
        called_url = mock_get.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://en.wikipedia.org/api/rest_v1/page/summary/Artificial_intelligence",
        )

    @patch("agent.search.requests.get")
    def test_search_wikipedia_summary_not_found(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("NonExistentTopic_XYZ_123")
        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 404)
        self.assertIn("not found", result["error"])

    @patch("agent.search.requests.get")
    def test_search_wikipedia_summary_request_exception(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.RequestException("Connection error")

        result = search_wikipedia_summary("Python")
        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 0)
        self.assertIn("Connection error", result["error"])

    def test_unified_search_combined(self) -> None:
        with patch(
            "agent.search.search_duckduckgo",
            return_value=[{"title": "Test Title", "url": "https://example.com", "snippet": "Test snippet"}],
        ), patch(
            "agent.search.search_wikipedia_summary",
            return_value={"title": "Test Topic", "found": True, "extract": "Wikipedia extract"},
        ):
            res = unified_search("Test Topic", max_results=1, include_wikipedia=True)
            self.assertEqual(res["query"], "Test Topic")
            self.assertEqual(res["duckduckgo_count"], 1)
            self.assertTrue(res["wikipedia"]["found"])
            self.assertEqual(res["wikipedia"]["title"], "Test Topic")


class SearchToolsWiringTests(unittest.TestCase):
    def test_tool_registry_has_wikipedia_summary(self) -> None:
        tool_names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("wikipedia_summary", tool_names)
        self.assertIn("web_search", tool_names)

    @patch("agent.search.requests.get")
    def test_execute_wikipedia_summary_via_registry(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Quantum computing",
            "description": "Computation using quantum mechanics",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Quantum_computing"}},
        }
        mock_get.return_value = mock_resp

        res = GLOBAL_TOOL_REGISTRY.execute("wikipedia_summary", {"title": "Quantum computing"})
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["title"], "Quantum computing")
        self.assertTrue(res["data"]["found"])

    @patch("agent.tools.unified_search")
    def test_langchain_search_web_tool(self, mock_unified: MagicMock) -> None:
        mock_unified.return_value = {
            "wikipedia": {"found": True, "title": "LangGraph", "extract": "Stateful agent library."},
            "duckduckgo_results": [
                {"title": "LangChain Docs", "url": "https://langchain.com", "snippet": "Official docs."}
            ],
        }
        output = search_web.run("LangGraph")
        self.assertIn("Search results for 'LangGraph':", output)
        self.assertIn("Wikipedia Summary: LangGraph", output)
        self.assertIn("LangChain Docs", output)

    @patch("agent.tools.search_wikipedia_summary")
    def test_langchain_get_wikipedia_summary_tool(self, mock_wiki: MagicMock) -> None:
        mock_wiki.return_value = {
            "found": True,
            "title": "Python",
            "description": "High-level programming language",
            "extract": "Python is designed to emphasize code readability.",
            "url": "https://en.wikipedia.org/wiki/Python",
        }
        output = get_wikipedia_summary.run("Python")
        self.assertIn("Title: Python", output)
        self.assertIn("High-level programming language", output)
        self.assertIn("https://en.wikipedia.org/wiki/Python", output)


if __name__ == "__main__":
    unittest.main()
