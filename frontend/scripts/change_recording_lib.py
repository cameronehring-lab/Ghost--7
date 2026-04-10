#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_WORKSPACE = Path("/Users/cehring/Downloads/uap-research-workspace")
RECORD_FIELDS = [
    "record_id",
    "timestamp_utc",
    "operator",
    "change_type",
    "reason",
    "source_url",
    "archive_url",
    "retrieval_timestamp",
    "artifact_hash",
    "related_entity_ids",
    "related_event_ids",
    "supersedes_record_id",
    "confidence",
    "claim_status",
]
CHANGE_TYPES = {"create", "update", "status_change", "supersede", "invalidate"}
CLAIM_STATUSES = {"", "claim", "corroborated", "disputed", "debunked"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    target = dt or utc_now()
    return target.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_timestamp(dt: datetime | None = None) -> str:
    target = dt or utc_now()
    return target.astimezone().replace(microsecond=0).strftime("%Y-%m-%d %H:%M %Z")


def compact_timestamp(dt: datetime | None = None) -> str:
    target = dt or utc_now()
    return target.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def operator_name() -> str:
    return (
        os.environ.get("CODEX_OPERATOR")
        or os.environ.get("USER")
        or os.environ.get("LOGNAME")
        or "unknown-operator"
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "entry"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_parent(path: Path) -> None:
    ensure_dir(path.parent)


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def append_text(path: Path, content: str) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    append_text(path, json.dumps(row, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def default_record(
    record_id: str,
    *,
    reason: str,
    change_type: str = "create",
    operator: str | None = None,
    source_url: str = "",
    archive_url: str = "",
    retrieval_timestamp: str | None = None,
    artifact_hash: str = "",
    related_entity_ids: Iterable[str] | None = None,
    related_event_ids: Iterable[str] | None = None,
    supersedes_record_id: str = "",
    confidence: float = 1.0,
    claim_status: str = "",
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "timestamp_utc": iso_utc(),
        "operator": operator or operator_name(),
        "change_type": change_type,
        "reason": reason,
        "source_url": source_url,
        "archive_url": archive_url,
        "retrieval_timestamp": retrieval_timestamp or iso_utc(),
        "artifact_hash": artifact_hash,
        "related_entity_ids": list(related_entity_ids or []),
        "related_event_ids": list(related_event_ids or []),
        "supersedes_record_id": supersedes_record_id,
        "confidence": confidence,
        "claim_status": claim_status,
    }


def record_id(prefix: str, label: str | None = None, *, dt: datetime | None = None) -> str:
    parts = [slugify(prefix), compact_timestamp(dt)]
    if label:
        parts.append(slugify(label))
    return "-".join(parts)


def sha256_for_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guessed_mime_type(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def resolve_workspace(path: str | None = None) -> Path:
    return Path(path).expanduser().resolve() if path else DEFAULT_WORKSPACE


def sort_records(rows: list[dict[str, Any]], *, primary: str = "timestamp_utc") -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[str, str]:
        return (str(row.get(primary, "")), str(row.get("record_id", "")))

    return sorted(rows, key=key)


def build_timeline_markdown(events: list[dict[str, Any]]) -> str:
    generated = iso_utc()
    lines = [
        "# UAP Research Timeline",
        "",
        f"Generated: {generated}",
        "",
        "## Visual Timeline",
        "",
        "```mermaid",
        "timeline",
        "    title UAP Research Timeline",
    ]
    if events:
        for row in sort_records(events, primary="event_date"):
            event_date = str(row.get("event_date") or row.get("timestamp_utc", ""))[:10]
            title = str(row.get("title") or row.get("record_id"))
            summary = str(row.get("summary") or row.get("reason") or "").strip()
            label = title if not summary else f"{title}: {summary}"
            label = label.replace('"', "'")
            lines.append(f"    {event_date} : {label}")
    else:
        lines.append("    1970-01-01 : No events recorded yet")
    lines.extend(["```", "", "## Event Log", ""])
    if events:
        for row in sort_records(events, primary="event_date"):
            event_date = str(row.get("event_date") or row.get("timestamp_utc", ""))[:10]
            title = str(row.get("title") or row.get("record_id"))
            summary = str(row.get("summary") or row.get("reason") or "").strip()
            category = str(row.get("category") or "uncategorized")
            lines.append(f"- {event_date} - **{title}** [{category}]")
            if summary:
                lines.append(f"  {summary}")
    else:
        lines.append("- No timeline events recorded yet.")
    lines.append("")
    return "\n".join(lines)


def build_evidence_markdown(
    *,
    sources: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> str:
    generated = iso_utc()
    lines = [
        "# Evidence Log",
        "",
        f"Generated: {generated}",
        "",
        "## Totals",
        "",
        "| Ledger | Records |",
        "| --- | ---: |",
        f"| sources | {len(sources)} |",
        f"| captures | {len(captures)} |",
        f"| artifacts | {len(artifacts)} |",
        f"| claims | {len(claims)} |",
        f"| events | {len(events)} |",
        "",
        "## Recent Activity",
        "",
    ]
    activity: list[tuple[str, str]] = []
    for ledger_name, rows in (
        ("source", sources),
        ("capture", captures),
        ("artifact", artifacts),
        ("claim", claims),
        ("event", events),
    ):
        for row in rows:
            timestamp = str(row.get("timestamp_utc") or row.get("event_date") or "")
            title = str(row.get("title") or row.get("summary") or row.get("reason") or row.get("record_id"))
            activity.append((timestamp, f"- {timestamp} - [{ledger_name}] {title}"))
    for _, line in sorted(activity, reverse=True)[:20]:
        lines.append(line)
    if not activity:
        lines.append("- No evidence records have been ingested yet.")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Interpretive changes should append superseding rows instead of rewriting history.",
            "- Large artifacts should remain outside Git history and be tracked by hash and path.",
            "",
        ]
    )
    return "\n".join(lines)
