"""
ghost_authoring.py
Bounded long-form authoring for Ghost-owned markdown documents with versioned rollback.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
import re
import time
from typing import Any, Callable, Optional

from config import settings  # type: ignore


_DOC_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_ALLOWED_SUFFIXES = {".md", ".txt"}


@dataclass
class _SectionBounds:
    start: int
    end: int
    level: int
    title: str


def _master_path() -> str:
    return os.path.abspath(
        str(getattr(settings, "GHOST_AUTHORING_MASTER_PATH", "/app/TPCV_MASTER.md") or "/app/TPCV_MASTER.md")
    )


def _works_dir() -> str:
    return os.path.abspath(
        str(getattr(settings, "GHOST_AUTHORING_WORKS_DIR", "/app/ghost_writings") or "/app/ghost_writings")
    )


def _version_root() -> str:
    return os.path.abspath(
        str(
            getattr(settings, "GHOST_AUTHORING_VERSION_STORE_DIR", os.path.join(_works_dir(), ".versions"))
            or os.path.join(_works_dir(), ".versions")
        )
    )


def _version_limit() -> int:
    return max(5, int(getattr(settings, "GHOST_AUTHORING_MAX_VERSIONS_PER_DOC", 80) or 80))


def _allowed_targets() -> list[str]:
    return [_master_path(), _works_dir()]


def _doc_key(doc_path: str) -> str:
    return hashlib.sha256(doc_path.encode("utf-8")).hexdigest()[:16]


def _action_log_path() -> str:
    return os.path.join(_version_root(), "actions.jsonl")


def resolve_document_path(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("document path is required")

    master_path = _master_path()
    works_dir = _works_dir()

    if value in {"TPCV_MASTER.md", os.path.basename(master_path), master_path}:
        return master_path

    candidate = value
    if not os.path.isabs(candidate):
        rel = candidate.lstrip("./")
        if rel.startswith("ghost_writings/"):
            rel = rel[len("ghost_writings/") :]
        candidate = os.path.join(works_dir, rel)
    candidate = os.path.abspath(candidate)

    suffix = os.path.splitext(candidate)[1].lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError("only markdown or text documents are allowed")

    works_root = works_dir.rstrip(os.sep) + os.sep
    if not candidate.startswith(works_root):
        raise ValueError("path is outside Ghost-owned authoring targets")
    return candidate


async def _read_text(path: str) -> str:
    def _read() -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    return await asyncio.to_thread(_read)


async def _write_text(path: str, content: str) -> None:
    def _write() -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    await asyncio.to_thread(_write)


async def _append_jsonl(path: str, payload: dict[str, Any]) -> None:
    def _append() -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    await asyncio.to_thread(_append)


async def _snapshot_document(
    doc_path: str,
    content: str,
    *,
    trigger: str,
    operation: str,
    reason: str,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    version_id = f"{int(time.time() * 1000)}_{hashlib.sha1(content.encode('utf-8')).hexdigest()[:10]}"
    version_dir = os.path.join(_version_root(), _doc_key(doc_path))
    payload = {
        "version_id": version_id,
        "doc_path": doc_path,
        "created_at": time.time(),
        "trigger": str(trigger or "ghost"),
        "operation": str(operation or "rewrite"),
        "reason": str(reason or ""),
        "metadata": dict(metadata or {}),
        "content": content,
    }

    def _write_version() -> None:
        os.makedirs(version_dir, exist_ok=True)
        file_path = os.path.join(version_dir, f"{version_id}.json")
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True)

        files = sorted(
            [name for name in os.listdir(version_dir) if name.endswith(".json")],
            reverse=True,
        )
        for stale in files[_version_limit() :]:
            try:
                os.remove(os.path.join(version_dir, stale))
            except OSError:
                pass

    await asyncio.to_thread(_write_version)
    return version_id


async def list_versions(path: str, limit: int = 40) -> list[dict[str, Any]]:
    doc_path = resolve_document_path(path)
    version_dir = os.path.join(_version_root(), _doc_key(doc_path))

    def _read_versions() -> list[dict[str, Any]]:
        if not os.path.isdir(version_dir):
            return []
        rows: list[dict[str, Any]] = []
        files = sorted([name for name in os.listdir(version_dir) if name.endswith(".json")], reverse=True)
        for name in files[: max(1, min(int(limit), 200))]:
            with open(os.path.join(version_dir, name), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            rows.append(
                {
                    "version_id": str(payload.get("version_id") or ""),
                    "doc_path": doc_path,
                    "created_at": float(payload.get("created_at") or 0.0),
                    "trigger": str(payload.get("trigger") or ""),
                    "operation": str(payload.get("operation") or ""),
                    "reason": str(payload.get("reason") or ""),
                    "metadata": dict(payload.get("metadata") or {}),
                    "content_length": len(str(payload.get("content") or "")),
                }
            )
        return rows

    return await asyncio.to_thread(_read_versions)


async def list_recent_actions(limit: int = 20) -> list[dict[str, Any]]:
    path = _action_log_path()

    def _read_actions() -> list[dict[str, Any]]:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        rows: list[dict[str, Any]] = []
        for line in lines[-max(1, min(int(limit), 200)) :]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(rows))

    return await asyncio.to_thread(_read_actions)


async def get_document(path: str) -> dict[str, Any]:
    doc_path = resolve_document_path(path)
    content = await _read_text(doc_path)
    versions = await list_versions(doc_path, limit=1)
    return {
        "status": "success",
        "path": doc_path,
        "exists": bool(os.path.exists(doc_path)),
        "content": content,
        "version_count": len(await list_versions(doc_path, limit=200)),
        "latest_version_id": str((versions[0] or {}).get("version_id") or "") if versions else "",
    }


def _section_bounds(text: str, heading: str) -> Optional[_SectionBounds]:
    matches = list(_HEADING_RE.finditer(text))
    target = str(heading or "").strip().lower()
    for idx, match in enumerate(matches):
        title = str(match.group(2) or "").strip()
        if title.lower() != target:
            continue
        level = len(match.group(1) or "")
        end = len(text)
        for later in matches[idx + 1 :]:
            later_level = len(later.group(1) or "")
            if later_level <= level:
                end = later.start()
                break
        return _SectionBounds(start=match.start(), end=end, level=level, title=title)
    return None


def _normalized_section_block(heading: str, body: str, level: int) -> str:
    clean_body = str(body or "").strip()
    clean_heading = str(heading or "").strip()
    block = f'{"#" * max(1, min(int(level), 6))} {clean_heading}\n\n{clean_body}\n'
    return block


def _append_block(text: str, block: str) -> str:
    base = str(text or "").rstrip()
    if not base:
        return block
    return base + "\n\n" + block


def _replace_or_append_section(text: str, heading: str, body: str, level: int) -> tuple[str, str]:
    bounds = _section_bounds(text, heading)
    block = _normalized_section_block(heading, body, level)
    if bounds is None:
        return _append_block(text, block), "created"
    return text[: bounds.start].rstrip() + "\n\n" + block + text[bounds.end :].lstrip("\n"), "updated"


def _extract_section_body(text: str, heading: str) -> tuple[Optional[str], int]:
    bounds = _section_bounds(text, heading)
    if bounds is None:
        return None, 2
    section_text = text[bounds.start : bounds.end]
    lines = section_text.splitlines()
    body = "\n".join(lines[1:]).strip()
    return body, bounds.level


def _remove_section(text: str, heading: str) -> tuple[str, bool]:
    bounds = _section_bounds(text, heading)
    if bounds is None:
        return text, False
    next_text = text[: bounds.start].rstrip() + "\n\n" + text[bounds.end :].lstrip("\n")
    return next_text.strip() + ("\n" if next_text.strip() else ""), True


async def _mutate_document(
    path: str,
    *,
    operation: str,
    trigger: str,
    requested_by: str,
    reason: str,
    metadata: Optional[dict[str, Any]],
    mutate: Callable[[str], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    doc_path = resolve_document_path(path)
    async with _DOC_LOCKS[doc_path]:
        current = await _read_text(doc_path)
        rollback_version_id = await _snapshot_document(
            doc_path,
            current,
            trigger=trigger,
            operation=operation,
            reason=reason,
            metadata=metadata,
        )
        next_content, out_meta = mutate(current)
        changed = next_content != current
        status = "updated" if changed else "noop"
        if changed:
            await _write_text(doc_path, next_content)
        action = {
            "created_at": time.time(),
            "doc_path": doc_path,
            "operation": operation,
            "trigger": trigger,
            "requested_by": requested_by,
            "reason": reason,
            "status": status,
            "rollback_version_id": rollback_version_id,
            "metadata": dict(metadata or {}) | dict(out_meta or {}),
        }
        await _append_jsonl(_action_log_path(), action)
        return {
            "status": status,
            "path": doc_path,
            "rollback_version_id": rollback_version_id,
            "changed": changed,
            "content_length": len(next_content),
            "reason": "ok" if changed else "no_change",
            "metadata": dict(out_meta or {}),
        }


async def upsert_section(
    path: str,
    heading: str,
    content: str,
    *,
    heading_level: int = 2,
    trigger: str = "ghost",
    requested_by: str = "ghost",
    reason: str = "",
) -> dict[str, Any]:
    if not str(heading or "").strip():
        return {"status": "blocked", "reason": "heading_required"}

    def _mutate(current: str) -> tuple[str, dict[str, Any]]:
        next_text, mode = _replace_or_append_section(current, heading, content, heading_level)
        return next_text, {
            "heading": heading,
            "heading_level": heading_level,
            "mode": mode,
        }

    return await _mutate_document(
        path,
        operation="upsert_section",
        trigger=trigger,
        requested_by=requested_by,
        reason=reason,
        metadata={"heading": heading, "heading_level": heading_level},
        mutate=_mutate,
    )


async def clone_section(
    path: str,
    source_heading: str,
    target_heading: str,
    *,
    trigger: str = "ghost",
    requested_by: str = "ghost",
    reason: str = "",
) -> dict[str, Any]:
    source_heading = str(source_heading or "").strip()
    target_heading = str(target_heading or "").strip()
    if not source_heading or not target_heading:
        return {"status": "blocked", "reason": "source_and_target_heading_required"}

    def _mutate(current: str) -> tuple[str, dict[str, Any]]:
        body, level = _extract_section_body(current, source_heading)
        if body is None:
            raise ValueError("source_heading_not_found")
        next_text, _ = _replace_or_append_section(current, target_heading, body, level)
        return next_text, {"source_heading": source_heading, "target_heading": target_heading}

    try:
        return await _mutate_document(
            path,
            operation="clone_section",
            trigger=trigger,
            requested_by=requested_by,
            reason=reason,
            metadata={"source_heading": source_heading, "target_heading": target_heading},
            mutate=_mutate,
        )
    except ValueError:
        return {"status": "blocked", "reason": "source_heading_not_found"}


async def merge_sections(
    path: str,
    target_heading: str,
    source_headings: list[str],
    *,
    remove_sources: bool = True,
    trigger: str = "ghost",
    requested_by: str = "ghost",
    reason: str = "",
) -> dict[str, Any]:
    target_heading = str(target_heading or "").strip()
    sources = [str(v).strip() for v in (source_headings or []) if str(v).strip()]
    if not target_heading or not sources:
        return {"status": "blocked", "reason": "target_and_sources_required"}

    def _mutate(current: str) -> tuple[str, dict[str, Any]]:
        merged_parts: list[str] = []
        target_body, target_level = _extract_section_body(current, target_heading)
        if target_body:
            merged_parts.append(target_body)
        if target_level <= 0:
            target_level = 2
        consumed: list[str] = []
        next_text = current
        for heading in sources:
            if heading.lower() == target_heading.lower():
                continue
            body, _ = _extract_section_body(next_text, heading)
            if body is None:
                continue
            merged_parts.append(body)
            consumed.append(heading)
            if remove_sources:
                next_text, _ = _remove_section(next_text, heading)
        if not consumed and not target_body:
            raise ValueError("no_source_sections_found")
        merged_body = "\n\n".join(part.strip() for part in merged_parts if part.strip())
        next_text, mode = _replace_or_append_section(next_text, target_heading, merged_body, target_level)
        return next_text, {"target_heading": target_heading, "merged_sources": consumed, "mode": mode}

    try:
        return await _mutate_document(
            path,
            operation="merge_sections",
            trigger=trigger,
            requested_by=requested_by,
            reason=reason,
            metadata={"target_heading": target_heading, "source_headings": sources, "remove_sources": remove_sources},
            mutate=_mutate,
        )
    except ValueError:
        return {"status": "blocked", "reason": "no_source_sections_found"}


async def rewrite_document(
    path: str,
    content: str,
    *,
    trigger: str = "ghost",
    requested_by: str = "ghost",
    reason: str = "",
) -> dict[str, Any]:
    return await _mutate_document(
        path,
        operation="rewrite_document",
        trigger=trigger,
        requested_by=requested_by,
        reason=reason,
        metadata={},
        mutate=lambda _current: (str(content or ""), {"rewrite": True}),
    )


async def restore_version(
    path: str,
    version_id: str,
    *,
    trigger: str = "operator_restore",
    requested_by: str = "operator",
    reason: str = "",
) -> dict[str, Any]:
    doc_path = resolve_document_path(path)
    version_dir = os.path.join(_version_root(), _doc_key(doc_path))
    file_path = os.path.join(version_dir, f"{str(version_id or '').strip()}.json")
    if not os.path.exists(file_path):
        return {"status": "blocked", "reason": "version_not_found", "path": doc_path}

    def _load_version() -> str:
        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return str(payload.get("content") or "")

    target_content = await asyncio.to_thread(_load_version)
    result = await _mutate_document(
        doc_path,
        operation="restore_version",
        trigger=trigger,
        requested_by=requested_by,
        reason=reason or f"restore:{version_id}",
        metadata={"restore_version_id": version_id},
        mutate=lambda _current: (target_content, {"restored_version_id": version_id}),
    )
    result["restored_version_id"] = str(version_id or "")
    return result


async def get_status_summary() -> dict[str, Any]:
    master_path = _master_path()
    works_dir = _works_dir()
    version_root = _version_root()
    recent_actions = await list_recent_actions(limit=20)

    def _scan() -> dict[str, Any]:
        doc_count = 0
        if os.path.exists(master_path):
            doc_count += 1
        if os.path.isdir(works_dir):
            for root, _dirs, files in os.walk(works_dir):
                if os.path.abspath(root).startswith(version_root.rstrip(os.sep) + os.sep):
                    continue
                for name in files:
                    if os.path.splitext(name)[1].lower() in _ALLOWED_SUFFIXES:
                        doc_count += 1
        version_count = 0
        if os.path.isdir(version_root):
            for root, _dirs, files in os.walk(version_root):
                for name in files:
                    if name.endswith(".json") and name != os.path.basename(_action_log_path()):
                        version_count += 1
        return {
            "master_path": master_path,
            "works_dir": works_dir,
            "version_store_dir": version_root,
            "document_count": doc_count,
            "version_count": version_count,
        }

    summary = await asyncio.to_thread(_scan)
    summary["recent_action_count"] = len(recent_actions)
    summary["recent_actions"] = recent_actions[:10]
    return summary


async def get_prompt_context(limit: int = 6) -> str:
    summary = await get_status_summary()
    actions = list(summary.get("recent_actions") or [])
    lines = [
        f"- master_draft: `{summary.get('master_path')}`",
        f"- works_dir: `{summary.get('works_dir')}`",
        f"- version_store: `{summary.get('version_store_dir')}`",
        f"- document_count: {int(summary.get('document_count') or 0)}",
        f"- version_count: {int(summary.get('version_count') or 0)}",
    ]
    for row in actions[: max(0, int(limit))]:
        lines.append(
            f"- recent_action: {row.get('operation') or 'unknown'} target=`{row.get('doc_path') or ''}` status={row.get('status') or 'unknown'}"
        )
    return "\n".join(lines)
