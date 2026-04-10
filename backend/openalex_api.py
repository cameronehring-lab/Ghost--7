"""
OpenAlex API metadata helpers.

Provides research-graph grounding (works, authors, venue, concepts).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.openalex_api")


def _endpoint() -> str:
    raw = str(getattr(settings, "OPENALEX_API_ENDPOINT", "") or "").strip()
    return raw or "https://api.openalex.org/works"


def _timeout_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(getattr(settings, "OPENALEX_API_TIMEOUT_SECONDS", 10.0))))
    except Exception:
        return 10.0


def _api_key() -> str:
    return str(getattr(settings, "OPENALEX_API_KEY", "") or "").strip()


def _mailto() -> str:
    return str(getattr(settings, "OPENALEX_MAILTO", "") or "").strip()


def _safe_text(value: Any, max_len: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _fetch_json(params: dict[str, Any]) -> Any:
    query = dict(params or {})
    key = _api_key()
    if key:
        query["api_key"] = key
    mailto = _mailto()
    if mailto:
        query["mailto"] = mailto
    url = f"{_endpoint()}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/openalex-grounder"})
    with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def _author_names(row: dict[str, Any], cap: int = 4) -> list[str]:
    out: list[str] = []
    for item in list(row.get("authorships") or []):
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        if not isinstance(author, dict):
            continue
        name = _safe_text(author.get("display_name") or "", 80)
        if not name:
            continue
        out.append(name)
        if len(out) >= max(1, cap):
            break
    return out


def _concept_names(row: dict[str, Any], cap: int = 4) -> list[str]:
    out: list[str] = []
    for item in list(row.get("concepts") or []):
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("display_name") or "", 80)
        if not name:
            continue
        out.append(name)
        if len(out) >= max(1, cap):
            break
    return out


def search_works(query: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    if not needle:
        return []
    cap = int(limit or getattr(settings, "OPENALEX_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    payload = _fetch_json({"search": needle[:200], "per-page": str(cap), "sort": "relevance_score:desc"})
    rows = payload.get("results") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for row in list(rows or [])[:cap]:
        if not isinstance(row, dict):
            continue
        source_name = ""
        primary_location = row.get("primary_location") or {}
        if isinstance(primary_location, dict):
            source = primary_location.get("source") or {}
            if isinstance(source, dict):
                source_name = _safe_text(source.get("display_name") or "", 120)
        out.append(
            {
                "id": str(row.get("id") or "").strip(),
                "title": _safe_text(row.get("display_name") or "", 240),
                "publication_year": row.get("publication_year"),
                "doi": str(row.get("doi") or "").strip(),
                "source": source_name,
                "authors": _author_names(row),
                "concepts": _concept_names(row),
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
        "[OPENALEX_API_CONTEXT]",
        f"query={_safe_text(needle, 140)}",
        f"matches={len(rows)}",
    ]
    if _mailto():
        lines.append("polite_pool=enabled")
    for idx, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").strip() or "untitled"
        lines.append(f"{idx}. {title}")
        year = row.get("publication_year")
        if year:
            lines.append(f"   year: {year}")
        source = str(row.get("source") or "").strip()
        if source:
            lines.append(f"   source: {source}")
        doi = str(row.get("doi") or "").strip()
        if doi:
            lines.append(f"   doi: {doi}")
        authors = ", ".join(list(row.get("authors") or [])[:4])
        if authors:
            lines.append(f"   authors: {authors}")
        concepts = ", ".join(list(row.get("concepts") or [])[:4])
        if concepts:
            lines.append(f"   concepts: {concepts}")
        work_id = str(row.get("id") or "").strip()
        if work_id:
            lines.append(f"   id: {work_id}")
    return "\n".join(lines).strip()
