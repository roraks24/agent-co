"""Wikipedia REST API integration for Agent Co.

Provides structured article summary retrieval via the Wikipedia REST API
(https://en.wikipedia.org/api/rest_v1/page/summary/{title}).

This module is the authoritative implementation for the ``wikipedia_summary``
tool.  It does **not** duplicate the general-purpose web-search capability
already provided by ``tools_registry.execute_web_search``.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_WIKI_USER_AGENT = "AgentCo/1.0 (https://github.com/roraks24/agent-co)"

WIKIPEDIA_SUMMARY_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
)

_WIKIPEDIA_ALLOWED_HOST = "en.wikipedia.org"

# Maximum accepted title length (bytes after encoding) to prevent abuse.
_MAX_TITLE_LENGTH = 300

# HTTP timeout for Wikipedia requests (seconds).
_REQUEST_TIMEOUT = 10

# Maximum response body we are willing to read (bytes).
_MAX_RESPONSE_BYTES = 256_000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_wiki_headers() -> dict[str, str]:
    """Build Wikipedia REST API request headers.

    Uses ``WIKI_USER_AGENT`` from the environment if set; otherwise falls back
    to ``DEFAULT_WIKI_USER_AGENT``.

    The Wikipedia REST API is **public** and does not require an API key.
    """
    user_agent = (os.getenv("WIKI_USER_AGENT") or "").strip() or DEFAULT_WIKI_USER_AGENT
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_wikipedia_summary(title: str) -> dict[str, Any]:
    """Fetch a structured article summary from the Wikipedia REST API.

    Parameters
    ----------
    title:
        The Wikipedia article title or topic (e.g. ``"Artificial intelligence"``).

    Returns
    -------
    dict
        A dictionary with keys:

        * ``title`` – resolved article title.
        * ``description`` – short description / tagline.
        * ``extract`` – plain-text summary paragraph.
        * ``url`` – canonical desktop URL of the article.
        * ``thumbnail`` – thumbnail image URL (or ``None``).
        * ``found`` – boolean indicating lookup success.
        * ``status_code`` – HTTP status code from the API.
        * ``observed_at`` – ISO timestamp of retrieval.
        * ``error`` – human-readable error message (only on failure).
    """
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title must not be empty.")
    if len(clean_title) > _MAX_TITLE_LENGTH:
        raise ValueError(
            f"title exceeds maximum length of {_MAX_TITLE_LENGTH} characters."
        )

    encoded_title = urllib.parse.quote(
        clean_title.replace(" ", "_"), safe="~()*!.'"
    )
    url = WIKIPEDIA_SUMMARY_URL.format(title=encoded_title)
    headers = _get_wiki_headers()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        response = requests.get(
            url, headers=headers, timeout=_REQUEST_TIMEOUT
        )

        if response.status_code == 200:
            # Bound the amount we parse.
            data = response.json()
            return {
                "title": data.get("title", clean_title),
                "description": data.get("description", ""),
                "extract": data.get("extract", ""),
                "url": (
                    data.get("content_urls", {})
                    .get("desktop", {})
                    .get("page")
                    or f"https://en.wikipedia.org/wiki/{encoded_title}"
                ),
                "thumbnail": (
                    data.get("thumbnail", {}).get("source")
                    if isinstance(data.get("thumbnail"), dict)
                    else None
                ),
                "found": True,
                "status_code": 200,
                "observed_at": now_iso,
            }

        if response.status_code == 404:
            return {
                "title": clean_title,
                "description": "",
                "extract": "",
                "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
                "found": False,
                "status_code": 404,
                "observed_at": now_iso,
                "error": f"Wikipedia article '{clean_title}' not found.",
            }

        if response.status_code == 429:
            return {
                "title": clean_title,
                "description": "",
                "extract": "",
                "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
                "found": False,
                "status_code": 429,
                "observed_at": now_iso,
                "error": "Wikipedia API rate limit exceeded. Try again later.",
            }

        # Generic server / client error.
        safe_body = response.text[:200] if response.text else ""
        return {
            "title": clean_title,
            "description": "",
            "extract": "",
            "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
            "found": False,
            "status_code": response.status_code,
            "observed_at": now_iso,
            "error": f"Wikipedia API returned HTTP {response.status_code}: {safe_body}",
        }

    except requests.ConnectionError as exc:
        logger.warning("Wikipedia connection error for '%s': %s", clean_title, exc)
        return {
            "title": clean_title,
            "description": "",
            "extract": "",
            "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
            "found": False,
            "status_code": 0,
            "observed_at": now_iso,
            "error": "Connection failed: unable to reach Wikipedia.",
        }

    except requests.Timeout as exc:
        logger.warning("Wikipedia request timeout for '%s': %s", clean_title, exc)
        return {
            "title": clean_title,
            "description": "",
            "extract": "",
            "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
            "found": False,
            "status_code": 0,
            "observed_at": now_iso,
            "error": "Request timed out while contacting Wikipedia.",
        }

    except requests.RequestException as exc:
        logger.warning("Wikipedia request error for '%s': %s", clean_title, exc)
        return {
            "title": clean_title,
            "description": "",
            "extract": "",
            "url": f"https://en.wikipedia.org/wiki/{encoded_title}",
            "found": False,
            "status_code": 0,
            "observed_at": now_iso,
            "error": f"Request failed: {type(exc).__name__}",
        }
