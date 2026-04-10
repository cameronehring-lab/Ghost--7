"""
arXiv API metadata client (legacy API compatible pacing).

Compliance defaults:
- metadata-only usage
- single-connection lock
- minimum interval between requests (default: 3 seconds)
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Optional

from config import settings  # type: ignore


logger = logging.getLogger("omega.arxiv_api")

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_TS = 0.0


def _endpoint() -> str:
    raw = str(getattr(settings, "ARXIV_API_ENDPOINT", "") or "").strip()
    return raw or "https://export.arxiv.org/api/query"


def _timeout_seconds() -> float:
    try:
        return max(2.0, min(30.0, float(getattr(settings, "ARXIV_API_TIMEOUT_SECONDS", 10.0))))
    except Exception:
        return 10.0


def _min_interval_seconds() -> float:
    try:
        return max(3.0, min(30.0, float(getattr(settings, "ARXIV_API_MIN_INTERVAL_SECONDS", 3.0))))
    except Exception:
        return 3.0


def _safe_text(value: Any, max_len: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _enforce_rate_limit_locked() -> None:
    global _LAST_REQUEST_TS
    now = time.time()
    gap = now - _LAST_REQUEST_TS
    min_gap = _min_interval_seconds()
    if gap < min_gap:
        time.sleep(min_gap - gap)
    _LAST_REQUEST_TS = time.time()


def _fetch_atom_xml(search_query: str, *, start: int = 0, max_results: int = 3) -> str:
    params = {
        "search_query": search_query,
        "start": str(max(0, int(start))),
        "max_results": str(max(1, min(int(max_results), 10))),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{_endpoint()}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "OMEGA4/arxiv-metadata-grounder"})
    with _REQUEST_LOCK:
        _enforce_rate_limit_locked()
        with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")


def _entry_text(node: ET.Element, tag: str, ns: dict[str, str], default: str = "") -> str:
    el = node.find(tag, ns)
    if el is None:
        return default
    return str(el.text or "").strip()


def _parse_entries(xml_text: str) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(xml_text)
    out: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title = _safe_text(_entry_text(entry, "atom:title", ns), max_len=240)
        summary = _safe_text(_entry_text(entry, "atom:summary", ns), max_len=420)
        published = _entry_text(entry, "atom:published", ns)
        updated = _entry_text(entry, "atom:updated", ns)
        arxiv_id_url = _entry_text(entry, "atom:id", ns)
        doi = _entry_text(entry, "arxiv:doi", ns)
        categories = [str(node.attrib.get("term") or "").strip() for node in entry.findall("atom:category", ns)]
        categories = [c for c in categories if c]
        authors = []
        for author in entry.findall("atom:author", ns):
            name = _entry_text(author, "atom:name", ns)
            if name:
                authors.append(name)
        link = ""
        for node in entry.findall("atom:link", ns):
            rel = str(node.attrib.get("rel") or "").strip()
            href = str(node.attrib.get("href") or "").strip()
            if rel == "alternate" and href:
                link = href
                break
        if not link:
            link = arxiv_id_url
        out.append(
            {
                "id_url": arxiv_id_url,
                "title": title,
                "summary": summary,
                "published": published,
                "updated": updated,
                "authors": authors[:8],
                "categories": categories[:8],
                "doi": doi,
                "link": link,
            }
        )
    return out


def search_metadata(query: str, *, max_results: Optional[int] = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip()
    if not needle:
        return []
    cap = int(max_results or getattr(settings, "ARXIV_API_MAX_RESULTS", 3) or 3)
    cap = max(1, min(cap, 10))
    xml_text = _fetch_atom_xml(f"all:{needle}", max_results=cap)
    return _parse_entries(xml_text)[:cap]


def build_query_context(query: str) -> str:
    needle = str(query or "").strip()
    if not needle:
        return ""
    results = search_metadata(needle)
    if not results:
        return ""

    ack = str(getattr(settings, "ARXIV_API_ACKNOWLEDGEMENT", "") or "").strip()
    lines = [
        "[ARXIV_API_CONTEXT]",
        f"query={_safe_text(needle, max_len=140)}",
        f"matches={len(results)}",
        "compliance=metadata_only",
    ]
    if ack:
        lines.append(f"acknowledgement={ack}")

    for idx, row in enumerate(results, start=1):
        lines.append(f"{idx}. {row.get('title') or 'untitled'}")
        authors = ", ".join(list(row.get("authors") or [])[:4])
        if authors:
            lines.append(f"   authors: {authors}")
        categories = ", ".join(list(row.get("categories") or [])[:4])
        if categories:
            lines.append(f"   categories: {categories}")
        pub = str(row.get("published") or "").strip()
        if pub:
            lines.append(f"   published: {pub}")
        link = str(row.get("link") or "").strip()
        if link:
            lines.append(f"   link: {link}")
        summary = str(row.get("summary") or "").strip()
        if summary:
            lines.append(f"   summary: {summary}")

    return "\n".join(lines).strip()
