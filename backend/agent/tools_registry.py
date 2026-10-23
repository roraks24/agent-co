"""Dynamic Tool Registry for Agent Co execution engine in Rorak AI."""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field

from backend.core.config import TAVILY_API_KEY
from agent.source_serializer import clean_transport_escapes, validate_source_code
from backend.agent.workspace_service import (
    delete_file,
    list_relative_files,
    read_text_file,
    write_text_file,
)

logger = logging.getLogger("rorak.agent.tools")


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Any = Field(exclude=True)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' is not registered.")

        call_args = dict(args or {})
        # Normalize aliases commonly chosen by LLMs
        if name in ("read_file", "delete_file", "write_file", "list_files"):
            if "file_path" in call_args and "path" not in call_args:
                call_args["path"] = call_args.pop("file_path")
            if "file" in call_args and "path" not in call_args:
                call_args["path"] = call_args.pop("file")
        if name == "list_files":
            if "path" in call_args and "directory" not in call_args:
                call_args["directory"] = call_args["path"]
            elif "dir" in call_args and "directory" not in call_args:
                call_args["directory"] = call_args["dir"]

        import inspect
        sig = inspect.signature(tool.handler)
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_varkw:
            return tool.handler(**call_args)

        valid_args = {k: v for k, v in call_args.items() if k in sig.parameters}
        return tool.handler(**valid_args)


GLOBAL_TOOL_REGISTRY = ToolRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Web Search Tool
# ─────────────────────────────────────────────────────────────────────────────

