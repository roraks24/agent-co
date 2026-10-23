from __future__ import annotations

from langchain_core.tools import tool

try:  # pragma: no cover - supports running as script
    from .workspace import (
        WorkspaceBinaryFileError,
        WorkspaceValidationError,
        list_relative_files,
        read_text_file,
        write_text_file,
    )
    from .search import (
        search_duckduckgo,
        search_wikipedia_summary,
        unified_search,
    )
except ImportError:  # pragma: no cover
    from workspace import (
        WorkspaceBinaryFileError,
        WorkspaceValidationError,
        list_relative_files,
        read_text_file,
        write_text_file,
    )
    from search import (
        search_duckduckgo,
        search_wikipedia_summary,
        unified_search,
    )


@tool
def write_file(path: str, content: str) -> str:
    """Writes content to a file inside the 'generated_project' folder."""
    relative_path = write_text_file(path, content)
    return f"WROTE: {relative_path}"


@tool
def read_file(path: str) -> str:
    """Reads content from a file within the 'generated_project' folder."""
    try:
        return read_text_file(path)
    except FileNotFoundError:
        return f"ERROR: File {path} does not exist."
    except WorkspaceBinaryFileError:
        return f"ERROR: File {path} is binary and cannot be read as text."


@tool
def list_files(directory: str = ".") -> str:
    """Lists all files inside the 'generated_project' folder."""
    try:
        files = list_relative_files(directory)
    except FileNotFoundError:
        return f"ERROR: {directory} does not exist"
    except WorkspaceValidationError:
        return f"ERROR: {directory} is not a directory"
    return "\n".join(files) if files else "No files found."


@tool
def search_web(query: str) -> str:
    """Searches DuckDuckGo and Wikipedia for external documentation, libraries, facts, and code examples."""
    try:
        data = unified_search(query)
        lines = [f"Search results for '{query}':"]
        wiki = data.get("wikipedia")
        if wiki and wiki.get("found"):
            lines.append(f"\n[Wikipedia Summary: {wiki.get('title')}]")
            if wiki.get("description"):
                lines.append(f"Description: {wiki.get('description')}")
            if wiki.get("extract"):
                lines.append(f"Extract: {wiki.get('extract')}")
            lines.append(f"URL: {wiki.get('url')}")

        ddg_results = data.get("duckduckgo_results", [])
        if ddg_results:
            lines.append("\n[Web Results]")
            for idx, res in enumerate(ddg_results, start=1):
                lines.append(f"{idx}. {res.get('title')}")
                lines.append(f"   URL: {res.get('url')}")
                lines.append(f"   Snippet: {res.get('snippet')}")
        elif not (wiki and wiki.get("found")):
            return f"No search results found for '{query}'."

        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR searching web: {str(exc)}"


@tool
def get_wikipedia_summary(title: str) -> str:
    """Fetches a structured summary of a topic or entity directly from the Wikipedia REST API."""
    try:
        res = search_wikipedia_summary(title)
        if not res.get("found"):
            return res.get("error", f"Wikipedia article '{title}' not found.")
        lines = [
            f"Title: {res.get('title')}",
            f"Description: {res.get('description') or 'N/A'}",
            f"Extract: {res.get('extract') or 'N/A'}",
            f"URL: {res.get('url')}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR fetching Wikipedia summary: {str(exc)}"
