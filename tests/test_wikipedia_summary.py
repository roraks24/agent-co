"""Tests for Wikipedia summary tool integration.

Covers:
- Input validation (empty, oversized titles)
- URL encoding of article titles
- Successful API responses with structured output
- 404 not-found handling
- HTTP error handling (429, 500) without sensitive info exposure
- Network timeout and connection error handling
- Tool registration in GLOBAL_TOOL_REGISTRY
- Tool discovery via list_tools API
- Execution record model compatibility
- Source evidence representation in verification engine
- Non-interference with existing web_search, get_github_repo_metadata,
  fetch_url_content, and factual verification tools
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests as requests_lib

from agent.search import (
    DEFAULT_WIKI_USER_AGENT,
    WIKIPEDIA_SUMMARY_URL,
    _get_wiki_headers,
    search_wikipedia_summary,
)
from agent.tools_registry import (
    GLOBAL_TOOL_REGISTRY,
    WikipediaSummaryInput,
    execute_wikipedia_summary,
)
from agent.state import (
    ActionExecutionRecord,
    GoalPlan,
    ActionStep,
    SourceEvidence,
)
from agent.verification_engine import FactualVerifier


# ─────────────────────────────────────────────────────────────────────────────
# 1. search_wikipedia_summary — core function tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchWikipediaSummaryValidation(unittest.TestCase):
    """Empty or invalid article titles are rejected."""

    def test_empty_title_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            search_wikipedia_summary("")

    def test_whitespace_only_title_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            search_wikipedia_summary("   ")

    def test_oversized_title_raises_value_error(self) -> None:
        long_title = "A" * 301
        with self.assertRaises(ValueError):
            search_wikipedia_summary(long_title)


class TestSearchWikipediaSummaryURLEncoding(unittest.TestCase):
    """Valid article titles are encoded correctly."""

    @patch("agent.search.requests.get")
    def test_spaces_replaced_with_underscores(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Artificial intelligence",
            "description": "Intelligence of machines",
            "extract": "AI is...",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Artificial_intelligence"}},
        }
        mock_get.return_value = mock_resp

        search_wikipedia_summary("Artificial intelligence")

        called_url = mock_get.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://en.wikipedia.org/api/rest_v1/page/summary/Artificial_intelligence",
        )

    @patch("agent.search.requests.get")
    def test_special_characters_encoded(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "C++",
            "extract": "C++ is a language.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/C%2B%2B"}},
        }
        mock_get.return_value = mock_resp

        search_wikipedia_summary("C++")

        called_url = mock_get.call_args[0][0]
        self.assertIn("C%2B%2B", called_url)


class TestSearchWikipediaSummarySuccess(unittest.TestCase):
    """Successful responses return title, extract, and canonical URL."""

    @patch("agent.search.requests.get")
    def test_successful_response_fields(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Python (programming language)",
            "description": "General-purpose programming language",
            "extract": "Python is a high-level, general-purpose programming language.",
            "content_urls": {
                "desktop": {"page": "https://en.wikipedia.org/wiki/Python_(programming_language)"}
            },
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
        }
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("Python (programming language)")

        self.assertTrue(result["found"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["title"], "Python (programming language)")
        self.assertEqual(result["description"], "General-purpose programming language")
        self.assertIn("high-level", result["extract"])
        self.assertEqual(
            result["url"],
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
        )
        self.assertEqual(result["thumbnail"], "https://upload.wikimedia.org/thumb.jpg")
        self.assertIn("observed_at", result)

    @patch("agent.search.requests.get")
    def test_no_thumbnail_returns_none(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Test",
            "extract": "Test article.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Test"}},
        }
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("Test")
        self.assertIsNone(result["thumbnail"])


class TestSearchWikipediaSummaryNotFound(unittest.TestCase):
    """Missing articles produce an appropriate not-found result."""

    @patch("agent.search.requests.get")
    def test_404_response(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("NonExistentTopicXYZ123")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 404)
        self.assertIn("not found", result["error"])
        self.assertIn("observed_at", result)


class TestSearchWikipediaSummaryHTTPErrors(unittest.TestCase):
    """HTTP errors are handled without exposing sensitive information."""

    @patch("agent.search.requests.get")
    def test_rate_limit_429(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too many requests"
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("Python")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 429)
        self.assertIn("rate limit", result["error"].lower())

    @patch("agent.search.requests.get")
    def test_server_error_500(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error with sensitive details"
        mock_get.return_value = mock_resp

        result = search_wikipedia_summary("Python")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 500)
        # Body is truncated to 200 chars to avoid leaking verbose server info
        self.assertIn("HTTP 500", result["error"])


class TestSearchWikipediaSummaryNetworkErrors(unittest.TestCase):
    """Network timeouts and connection errors are handled correctly."""

    @patch("agent.search.requests.get")
    def test_connection_error(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests_lib.ConnectionError("DNS resolution failed")

        result = search_wikipedia_summary("Python")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 0)
        self.assertIn("Connection failed", result["error"])
        # Should not expose raw exception details
        self.assertNotIn("DNS resolution failed", result["error"])

    @patch("agent.search.requests.get")
    def test_timeout_error(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests_lib.Timeout("Read timed out")

        result = search_wikipedia_summary("Python")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 0)
        self.assertIn("timed out", result["error"].lower())

    @patch("agent.search.requests.get")
    def test_generic_request_exception(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests_lib.RequestException("Something broke")

        result = search_wikipedia_summary("Python")

        self.assertFalse(result["found"])
        self.assertEqual(result["status_code"], 0)
        # Sanitised: only the exception class name, not internal details
        self.assertIn("RequestException", result["error"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wiki headers
# ─────────────────────────────────────────────────────────────────────────────


class TestWikiHeaders(unittest.TestCase):
    def test_default_user_agent(self) -> None:
        with patch.dict(os.environ, {"WIKI_USER_AGENT": ""}, clear=False):
            headers = _get_wiki_headers()
            self.assertEqual(headers["User-Agent"], DEFAULT_WIKI_USER_AGENT)
            self.assertEqual(headers["Accept"], "application/json")
            # No API key = no Authorization header
            self.assertNotIn("Authorization", headers)

    def test_custom_user_agent_from_env(self) -> None:
        with patch.dict(os.environ, {"WIKI_USER_AGENT": "CustomBot/2.0"}, clear=False):
            headers = _get_wiki_headers()
            self.assertEqual(headers["User-Agent"], "CustomBot/2.0")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tool registry integration
# ─────────────────────────────────────────────────────────────────────────────


class TestToolRegistryIntegration(unittest.TestCase):
    """The tool is registered in main's existing registry."""

    def test_wikipedia_summary_is_registered(self) -> None:
        tool_names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("wikipedia_summary", tool_names)

    def test_tool_has_correct_metadata(self) -> None:
        tool_def = GLOBAL_TOOL_REGISTRY.get("wikipedia_summary")
        self.assertIsNotNone(tool_def)
        self.assertEqual(tool_def.name, "wikipedia_summary")
        self.assertEqual(tool_def.schema, WikipediaSummaryInput)
        self.assertIn("Wikipedia", tool_def.description)