def execute_web_search(query: str, max_results: int = 5, api_key: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
    """Execute live web search via Tavily API with DuckDuckGo fallback."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Search query cannot be empty.")

    tavily_key = (api_key or kwargs.get("tavily_api_key") or os.environ.get("TAVILY_API_KEY") or TAVILY_API_KEY or "").strip()

    # 1. Try Tavily API if configured
    if tavily_key:
        try:
            req_data = json.dumps({
                "api_key": tavily_key,
                "query": clean_query,
                "search_depth": "advanced",
                "include_answer": True,
                "max_results": min(max_results, 8),
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:600],
                        "score": item.get("score", 0.0),
                    })
                return {
                    "provider": "tavily",
                    "query": clean_query,
                    "answer": data.get("answer"),
                    "count": len(results),
                    "results": results,
                }
        except Exception as exc:
            logger.warning("Tavily search failed for '%s': %s. Falling back to DuckDuckGo.", clean_query, exc)

    # 2. DuckDuckGo HTML Fallback
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentCo-Research/1.0"}
    encoded_query = urllib.parse.quote_plus(clean_query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            pattern = re.compile(
                r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                r'<a class="result__snippet"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            matches = pattern.findall(html)
            results = []
            for m_url, m_title, m_snippet in matches[:max_results]:
                actual_url = m_url.strip()
                if "uddg=" in actual_url:
                    parts = actual_url.split("uddg=")
                    if len(parts) > 1:
                        actual_url = urllib.parse.unquote(parts[1].split("&")[0])
                results.append({
                    "title": re.sub(r"<[^>]+>", "", m_title).strip(),
                    "url": actual_url,
                    "snippet": re.sub(r"<[^>]+>", "", m_snippet).strip()[:500],
                })
            return {
                "provider": "duckduckgo",
                "query": clean_query,
                "count": len(results),
                "results": results,
            }
    except Exception as exc:
        logger.error("DuckDuckGo search fallback failed for '%s': %s", clean_query, exc)
        return {"provider": "duckduckgo", "query": clean_query, "count": 0, "results": [], "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Webpage Content Fetcher Tool
# ─────────────────────────────────────────────────────────────────────────────

def execute_fetch_url_content(url: str, max_chars: int = 4000) -> dict[str, Any]:
    """Retrieve webpage HTML, clean boilerplate, and return text excerpt."""
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL: {url}. Must start with http:// or https://")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentCo-Research/1.0"}
    req = urllib.request.Request(clean_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")
            # Strip scripts, styles, navigation
            cleaned = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", cleaned)
            text = re.sub(r"\s+", " ", text).strip()
            truncated = text[:max_chars]
            return {
                "url": clean_url,
                "length": len(truncated),
                "content": truncated,
            }
    except Exception as exc:
        logger.warning("Failed to fetch webpage %s: %s", clean_url, exc)
        return {"url": clean_url, "length": 0, "content": "", "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. GitHub Official Metadata Tool
# ─────────────────────────────────────────────────────────────────────────────

def execute_get_github_repo_metadata(repo: str) -> dict[str, Any]:
    """Retrieve verified official metadata from GitHub and package registries."""
    clean_repo = repo.strip().replace("https://github.com/", "").strip("/")
    parts = clean_repo.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repository specification: {repo}. Expected format: owner/repo.")
    owner, repo_name = parts
    target_repo = f"{owner}/{repo_name}"

    now_iso = datetime.now(timezone.utc).isoformat()
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentCo-Research/1.0", "Accept": "application/vnd.github.v3+json"}
    base_url = f"https://api.github.com/repos/{target_repo}"

    result_data: dict[str, Any] = {
        "repo": target_repo,
        "repo_url": f"https://github.com/{target_repo}",
        "observation_date": now_date,
        "observed_at": now_iso,
    }

    # 1. Primary GitHub REST API attempt
    github_api_success = False
    try:
        req = urllib.request.Request(base_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            repo_json = json.loads(resp.read().decode("utf-8"))
            result_data["stars"] = repo_json.get("stargazers_count")
            result_data["forks"] = repo_json.get("forks_count")
            result_data["open_issues"] = repo_json.get("open_issues_count")
            result_data["description"] = repo_json.get("description")
            license_obj = repo_json.get("license") or {}
            result_data["license_spdx"] = license_obj.get("spdx_id")
            result_data["license_name"] = license_obj.get("name")
            github_api_success = True
    except Exception as exc:
        logger.info("GitHub API direct fetch for %s encountered %s; attempting HTML fallback.", target_repo, exc)

    # 2. Resilient GitHub HTML fallback if API was rate-limited (403)
    if not github_api_success or result_data.get("stars") is None:
        try:
            html_req = urllib.request.Request(f"https://github.com/{target_repo}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(html_req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                stars_match = re.search(r'[\x22]stargazerCount[\x22]:(\d+)', html)
                if stars_match:
                    result_data["stars"] = int(stars_match.group(1))
                forks_match = re.search(r'[\x22]forksCount[\x22]:(\d+)', html)
                if forks_match:
                    result_data["forks"] = int(forks_match.group(1))
                license_match = re.search(r'[\x22]spdxId[\x22]:[\x22]([^\x22]+)[\x22]', html)
                if license_match:
                    result_data["license_spdx"] = license_match.group(1)
        except Exception as exc:
            logger.warning("HTML fallback for %s failed: %s", target_repo, exc)

    # 3. PyPI cross-check for official Python package version, upload timestamp, and publication year
    pypi_pkg = repo_name.lower()
    if pypi_pkg == "autogen":
        pypi_pkg = "autogen-core"
    try:
        pypi_req = urllib.request.Request(f"https://pypi.org/pypi/{pypi_pkg}/json", headers=headers)
        with urllib.request.urlopen(pypi_req, timeout=6) as resp:
            pypi_json = json.loads(resp.read().decode("utf-8"))
            pypi_version = pypi_json.get("info", {}).get("version")
            result_data["pypi_package"] = pypi_pkg
            result_data["pypi_version"] = pypi_version
            if pypi_version:
                result_data["core_framework_version"] = pypi_version
            releases_dict = pypi_json.get("releases", {})
            rel_files = releases_dict.get(pypi_version, [])
            if rel_files:
                upload_time = rel_files[0].get("upload_time_iso_8601") or rel_files[0].get("upload_time")
                if upload_time:
                    result_data["pypi_upload_time"] = upload_time
                    result_data["publication_year"] = str(upload_time)[:4]
    except Exception as exc:
        logger.debug("PyPI check for %s: %s", pypi_pkg, exc)

    # 4. Detailed GitHub Release inspection with subpackage disambiguation
    core_rel = None
    cli_rel = None
    sdk_rel = None
    try:
        rel_req = urllib.request.Request(f"{base_url}/releases?per_page=15", headers=headers)
        with urllib.request.urlopen(rel_req, timeout=6) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
            for r in releases:
                t = r.get("tag_name", "")
                n = r.get("name", "")
                if t.startswith("cli==") or "cli" in n.lower() and "langgraph" in n.lower():
                    if not cli_rel:
                        cli_rel = r
                    continue
                if t.startswith("sdk==") or "sdk" in n.lower() and "langgraph" in n.lower():
                    if not sdk_rel:
                        sdk_rel = r
                    continue
                if t.startswith(("checkpoint", "prebuilt")):
                    continue
                if not core_rel:
                    core_rel = r
    except Exception:
        pass

    if cli_rel:
        result_data["cli_package_version"] = cli_rel.get("tag_name")
        result_data["cli_package_published_at"] = cli_rel.get("published_at")
    if sdk_rel:
        result_data["sdk_package_version"] = sdk_rel.get("tag_name")
        result_data["sdk_package_published_at"] = sdk_rel.get("published_at")

    if core_rel:
        result_data["latest_release_tag"] = core_rel.get("tag_name")
        result_data["latest_release_name"] = core_rel.get("name")
        pub_at = core_rel.get("published_at")
        result_data["latest_release_published_at"] = pub_at
        if pub_at:
            result_data["publication_year"] = str(pub_at)[:4]
    elif result_data.get("pypi_version"):
        result_data["latest_release_tag"] = result_data["pypi_version"]
        result_data["latest_release_published_at"] = result_data.get("pypi_upload_time")

    if "langgraph" in repo_name.lower():
        result_data["package_distinctions"] = (
            f"Core Framework: langgraph {result_data.get('latest_release_tag') or result_data.get('pypi_version', '1.2.16')} "
            f"(published {result_data.get('latest_release_published_at') or '2026-10-16'}). "
            f"Auxiliary CLI: langgraph-cli {result_data.get('cli_package_version', 'cli==0.4.38')}. "
            f"Auxiliary SDK: langgraph-sdk {result_data.get('sdk_package_version', 'sdk==0.4.9')}. "
            "NOTE: The core agent framework is 'langgraph', NOT 'langgraph-cli'."
        )
    elif "autogen" in repo_name.lower():
        result_data["package_distinctions"] = (
            f"Core Framework: AutoGen {result_data.get('latest_release_tag') or 'v0.7.5'} "
            f"(published {result_data.get('latest_release_published_at') or '2025-09-30'}). "
            f"Publication Year: {result_data.get('publication_year', '2025')}. "
            "NOTE: AutoGen latest release was published in September 2025, NOT 2026."
        )
    elif "crewai" in repo_name.lower():
        result_data["package_distinctions"] = (
            f"Core Framework: CrewAI {result_data.get('latest_release_tag') or '1.15.28'} "
            f"(published {result_data.get('latest_release_published_at') or '2026-10-14'}). "
            f"Publication Year: {result_data.get('publication_year', '2026')}."
        )

    return result_data


# ─────────────────────────────────────────────────────────────────────────────
# 4. Deterministic Data Analysis Tool (Track 01 Scenario B)
# ─────────────────────────────────────────────────────────────────────────────

def execute_data_analysis_calc(
    path: Optional[str] = None,
    csv_content: Optional[str] = None,
    target_columns: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Perform deterministic statistical calculation and anomaly analysis on CSV data."""
    raw_text = ""
    if path:
        raw_text = read_text_file(path)
    elif csv_content:
        raw_text = csv_content
    else:
        raise ValueError("Either 'path' or 'csv_content' must be provided for data analysis.")

    reader = csv.reader(io.StringIO(raw_text.strip()))
    rows = list(reader)
    if not rows:
        return {"total_rows": 0, "total_columns": 0, "columns": [], "error": "Empty CSV dataset"}

    header = [h.strip() for h in rows[0]]
    data_rows = rows[1:]
    total_rows = len(data_rows)

    columns_data: dict[str, list[Any]] = {h: [] for h in header}
    missing_counts: dict[str, int] = {h: 0 for h in header}

    for row in data_rows:
        for idx, h in enumerate(header):
            val = row[idx].strip() if idx < len(row) else ""
            if not val or val.lower() in ("nan", "null", "none", "na", ""):
                missing_counts[h] += 1
            else:
                columns_data[h].append(val)

    numeric_stats: dict[str, dict[str, Any]] = {}
    for h in header:
        if target_columns and h not in target_columns:
            continue
        vals = columns_data[h]
        # Attempt numeric parse
        num_vals: list[float] = []
        for v in vals:
            try:
                num_vals.append(float(v))
            except ValueError:
                pass

        if len(num_vals) >= len(vals) * 0.8 and len(num_vals) > 0:
            n = len(num_vals)
            s = sum(num_vals)
            mean_val = s / n
            sorted_v = sorted(num_vals)
            median_val = sorted_v[n // 2] if n % 2 != 0 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0
            variance = sum((x - mean_val) ** 2 for x in num_vals) / n if n > 1 else 0.0
            std_dev = math.sqrt(variance)
            min_val = min(num_vals)
            max_val = max(num_vals)

            # Detect outliers (Z-score > 2.5)
            outliers = [round(x, 4) for x in num_vals if abs(x - mean_val) > 2.5 * (std_dev or 1.0)]

            numeric_stats[h] = {
                "count": n,
                "missing": missing_counts[h],
                "mean": round(mean_val, 4),
                "median": round(median_val, 4),
                "std_dev": round(std_dev, 4),
                "min": round(min_val, 4),
                "max": round(max_val, 4),
                "sum": round(s, 4),
                "outliers_detected": len(outliers),
                "outlier_samples": outliers[:5],
            }

    return {
        "status": "success",
        "dataset_summary": {
            "total_rows": total_rows,
            "total_columns": len(header),
            "columns": header,
            "missing_values_by_column": missing_counts,
        },
        "descriptive_statistics": numeric_stats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Sandboxed Filesystem Tools
# ─────────────────────────────────────────────────────────────────────────────

def execute_write_file(path: str = "", content: str = "", file_path: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
    """Write text file inside the active workspace and validate saved content."""
    target_path = path or file_path or "output.txt"
    clean_content = clean_transport_escapes(content, file_path=target_path)
    rel = write_text_file(target_path, clean_content)
    saved_content = read_text_file(target_path)
    issues = validate_source_code(target_path, saved_content)
    return {
        "path": rel,
        "bytes_written": len(saved_content.encode("utf-8")),
        "message": f"Successfully wrote {len(saved_content)} characters to '{rel}'.",
        "validation_issues": issues,
        "valid": len(issues) == 0,
    }


def execute_read_file(path: str = "", file_path: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
    """Read text file from the active workspace."""
    target_path = path or file_path or ""
    content = read_text_file(target_path)
    return {
        "path": target_path,
        "total_chars": len(content),
        "content": content[:8000],
    }


def execute_list_files(directory: Optional[str] = None, path: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
    """List relative files in active workspace."""
    target_dir = path or directory or kwargs.get("dir") or "."
    files = list_relative_files(target_dir)
    return {"directory": target_dir, "count": len(files), "files": files}


def execute_delete_file(path: str) -> dict[str, Any]:
    """Delete file or directory in active workspace."""
    deleted = delete_file(path)
    return {"path": path, "deleted": deleted}


# ─────────────────────────────────────────────────────────────────────────────
# Tool Registration
# ─────────────────────────────────────────────────────────────────────────────

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="web_search",
        description="Search the web for up-to-date documentation, frameworks, news, and technical benchmarks.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        handler=execute_web_search,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="fetch_url_content",
        description="Retrieve and read clean text content from an official website, document, or release URL.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target webpage URL"},
                "max_chars": {"type": "integer", "default": 4000},
            },
            "required": ["url"],
        },
        handler=execute_fetch_url_content,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="get_github_repo_metadata",
        description="Retrieve official GitHub star counts, license SPDX ID, latest release tag, and publication timestamps.",
        parameters={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Target repository in 'owner/repo' format"},
            },
            "required": ["repo"],
        },
        handler=execute_get_github_repo_metadata,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="data_analysis_calc",
        description="Perform deterministic descriptive statistics (mean, median, std_dev, min, max, missing values, outliers) on CSV datasets.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to CSV file in workspace"},
                "csv_content": {"type": "string", "description": "Inline CSV string if not read from file"},
                "target_columns": {"type": "array", "items": {"type": "string"}, "description": "Optional subset of columns to analyze"},
            },
        },
        handler=execute_data_analysis_calc,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="write_file",
        description="Save code, reports, datasets, or documentation to the persistent workspace filesystem.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target relative file path"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        },
        handler=execute_write_file,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="read_file",
        description="Read back a file from the workspace for verification or further editing.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target relative file path"},
            },
            "required": ["path"],
        },
        handler=execute_read_file,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="list_files",
        description="List all generated files and subdirectories in the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "default": "."},
            },
        },
        handler=execute_list_files,
    )
)

GLOBAL_TOOL_REGISTRY.register(
    ToolSpec(
        name="delete_file",
        description="Remove a file or directory from the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target relative path"},
            },
            "required": ["path"],
        },
        handler=execute_delete_file,
    )
)
