"""
Wikipedia API client helpers.

Provides search/snippet context for high-level factual grounding.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.wikipedia_api")

_TAG_RE = re.compile(r"<[^>]+>")


def _endpoint() -> str:
    raw = str(getattr(settings, "WIKIPEDIA_API_ENDPOINT", "") or "").strip()
    return raw or "https://en.wikipedia.org/w/api.php"


def _timeout_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(getattr(settings, "WIKIPEDIA_API_TIMEOUT_SECONDS", 8.0))))
    except Exception:
        return 8.0


def _safe_text(value: Any, max_len: int = 220) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _fetch_json(params: dict[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    url = f"{_endpoint()}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/wikipedia-grounder"})
    with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def search_pages(query: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    if not needle:
        return []
    cap = int(limit or getattr(settings, "WIKIPEDIA_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    payload = _fetch_json(
        {
            "action": "query",
            "list": "search",
            "format": "json",
            "utf8": "1",
            "srlimit": str(cap),
            "srsearch": needle[:180],
        }
    )
    rows = ((payload or {}).get("query") or {}).get("search") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for row in list(rows or [])[:cap]:
        if not isinstance(row, dict):
            continue
        title = _safe_text(row.get("title") or "", 120)
        snippet = _safe_text(row.get("snippet") or "", 220)
        pageid = int(row.get("pageid") or 0)
        url_title = urllib.parse.quote(str(title).replace(" ", "_"))
        out.append(
            {
                "title": title,
                "snippet": snippet,
                "pageid": pageid,
                "url": f"https://en.wikipedia.org/wiki/{url_title}",
            }
        )
    return out


def build_query_context(query: str) -> str:
    needle = str(query or "").strip()
    if not needle:
        return ""
    rows = search_pages(needle)
    if not rows:
        return ""

    lines = [
        "[WIKIPEDIA_API_CONTEXT]",
        f"query={_safe_text(needle, 140)}",
        f"matches={len(rows)}",
    ]
    for idx, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").strip() or "unknown"
        snippet = str(row.get("snippet") or "").strip() or "n/a"
        lines.append(f"{idx}. {title}")
        lines.append(f"   snippet: {snippet}")
        link = str(row.get("url") or "").strip()
        if link:
            lines.append(f"   link: {link}")
    return "\n".join(lines).strip()
