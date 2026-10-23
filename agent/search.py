"""Search utility module integrating DuckDuckGo and Wikipedia REST API.

Provides:
- DuckDuckGo search via `ddgs.DDGS`
- Wikipedia article summary via Wikipedia REST API (`https://en.wikipedia.org/api/rest_v1/page/summary/{title}`)
  with support for `WIKI_USER_AGENT` and optional `WIKI_API_KEY` from .env
- Unified search utility combining web search and Wikipedia knowledge
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Optional

import requests
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded
load_dotenv()

from ddgs import DDGS

logger = logging.getLogger(__name__)

DEFAULT_WIKI_USER_AGENT = "AgentCo/1.0 (https://github.com/roraks24/agent-co; contact@agentco.dev)"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def get_wiki_headers() -> dict[str, str]:
    """Build Wikipedia REST API headers using WIKI_USER_AGENT and optional WIKI_API_KEY from .env."""
    user_agent = (os.getenv("WIKI_USER_AGENT") or "").strip() or DEFAULT_WIKI_USER_AGENT
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }
    wiki_api_key = (os.getenv("WIKI_API_KEY") or "").strip()
    if wiki_api_key:
        headers["Authorization"] = f"Bearer {wiki_api_key}"
    return headers


def search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo using ddgs.DDGS and return standardized results."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")

    results: list[dict[str, str]] = []
    try:
        with DDGS(timeout=10) as ddgs:
            raw_results = list(ddgs.text(clean_query, max_results=max_results))
            for item in raw_results:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    }
                )
    except Exception as exc:
        logger.warning("DuckDuckGo search encountered error for query '%s': %s", clean_query, exc)
        raise

    return results


def search_wikipedia_summary(title: str) -> dict[str, Any]:
    """Fetch article summary from Wikipedia REST API.

    Endpoint: https://en.wikipedia.org/api/rest_v1/page/summary/{title}
    """
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title must not be empty.")

    encoded_title = urllib.parse.quote(clean_title.replace(" ", "_"), safe="~()*!.'")
    url = WIKIPEDIA_SUMMARY_URL.format(title=encoded_title)
    headers = get_wiki_headers()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "title": data.get("title", clean_title),
                "description": data.get("description", ""),
                "extract": data.get("extract", ""),
                "url": (
                    data.get("content_urls", {}).get("desktop", {}).get("page")
                    or f"https://en.wikipedia.org/wiki/{encoded_title}"
                ),
                "thumbnail": (
                    data.get("thumbnail", {}).get("source")
                    if isinstance(data.get("thumbnail"), dict)
                    else None
                ),
                "found": True,
                "status_code": 200,
            }
        elif response.status_code == 404:
            return {
                "title": clean_title,
                "description": "",
                "extract": "",
                "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
                "found": False,
                "status_code": 404,
                "error": f"Wikipedia article '{clean_title}' not found.",
            }
        else:
            return {
                "title": clean_title,
                "description": "",
                "extract": "",
                "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
                "found": False,
                "status_code": response.status_code,
                "error": f"Wikipedia API returned HTTP {response.status_code}: {response.text[:200]}",
            }
    except requests.RequestException as exc:
        logger.warning("Wikipedia API request error for '%s': %s", clean_title, exc)
        return {
            "title": clean_title,
            "description": "",
            "extract": "",
            "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
            "found": False,
            "status_code": 0,
            "error": f"Request failed: {str(exc)}",
        }


def unified_search(
    query: str,
    max_results: int = 5,
    include_wikipedia: bool = True,
) -> dict[str, Any]:
    """Execute unified search combining DuckDuckGo and Wikipedia REST API."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")

    ddg_results: list[dict[str, str]] = []
    try:
        ddg_results = search_duckduckgo(clean_query, max_results=max_results)
    except Exception as exc:
        logger.warning("DuckDuckGo failed during unified search: %s", exc)

    wiki_summary: Optional[dict[str, Any]] = None
    if include_wikipedia:
        try:
            wiki_summary = search_wikipedia_summary(clean_query)
        except Exception as exc:
            logger.warning("Wikipedia summary lookup failed during unified search: %s", exc)

    return {
        "query": clean_query,
        "duckduckgo_results": ddg_results,
        "duckduckgo_count": len(ddg_results),
        "wikipedia": wiki_summary,
        "results": ddg_results,
    }


# Convenient alias
wikipedia_summary = search_wikipedia_summary
