"""
Ephemeral Ghost-contact thread store with Redis primary + in-memory fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger("omega.contact_threads")

_THREAD_KEY_RE = re.compile(r"[^a-z0-9_+@.-]+")
_VERBATIM_TURN_CAP = 12
_MAX_SUMMARY_CHARS = 4000
_MAX_TEXT_CHARS = 2000
_MAX_SUMMARY_ITEMS = 8


def normalize_thread_key(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "unknown_thread"
    normalized = _THREAD_KEY_RE.sub("_", value).strip("_")
    return normalized[:120] or "unknown_thread"


def _clip(text: str, cap: int) -> str:
    val = str(text or "").strip()
    if len(val) <= cap:
        return val
    return val[: max(0, cap - 1)].rstrip() + "…"


def _summary_from_turns(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return ""
    rows: list[str] = []
    for turn in turns[-_MAX_SUMMARY_ITEMS:]:
        direction = str(turn.get("direction") or "").strip().lower()
        marker = "IN" if direction == "inbound" else "OUT"
        snippet = _clip(str(turn.get("text") or ""), 120)
        if snippet:
            rows.append(f"{marker}: {snippet}")
    if not rows:
        return ""
    return "Earlier thread context: " + " | ".join(rows)


def _merge_summary(existing: str, addition: str) -> str:
    cur = str(existing or "").strip()
    add = str(addition or "").strip()
    if not cur:
        merged = add
    elif not add:
        merged = cur
    else:
        merged = f"{cur}\n{add}"
    if len(merged) <= _MAX_SUMMARY_CHARS:
        return merged
    return merged[-_MAX_SUMMARY_CHARS:]


class EphemeralContactThreadStore:
    def __init__(self, *, redis_url: str, ttl_seconds: int = 86400) -> None:
        self.redis_url = str(redis_url or "").strip()
        self.ttl_seconds = max(60, int(ttl_seconds or 86400))
        self._redis: Any = None
        self._redis_checked = False
        self._redis_enabled = False
        self._locks: dict[str, asyncio.Lock] = {}
        self._memory: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        await self._ensure_redis()

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
        self._redis = None
        self._redis_checked = True
        self._redis_enabled = False

    async def status(self) -> dict[str, Any]:
        await self._ensure_redis()
        backend = "redis" if self._redis_enabled else "memory"
        return {
            "backend": backend,
            "ttl_seconds": self.ttl_seconds,
        }

    async def append_turn(
        self,
        *,
        thread_key: str,
        person_key: str,
        contact_handle: str,
        direction: str,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        key = normalize_thread_key(thread_key)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            thread = await self._read_thread(key)
            now = time.time()
            if not thread:
                thread = {
                    "thread_key": key,
                    "person_key": str(person_key or "").strip(),
                    "contact_handle": str(contact_handle or "").strip(),
                    "turns": [],
                    "compact_summary": "",
                    "updated_at": now,
                }

            turns = list(thread.get("turns") or [])
            turns.append(
                {
                    "direction": str(direction or "").strip().lower() or "inbound",
                    "text": _clip(str(text or ""), _MAX_TEXT_CHARS),
                    "timestamp": now,
                    "metadata": dict(metadata or {}),
                }
            )

            if len(turns) > _VERBATIM_TURN_CAP:
                overflow = turns[:-_VERBATIM_TURN_CAP]
                turns = turns[-_VERBATIM_TURN_CAP:]
                added_summary = _summary_from_turns(overflow)
                thread["compact_summary"] = _merge_summary(
                    str(thread.get("compact_summary") or ""),
                    added_summary,
                )

            thread["thread_key"] = key
            if person_key:
                thread["person_key"] = str(person_key).strip()
            if contact_handle:
                thread["contact_handle"] = str(contact_handle).strip()
            thread["turns"] = turns
            thread["updated_at"] = now
            await self._write_thread(key, thread)
            return dict(thread)

    async def get_thread(self, thread_key: str) -> dict[str, Any]:
        key = normalize_thread_key(thread_key)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            thread = await self._read_thread(key)
            if not thread:
                return {
                    "thread_key": key,
                    "person_key": "",
                    "contact_handle": "",
                    "turns": [],
                    "compact_summary": "",
                    "updated_at": 0.0,
                }
            return dict(thread)

    async def build_history(self, thread_key: str, *, max_turns: int = 12) -> list[dict[str, Any]]:
        key = normalize_thread_key(thread_key)
        thread = await self.get_thread(key)
        summary = str(thread.get("compact_summary") or "").strip()
        history: list[dict[str, Any]] = []
        if summary:
            history.append(
                {
                    "role": "model",
                    "content": f"[COMPACT_THREAD_SUMMARY]\n{summary}",
                    "timestamp": float(thread.get("updated_at") or 0.0),
                }
            )
        for turn in list(thread.get("turns") or [])[-max(1, int(max_turns)):]:
            direction = str(turn.get("direction") or "").strip().lower()
            role = "user" if direction == "inbound" else "model"
            history.append(
                {
                    "role": role,
                    "content": str(turn.get("text") or ""),
                    "timestamp": float(turn.get("timestamp") or 0.0),
                }
            )
        return history

    async def _ensure_redis(self) -> None:
        if self._redis_checked:
            return
        self._redis_checked = True
        self._redis_enabled = False
        if not self.redis_url:
            logger.info("Contact thread store: Redis URL not configured, using memory fallback")
            return
        try:
            import redis.asyncio as redis  # type: ignore

            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            self._redis_enabled = True
            logger.info("Contact thread store: Redis backend enabled")
        except Exception as exc:
            self._redis = None
            self._redis_enabled = False
            logger.warning("Contact thread store: Redis unavailable (%s), using memory fallback", exc)

    async def _read_thread(self, thread_key: str) -> Optional[dict[str, Any]]:
        await self._ensure_redis()
        if self._redis_enabled and self._redis is not None:
            try:
                raw = await self._redis.get(self._redis_key(thread_key))
                if not raw:
                    return None
                decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                loaded = json.loads(decoded)
                if isinstance(loaded, dict):
                    return loaded
            except Exception as exc:
                logger.warning("Contact thread redis read failed: %s", exc)
                self._redis_enabled = False

        self._prune_memory_expired()
        row = self._memory.get(thread_key)
        if not row:
            return None
        return dict(row.get("thread") or {})

    async def _write_thread(self, thread_key: str, thread: dict[str, Any]) -> None:
        await self._ensure_redis()
        if self._redis_enabled and self._redis is not None:
            try:
                await self._redis.set(
                    self._redis_key(thread_key),
                    json.dumps(thread),
                    ex=self.ttl_seconds,
                )
                return
            except Exception as exc:
                logger.warning("Contact thread redis write failed: %s", exc)
                self._redis_enabled = False

        self._memory[thread_key] = {
            "expires_at": time.time() + float(self.ttl_seconds),
            "thread": dict(thread),
        }
        self._prune_memory_expired()

    def _redis_key(self, thread_key: str) -> str:
        return f"ghost:contact_thread:{thread_key}"

    def _prune_memory_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._memory.items() if float(v.get("expires_at") or 0.0) <= now]
        for key in expired:
            self._memory.pop(key, None)