class TestToolDiscoveryAPI(unittest.TestCase):
    """The tool-discovery API exposes the registered tool."""

    def test_list_tools_includes_wikipedia_summary(self) -> None:
        tools = GLOBAL_TOOL_REGISTRY.list_tools()
        wiki_tool = next((t for t in tools if t["name"] == "wikipedia_summary"), None)
        self.assertIsNotNone(wiki_tool)
        self.assertIn("parameters", wiki_tool)
        self.assertIn("restrictions", wiki_tool)
        self.assertIn("description", wiki_tool)

    def test_tool_parameters_schema_has_title(self) -> None:
        tools = GLOBAL_TOOL_REGISTRY.list_tools()
        wiki_tool = next(t for t in tools if t["name"] == "wikipedia_summary")
        props = wiki_tool["parameters"].get("properties", {})
        self.assertIn("title", props)


class TestToolExecution(unittest.TestCase):
    """Tool output is available in the execution-record model."""

    @patch("agent.search.requests.get")
    def test_execute_via_registry_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Quantum computing",
            "description": "Computation using quantum mechanics",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Quantum_computing"}},
        }
        mock_get.return_value = mock_resp

        result = GLOBAL_TOOL_REGISTRY.execute("wikipedia_summary", {"title": "Quantum computing"})

        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertIn("started_at", result)
        self.assertIn("completed_at", result)

        data = result["data"]
        self.assertTrue(data["found"])
        self.assertEqual(data["title"], "Quantum computing")
        self.assertIn("Quantum computing", data["extract"])

    def test_execute_via_registry_validation_error(self) -> None:
        result = GLOBAL_TOOL_REGISTRY.execute("wikipedia_summary", {"title": ""})
        self.assertFalse(result["success"])
        self.assertIn("ValidationError", result["error"])

    @patch("agent.search.requests.get")
    def test_execution_record_model_compatibility(self, mock_get: MagicMock) -> None:
        """The tool result fits into ActionExecutionRecord without error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Test",
            "extract": "Test content.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Test"}},
        }
        mock_get.return_value = mock_resp

        tool_result = GLOBAL_TOOL_REGISTRY.execute("wikipedia_summary", {"title": "Test"})

        # Should be constructable as an ActionExecutionRecord
        record = ActionExecutionRecord(
            step_id="step-1",
            tool_name="wikipedia_summary",
            tool_args={"title": "Test"},
            started_at=tool_result["started_at"],
            completed_at=tool_result["completed_at"],
            duration_ms=42,
            tool_result=tool_result["data"],
            status="success" if tool_result["success"] else "failed",
        )
        self.assertEqual(record.tool_name, "wikipedia_summary")
        self.assertEqual(record.status, "success")
        self.assertIsNotNone(record.tool_result)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Source evidence / verification integration
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceEvidenceIntegration(unittest.TestCase):
    """Successful results can be represented in source evidence."""

    def test_successful_wikipedia_result_creates_source_evidence(self) -> None:
        wiki_result = {
            "title": "Machine learning",
            "description": "Branch of AI",
            "extract": "Machine learning is a subset of artificial intelligence.",
            "url": "https://en.wikipedia.org/wiki/Machine_learning",
            "found": True,
            "status_code": 200,
            "observed_at": "2026-10-23T12:00:00+00:00",
        }

        record = ActionExecutionRecord(
            step_id="step-1",
            tool_name="wikipedia_summary",
            tool_args={"title": "Machine learning"},
            started_at="2026-10-23T12:00:00+00:00",
            completed_at="2026-10-23T12:00:01+00:00",
            duration_ms=800,
            tool_result=wiki_result,
            status="success",
        )

        goal_plan = GoalPlan(
            objective="Research ML",
            task_type="research",
            expected_outcome="ML summary",
            steps=[
                ActionStep(
                    id="step-1",
                    title="Look up ML on Wikipedia",
                    tool_name="wikipedia_summary",
                    tool_args={"title": "Machine learning"},
                    status="completed",
                ),
            ],
        )

        verifier = FactualVerifier(goal_plan, [record])

        # Verify evidence was populated
        wiki_sources = [s for s in verifier.source_evidence if "wikipedia" in s.url.lower()]
        self.assertTrue(len(wiki_sources) > 0)
        se = wiki_sources[0]
        self.assertEqual(se.status, "retrieved")
        self.assertIn("Machine learning", se.title)
        self.assertIn("Machine learning", se.relevant_excerpt)
        self.assertFalse(se.is_official_source)  # Wikipedia is not official for quantitative claims

    def test_failed_wikipedia_result_does_not_create_evidence(self) -> None:
        """When article is not found, no source evidence is recorded."""
        wiki_result = {
            "title": "NonExistent",
            "extract": "",
            "url": "https://en.wikipedia.org/wiki/NonExistent",
            "found": False,
            "status_code": 404,
            "error": "Article not found.",
        }

        record = ActionExecutionRecord(
            step_id="step-1",
            tool_name="wikipedia_summary",
            tool_args={"title": "NonExistent"},
            started_at="2026-10-23T12:00:00+00:00",
            completed_at="2026-10-23T12:00:01+00:00",
            duration_ms=300,
            tool_result=wiki_result,
            status="success",  # Tool itself succeeded; article just wasn't found
        )

        goal_plan = GoalPlan(
            objective="Test",
            task_type="general",
            expected_outcome="Test",
            steps=[
                ActionStep(
                    id="step-1",
                    title="Lookup",
                    tool_name="wikipedia_summary",
                    tool_args={"title": "NonExistent"},
                    status="completed",
                ),
            ],
        )

        verifier = FactualVerifier(goal_plan, [record])
        wiki_sources = [s for s in verifier.source_evidence if "wikipedia" in (s.title or "").lower()]
        self.assertEqual(len(wiki_sources), 0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Non-interference with existing tools
# ─────────────────────────────────────────────────────────────────────────────


class TestExistingToolsUnaffected(unittest.TestCase):
    """Existing web search, GitHub metadata, webpage fetching, and
    factual verification remain unaffected."""

    def test_web_search_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("web_search", names)

    def test_github_metadata_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("get_github_repo_metadata", names)

    def test_fetch_url_content_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("fetch_url_content", names)

    def test_write_file_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("write_file", names)

    def test_read_file_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("read_file", names)

    def test_list_files_still_registered(self) -> None:
        names = {t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools()}
        self.assertIn("list_files", names)

    def test_total_tool_count_increased_by_one(self) -> None:
        """We added exactly one new tool (wikipedia_summary) to the default set."""
        tools = GLOBAL_TOOL_REGISTRY.list_tools()
        names = {t["name"] for t in tools}
        expected = {
            "web_search",
            "get_github_repo_metadata",
            "fetch_url_content",
            "write_file",
            "read_file",
            "list_files",
            "wikipedia_summary",
        }
        self.assertEqual(names, expected)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Integration test (live network — skipped by default)
# ─────────────────────────────────────────────────────────────────────────────


@unittest.skipUnless(
    os.getenv("AGENT_CO_INTEGRATION_TESTS") == "1",
    "Live integration tests require AGENT_CO_INTEGRATION_TESTS=1",
)
class TestLiveWikipediaSummary(unittest.TestCase):
    """Live integration test — sends a real request to Wikipedia REST API."""

    def test_live_python_article(self) -> None:
        result = search_wikipedia_summary("Python (programming language)")
        self.assertTrue(result["found"])
        self.assertEqual(result["status_code"], 200)
        self.assertIn("Python", result["title"])
        self.assertTrue(len(result["extract"]) > 20)
        self.assertIn("wikipedia.org", result["url"])


if __name__ == "__main__":
    unittest.main()
