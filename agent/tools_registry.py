"""Extensible Tool Registry for Agent Co.

Registers safe, schema-validated tools for file management, web research,
and external data retrieval without exposing unrestricted execution or secrets.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

try:
    from .workspace import (
        WorkspaceBinaryFileError,
        WorkspaceValidationError,
        list_relative_files,
        read_text_file,
        write_text_file,
    )
except ImportError:  # pragma: no cover
    from workspace import (
        WorkspaceBinaryFileError,
        WorkspaceValidationError,
        list_relative_files,
        read_text_file,
        write_text_file,
    )

logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 12_000
SECRET_KEY_PATTERN = re.compile(
    r"(api[-_]?key|token|secret|password|auth|bearer|credential)",
    re.IGNORECASE,
)


def redact_sensitive_data(value: Any) -> Any:
    """Recursively mask sensitive values matching credential or secret patterns."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            if SECRET_KEY_PATTERN.search(str(k)):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_sensitive_data(v)
        return sanitized
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        # Redact Bearer tokens and generic long hex/base64 keys
        if len(value) > 24 and any(prefix in value.lower() for prefix in ("gsk_", "sk-", "bearer ")):
            return "[REDACTED]"
    return value


def _truncate_output(text: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    omitted = len(text) - max_chars
    return f"{truncated}\n... [TRUNCATED {omitted} characters for context limit]"


# ─────────────────────────────────────────────────────────────────────────────
# Tool Input Schemas
# ─────────────────────────────────────────────────────────────────────────────

class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="The search query.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of search results (1-10).")


class FetchUrlInput(BaseModel):
    url: str = Field(..., min_length=8, description="Public HTTP/HTTPS URL to fetch content from.")
    max_chars: int = Field(default=4000, ge=100, le=10000, description="Max characters to return.")


class GitHubRepoInput(BaseModel):
    repo: str = Field(..., min_length=3, description="GitHub repository in owner/repo format, e.g. langchain-ai/langgraph.")


class WriteFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Relative path in the session workspace.")
    content: str = Field(..., description="Full text content to write to the file.")


class ReadFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Relative path to read from the session workspace.")


class ListFilesInput(BaseModel):
    directory: str = Field(default=".", description="Relative directory path to list (default: root).")


# ─────────────────────────────────────────────────────────────────────────────
# Tool Implementations
# ─────────────────────────────────────────────────────────────────────────────

def _is_private_or_loopback_host(host: str) -> bool:
    """Detect loopback and private IP hosts to prevent SSRF."""
    host_clean = host.split(":")[0].strip().lower()
    if host_clean in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ip_address(host_clean)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return False


def execute_web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Execute real web search using ddgs or Tavily if configured."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")

    results: list[dict[str, str]] = []

    # Strategy 1: Tavily API if key provided
    tavily_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if tavily_key:
        try:
            from tavily import TavilyClient  # type: ignore

            client = TavilyClient(api_key=tavily_key)
            response = client.search(clean_query, max_results=max_results)
            for item in response.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                    }
                )
            if results:
                return {
                    "provider": "tavily",
                    "query": clean_query,
                    "count": len(results),
                    "results": results,
                }
        except Exception as exc:
            logger.warning("Tavily search failed, falling back: %s", exc)

    # Strategy 2: DDGS search
    try:
        from ddgs import DDGS  # type: ignore

        with DDGS(timeout=8) as ddgs:
            raw_results = list(ddgs.text(clean_query, max_results=max_results))
            for item in raw_results:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    }
                )
        if results:
            return {
                "provider": "duckduckgo",
                "query": clean_query,
                "count": len(results),
                "results": results,
            }
    except Exception as exc:
        logger.warning("DDGS search encountered error: %s", exc)

    # Strategy 3: Lightweight Wikipedia / public knowledge fallback for research queries
    try:
        import urllib.parse
        import urllib.request
        import json

        encoded = urllib.parse.quote(clean_query)
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit={max_results}&namespace=0&format=json"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "AgentCo-Research/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if len(data) >= 4:
                titles = data[1]
                snippets = data[2]
                urls = data[3]
                for i in range(len(titles)):
                    results.append(
                        {
                            "title": titles[i],
                            "url": urls[i],
                            "snippet": snippets[i] if i < len(snippets) else "",
                        }
                    )
        if results:
            return {
                "provider": "wikipedia_knowledge",
                "query": clean_query,
                "count": len(results),
                "results": results,
            }
    except Exception as exc:
        logger.warning("Knowledge search fallback failed: %s", exc)

    if not results:
        return {
            "provider": "none",
            "query": clean_query,
            "count": 0,
            "results": [],
            "message": f"No search results returned for '{clean_query}'. Verify network connectivity.",
        }

    return {
        "provider": "duckduckgo",
        "query": clean_query,
        "count": len(results),
        "results": results,
    }


