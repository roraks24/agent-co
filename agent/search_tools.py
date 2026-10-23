"""Search tools integration module alias for agent.search."""

from __future__ import annotations

from .search import (
    DEFAULT_WIKI_USER_AGENT,
    WIKIPEDIA_SUMMARY_URL,
    get_wiki_headers,
    search_duckduckgo,
    search_wikipedia_summary,
    unified_search,
    wikipedia_summary,
)

__all__ = [
    "DEFAULT_WIKI_USER_AGENT",
    "WIKIPEDIA_SUMMARY_URL",
    "get_wiki_headers",
    "search_duckduckgo",
    "search_wikipedia_summary",
    "unified_search",
    "wikipedia_summary",
]
