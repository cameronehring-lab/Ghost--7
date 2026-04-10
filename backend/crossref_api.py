"""
Crossref REST API metadata helpers.

Provides DOI-centric bibliographic grounding for research questions.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.crossref_api")


def _endpoint() -> str:
    raw = str(getattr(settings, "CROSSREF_API_ENDPOINT", "") or "").strip()
    return raw or "https://api.crossref.org/works"


def _timeout_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(getattr(settings, "CROSSREF_API_TIMEOUT_SECONDS", 10.0))))
    except Exception:
        return 10.0


def _mailto() -> str:
    return str(getattr(settings, "CROSSREF_MAILTO", "") or "").strip()


def _safe_text(value: Any, max_len: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _fetch_json(params: dict[str, Any]) -> Any:
    query = dict(params or {})
    if _mailto():
        query["mailto"] = _mailto()
    url = f"{_endpoint()}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/crossref-grounder"})
    with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def _authors(row: dict[str, Any], cap: int = 4) -> list[str]:
    out: list[str] = []
    for item in list(row.get("author") or []):
        if not isinstance(item, dict):
            continue
        given = str(item.get("given") or "").strip()
        family = str(item.get("family") or "").strip()
        full = " ".join([piece for piece in (given, family) if piece]).strip()
        if not full:
            continue
        out.append(_safe_text(full, 80))
        if len(out) >= max(1, cap):
            break
    return out


def _published_year(row: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        payload = row.get(key)
        if not isinstance(payload, dict):
            continue
        parts = payload.get("date-parts") or []
        if not isinstance(parts, list) or not parts:
            continue
        first = parts[0]
        if isinstance(first, list) and first:
            return str(first[0])
    return ""


def search_works(query: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    if not needle:
        return []
    cap = int(limit or getattr(settings, "CROSSREF_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    payload = _fetch_json({"query.bibliographic": needle[:220], "rows": str(cap), "sort": "relevance"})
    items = ((payload or {}).get("message") or {}).get("items") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for row in list(items or [])[:cap]:
        if not isinstance(row, dict):
            continue
        title_list = row.get("title") or []
        title = _safe_text(title_list[0] if isinstance(title_list, list) and title_list else "", 240)
        container = row.get("container-title") or []
        venue = _safe_text(container[0] if isinstance(container, list) and container else "", 120)
        out.append(
            {
                "title": title,
                "doi": str(row.get("DOI") or "").strip(),
                "url": str(row.get("URL") or "").strip(),
                "publisher": _safe_text(row.get("publisher") or "", 120),
                "venue": venue,
                "year": _published_year(row),
                "authors": _authors(row),
            }
        )
    return out


def build_query_context(query: str) -> str:
    needle = str(query or "").strip()
    if not needle:
        return ""
    rows = search_works(needle)
    if not rows:
        return ""
    lines = [
        "[CROSSREF_API_CONTEXT]",
        f"query={_safe_text(needle, 140)}",
        f"matches={len(rows)}",
    ]
    if _mailto():
        lines.append("polite_pool=enabled")
    for idx, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").strip() or "untitled"
        lines.append(f"{idx}. {title}")
        year = str(row.get("year") or "").strip()
        if year:
            lines.append(f"   year: {year}")
        doi = str(row.get("doi") or "").strip()
        if doi:
            lines.append(f"   doi: {doi}")
        venue = str(row.get("venue") or "").strip()
        if venue:
            lines.append(f"   venue: {venue}")
        publisher = str(row.get("publisher") or "").strip()
        if publisher:
            lines.append(f"   publisher: {publisher}")
        authors = ", ".join(list(row.get("authors") or [])[:4])
        if authors:
            lines.append(f"   authors: {authors}")
        url = str(row.get("url") or "").strip()
        if url:
            lines.append(f"   link: {url}")
    return "\n".join(lines).strip()