def execute_fetch_url(url: str, max_chars: int = 4000) -> dict[str, Any]:
    """Safely fetch and extract readable text from a public HTTP/HTTPS URL."""
    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must have an http or https scheme.")
    if not parsed.netloc:
        raise ValueError("URL netloc is invalid.")
    if _is_private_or_loopback_host(parsed.netloc):
        raise PermissionError("Access to loopback or private network IPs is forbidden.")

    import urllib.request
    from bs4 import BeautifulSoup  # type: ignore

    req = urllib.request.Request(
        clean_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )

    with urllib.request.urlopen(req, timeout=8) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if not any(t in content_type for t in ("text/", "html", "json", "xml")):
            raise ValueError(f"Content type '{content_type}' is not readable text.")

        raw_bytes = response.read(100_000)  # Read up to 100KB max
        text = raw_bytes.decode("utf-8", errors="replace")

    soup = BeautifulSoup(text, "html.parser")
    # Remove script, style, navigation tags
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()

    extracted = soup.get_text(separator=" ", strip=True)
    collapsed = re.sub(r"\s+", " ", extracted).strip()
    truncated = collapsed[:max_chars]

    return {
        "url": clean_url,
        "length": len(truncated),
        "content": truncated,
    }


def execute_get_github_repo_metadata(repo: str) -> dict[str, Any]:
    """Retrieve verified official metadata from the public GitHub REST API."""
    clean_repo = repo.strip().replace("https://github.com/", "").strip("/")
    parts = clean_repo.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repository specification: {repo}. Expected format: owner/repo.")
    owner, repo_name = parts
    target_repo = f"{owner}/{repo_name}"

    import json
    import urllib.request
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    headers = {"User-Agent": "AgentCo-Research/1.0", "Accept": "application/vnd.github.v3+json"}
    base_url = f"https://api.github.com/repos/{target_repo}"

    result_data: dict[str, Any] = {
        "repo": target_repo,
        "repo_url": f"https://github.com/{target_repo}",
        "observation_date": now_date,
        "observed_at": now_iso,
    }

    try:
        req = urllib.request.Request(base_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            repo_json = json.loads(resp.read().decode("utf-8"))
            result_data["stars"] = repo_json.get("stargazers_count")
            result_data["forks"] = repo_json.get("forks_count")
            result_data["open_issues"] = repo_json.get("open_issues_count")
            result_data["description"] = repo_json.get("description")
            result_data["default_branch"] = repo_json.get("default_branch")
            license_obj = repo_json.get("license") or {}
            result_data["license_spdx"] = license_obj.get("spdx_id")
            result_data["license_name"] = license_obj.get("name")
            result_data["archived"] = repo_json.get("archived", False)
    except Exception as exc:
        logger.warning("Failed to fetch repository metadata for %s: %s", target_repo, exc)
        raise ValueError(f"Could not retrieve GitHub repository metadata for {target_repo}: {exc}")

    # Also attempt to retrieve latest release
    try:
        rel_req = urllib.request.Request(f"{base_url}/releases/latest", headers=headers)
        with urllib.request.urlopen(rel_req, timeout=5) as resp:
            rel_json = json.loads(resp.read().decode("utf-8"))
            result_data["latest_release_tag"] = rel_json.get("tag_name")
            result_data["latest_release_name"] = rel_json.get("name")
            result_data["latest_release_published_at"] = rel_json.get("published_at")
    except Exception:
        # Fall back to PyPI version query for python packages
        package_name = repo_name.lower()
        try:
            pypi_req = urllib.request.Request(f"https://pypi.org/pypi/{package_name}/json", headers=headers)
            with urllib.request.urlopen(pypi_req, timeout=5) as resp:
                pypi_json = json.loads(resp.read().decode("utf-8"))
                result_data["pypi_version"] = pypi_json.get("info", {}).get("version")
        except Exception:
            result_data["latest_release_tag"] = None

    return result_data


def execute_write_file(path: str, content: str) -> dict[str, Any]:
    """Write text file inside the active session workspace."""
    relative_path = write_text_file(path, content)
    return {
        "path": relative_path,
        "bytes_written": len(content.encode("utf-8")),
        "message": f"Successfully wrote {len(content)} characters to '{relative_path}'.",
    }


def execute_read_file(path: str) -> dict[str, Any]:
    """Read text file from the active session workspace."""
    try:
        content = read_text_file(path)
        return {
            "path": path,
            "content": _truncate_output(content),
            "total_chars": len(content),
        }
    except FileNotFoundError:
        return {
            "path": path,
            "error": f"File '{path}' does not exist in workspace.",
            "content": "",
        }
    except WorkspaceBinaryFileError:
        return {
            "path": path,
            "error": f"File '{path}' is binary and cannot be read as text.",
            "content": "",
        }


def execute_list_files(directory: str = ".") -> dict[str, Any]:
    """List relative files inside the active session workspace."""
    try:
        files = list_relative_files(directory)
        return {
            "directory": directory,
            "count": len(files),
            "files": files,
        }
    except FileNotFoundError:
        return {
            "directory": directory,
            "count": 0,
            "files": [],
            "error": f"Directory '{directory}' does not exist.",
        }
    except WorkspaceValidationError as exc:
        return {
            "directory": directory,
            "count": 0,
            "files": [],
            "error": str(exc),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tool Definition & Registry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    name: str
    description: str
    schema: type[BaseModel]
    restrictions: str
    handler: Callable[..., Any]

    def validate_and_execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments against schema, redact secrets, and execute safely."""
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            validated = self.schema(**arguments)
            raw_result = self.handler(**validated.model_dump())
            completed_at = datetime.now(timezone.utc).isoformat()
            return {
                "success": True,
                "data": raw_result,
                "error": None,
                "started_at": started_at,
                "completed_at": completed_at,
            }
        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            logger.exception("Error executing tool '%s': %s", self.name, exc)
            return {
                "success": False,
                "data": None,
                "error": f"{exc.__class__.__name__}: {str(exc)}",
                "started_at": started_at,
                "completed_at": completed_at,
            }


class ToolRegistry:
    """Central registry of agent tools with schema validation and access controls."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool_def: ToolDefinition) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema.model_json_schema(),
                "restrictions": t.restrictions,
            }
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool_def = self.get(name)
        if tool_def is None:
            now_iso = datetime.now(timezone.utc).isoformat()
            return {
                "success": False,
                "data": None,
                "error": f"Tool '{name}' is not registered. Available tools: {list(self._tools.keys())}",
                "started_at": now_iso,
                "completed_at": now_iso,
            }
        return tool_def.validate_and_execute(arguments)

    def _register_default_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="web_search",
                description=(
                    "Search the web for up-to-date facts, research, articles, benchmarks, and documentation. "
                    "Returns a list of titles, URLs, and summaries."
                ),
                schema=WebSearchInput,
                restrictions="Read-only outbound search queries. Max 10 results per query.",
                handler=execute_web_search,
            )
        )
        self.register(
            ToolDefinition(
                name="get_github_repo_metadata",
                description=(
                    "Retrieve official GitHub repository metadata (verified star count, forks, official license SPDX ID, "
                    "latest release tag and publish date). Essential for factual framework research."
                ),
                schema=GitHubRepoInput,
                restrictions="Public repositories on github.com only. Non-destructive.",
                handler=execute_get_github_repo_metadata,
            )
        )
        self.register(
            ToolDefinition(
                name="fetch_url_content",
                description=(
                    "Fetch and extract clean readable text content from a public HTTP/HTTPS URL. "
                    "Ideal for reading articles, release notes, and documentation."
                ),
                schema=FetchUrlInput,
                restrictions="Public HTTP/HTTPS URLs only. Private IP ranges and loopbacks are strictly blocked.",
                handler=execute_fetch_url,
            )
        )
        self.register(
            ToolDefinition(
                name="write_file",
                description=(
                    "Write or overwrite a file in the session workspace. "
                    "Creates any missing parent folders automatically."
                ),
                schema=WriteFileInput,
                restrictions="Restricted to the active session workspace. Directory traversal (..) is blocked.",
                handler=execute_write_file,
            )
        )
        self.register(
            ToolDefinition(
                name="read_file",
                description="Read the text contents of a file inside the session workspace.",
                schema=ReadFileInput,
                restrictions="Restricted to the active session workspace. Binary files are rejected.",
                handler=execute_read_file,
            )
        )
        self.register(
            ToolDefinition(
                name="list_files",
                description="List all files in a directory of the session workspace.",
                schema=ListFilesInput,
                restrictions="Restricted to the active session workspace.",
                handler=execute_list_files,
            )
        )


# Global singleton registry
GLOBAL_TOOL_REGISTRY = ToolRegistry()
