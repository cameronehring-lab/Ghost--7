"""
Philosophers API client helpers.

Provides lightweight retrieval + context formatting so Ghost can ground
philosophy-related turns with structured external data.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.philosophers_api")


def _base_url() -> str:
    raw = str(getattr(settings, "PHILOSOPHERS_API_BASE_URL", "") or "").strip()
    return raw.rstrip("/") if raw else "https://philosophersapi.com"


def _timeout_seconds() -> float:
    try:
        return max(1.0, min(30.0, float(getattr(settings, "PHILOSOPHERS_API_TIMEOUT_SECONDS", 8.0))))
    except Exception:
        return 8.0


def _safe_text(value: Any, max_len: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _fetch_json(path: str) -> Any:
    base = _base_url()
    url = f"{base}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/ghost-philosophy-grounder"})
    with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def _extract_quotes(payload: dict[str, Any], limit: int = 2) -> list[str]:
    candidates = payload.get("quotes") or payload.get("famousQuotes") or payload.get("famous_quotes") or []
    out: list[str] = []
    for row in list(candidates or []):
        if isinstance(row, dict):
            text = row.get("quote") or row.get("text") or row.get("content") or ""
        else:
            text = row
        cleaned = _safe_text(text, max_len=220)
        if not cleaned:
            continue
        out.append(cleaned)
        if len(out) >= max(1, limit):
            break
    return out


def _extract_key_ideas(payload: dict[str, Any], limit: int = 4) -> list[str]:
    candidates = payload.get("keyIdeas") or payload.get("key_ideas") or payload.get("ideas") or []
    out: list[str] = []
    for row in list(candidates or []):
        if isinstance(row, dict):
            text = row.get("idea") or row.get("name") or row.get("title") or row.get("description") or ""
        else:
            text = row
        cleaned = _safe_text(text, max_len=140)
        if not cleaned:
            continue
        out.append(cleaned)
        if len(out) >= max(1, limit):
            break
    return out


def search_philosophers(keyword: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(keyword or "").strip()
    if not needle:
        return []
    cap = int(limit or getattr(settings, "PHILOSOPHERS_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    q = urllib.parse.quote_plus(needle[:120])
    payload = _fetch_json(f"/api/philosophers/search?keyword={q}")
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in payload[:cap]:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "id": str(row.get("id") or "").strip(),
                "name": _safe_text(row.get("name") or row.get("wikiTitle") or "", 90),
                "life": _safe_text(row.get("life") or "", 40),
                "school": _safe_text(row.get("school") or "", 80),
                "interests": _safe_text(row.get("interests") or "", 220),
                "spe_link": str(row.get("speLink") or "").strip(),
                "iep_link": str(row.get("iepLink") or "").strip(),
            }
        )
    return rows


def fetch_philosopher_details_by_name(name: str) -> Optional[dict[str, Any]]:
    raw = str(name or "").strip()
    if not raw:
        return None
    encoded = urllib.parse.quote_plus(raw)
    payload = _fetch_json(f"/api/philosophers/name/{encoded}")
    if not isinstance(payload, dict):
        return None
    details = {
        "id": str(payload.get("id") or "").strip(),
        "name": _safe_text(payload.get("name") or payload.get("wikiTitle") or raw, 90),
        "life": _safe_text(payload.get("life") or "", 40),
        "school": _safe_text(payload.get("school") or "", 80),
        "interests": _safe_text(payload.get("interests") or "", 260),
        "spe_link": str(payload.get("speLink") or "").strip(),
        "iep_link": str(payload.get("iepLink") or "").strip(),
        "quotes": _extract_quotes(payload),
        "key_ideas": _extract_key_ideas(payload),
        "has_ebooks": bool(payload.get("hasEBooks")),
    }
    return details


def build_query_context(query: str) -> str:
    needle = str(query or "").strip()
    if not needle:
        return ""
    rows = search_philosophers(needle)
    if not rows:
        return ""

    lines = [
        "[PHILOSOPHERS_API_CONTEXT]",
        f"query={_safe_text(needle, max_len=120)}",
        f"matches={len(rows)}",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"{idx}. {row.get('name') or 'unknown'} | {row.get('life') or 'n/a'} | school={row.get('school') or 'n/a'}"
        )
        interests = str(row.get("interests") or "").strip()
        if interests:
            lines.append(f"   interests: {interests}")
        spe = str(row.get("spe_link") or "").strip()
        iep = str(row.get("iep_link") or "").strip()
        if spe:
            lines.append(f"   spe: {spe}")
        if iep:
            lines.append(f"   iep: {iep}")

    # Try one richer detail payload for the top match.
    top_name = str(rows[0].get("name") or "").strip()
    if top_name:
        try:
            details = fetch_philosopher_details_by_name(top_name)
        except Exception as exc:
            logger.debug("Philosophers API detail fetch failed for %s: %s", top_name, exc)
            details = None
        if details:
            key_ideas = list(details.get("key_ideas") or [])[:4]
            quotes = list(details.get("quotes") or [])[:2]
            if key_ideas:
                lines.append("top_match_key_ideas:")
                for item in key_ideas:
                    lines.append(f"- {item}")
            if quotes:
                lines.append("top_match_quotes:")
                for item in quotes:
                    lines.append(f"- \"{item}\"")
            if bool(details.get("has_ebooks")):
                lines.append("top_match_has_ebooks=true")

    return "\n".join(lines).strip()
