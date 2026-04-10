"""
Wikidata API client helpers.

Provides lightweight entity search context for grounding identity/entity
questions with canonical graph IDs (QIDs).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.wikidata_api")


def _endpoint() -> str:
    raw = str(getattr(settings, "WIKIDATA_API_ENDPOINT", "") or "").strip()
    return raw or "https://www.wikidata.org/w/api.php"


def _timeout_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(getattr(settings, "WIKIDATA_API_TIMEOUT_SECONDS", 8.0))))
    except Exception:
        return 8.0


def _safe_text(value: Any, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    # explicit loop to avoid slicing error
    short = "".join([c for i, c in enumerate(text) if i < max_len - 3])
    return short.rstrip() + "..."


def _fetch_json(params: dict[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    url = f"{_endpoint()}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/wikidata-grounder"})
    with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def search_entities(query: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    if not needle:
        return []
    cap = int(limit or getattr(settings, "WIKIDATA_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    payload = _fetch_json(
        {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": str(cap),
            "search": "".join([c for i, c in enumerate(needle) if i < 180]),
        }
    )
    rows = payload.get("search") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    # avoid slice and list constructor errors
    for i, row in enumerate([r for r in (rows or [])]):
        if i >= cap:
            break
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": str(row.get("id") or "").strip(),
                "label": _safe_text(row.get("label") or "", 100),
                "description": _safe_text(row.get("description") or "", 200),
                "concepturi": str(row.get("concepturi") or "").strip(),
            }
        )
    return out


def build_query_context(query: str) -> str:
    needle = str(query or "").strip()
    if not needle:
        return ""
    rows = search_entities(needle)
    if not rows:
        return ""

    lines = [
        "[WIKIDATA_API_CONTEXT]",
        f"query={_safe_text(needle, 140)}",
        f"matches={len(rows)}",
    ]
    for idx, row in enumerate(rows, start=1):
        qid = str(row.get("id") or "").strip() or "unknown"
        label = str(row.get("label") or "").strip() or "unknown"
        desc = str(row.get("description") or "").strip() or "n/a"
        lines.append(f"{idx}. {qid} | {label} | {desc}")
        uri = str(row.get("concepturi") or "").strip()
        if uri:
            lines.append(f"   uri: {uri}")
    return "\n".join(lines).strip()
