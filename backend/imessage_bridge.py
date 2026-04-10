"""
imessage_bridge.py
Polls macOS Messages chat.db for inbound iMessage rows and forwards them into
the async Ghost runtime callback path.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
from typing import Awaitable, Callable, Optional

import person_rolodex  # type: ignore

logger = logging.getLogger("omega.imessage_bridge")


@dataclass(frozen=True)
class IMessageBridgeRecord:
    rowid: int
    guid: str
    text: str
    handle: str
    service: str
    raw_date: Optional[int]


class IMessageBridge:
    def __init__(
        self,
        *,
        db_path: str,
        poll_interval_seconds: float,
        batch_size: int,
        on_message: Callable[[IMessageBridgeRecord], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self.batch_size = max(1, int(batch_size))
        self.on_message = on_message
        self.loop = loop
        self._last_rowid: int = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_rowid = self._read_max_rowid()
        self._thread = threading.Thread(
            target=self._run,
            name="omega-imessage-bridge",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "iMessage bridge started: db=%s last_rowid=%s interval=%.2fs batch=%d",
            self.db_path,
            self._last_rowid,
            self.poll_interval_seconds,
            self.batch_size,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, 2.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                records = self._poll_new_messages(self._last_rowid)
                if records:
                    for record in records:
                        self._schedule(record)
                    self._last_rowid = max(self._last_rowid, records[-1].rowid)
            except Exception as e:
                logger.warning("iMessage bridge poll failure: %s", e)
            self._stop_event.wait(self.poll_interval_seconds)

    def _schedule(self, record: IMessageBridgeRecord) -> None:
        future = asyncio.run_coroutine_threadsafe(self.on_message(record), self.loop)

        def _done(fut):
            try:
                fut.result()
            except Exception as e:
                logger.warning("iMessage bridge callback failed rowid=%s: %s", record.rowid, e)

        future.add_done_callback(_done)

    def _read_max_rowid(self) -> int:
        sql = "SELECT COALESCE(MAX(ROWID), 0) FROM message"
        rows = self._query_snapshot(sql, tuple())
        if not rows:
            return 0
        try:
            return int(rows[0][0] or 0)
        except Exception:
            return 0

    def _poll_new_messages(self, last_rowid: int) -> list[IMessageBridgeRecord]:
        sql = """
            SELECT
                m.ROWID,
                COALESCE(m.guid, '') AS guid,
                COALESCE(m.text, '') AS text,
                COALESCE(h.id, '') AS handle_id,
                COALESCE(h.service, '') AS service,
                m.date
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE m.ROWID > ?
              AND m.is_from_me = 0
            ORDER BY m.ROWID ASC
            LIMIT ?
        """
        rows = self._query_snapshot(sql, (int(last_rowid), int(self.batch_size)))
        out: list[IMessageBridgeRecord] = []
        for row in rows:
            text = str(row[2] or "").strip()
            if not text:
                continue
            service = str(row[4] or "").strip()
            if service and service.lower() != "imessage":
                continue
            handle = person_rolodex.normalize_contact_handle(str(row[3] or ""))
            if not handle:
                continue
            out.append(
                IMessageBridgeRecord(
                    rowid=int(row[0]),
                    guid=str(row[1] or ""),
                    text=text,
                    handle=handle,
                    service=service,
                    raw_date=(int(row[5]) if row[5] is not None else None),
                )
            )
        return out

    def _query_snapshot(self, sql: str, params: tuple) -> list[tuple]:
        if not self.db_path.exists():
            return []

        with tempfile.TemporaryDirectory(prefix="omega_imessage_") as tmpdir:
            tmp_root = Path(tmpdir)
            snap_db = tmp_root / "chat.db"
            shutil.copy2(self.db_path, snap_db)
            wal_src = Path(str(self.db_path) + "-wal")
            shm_src = Path(str(self.db_path) + "-shm")
            if wal_src.exists():
                shutil.copy2(wal_src, tmp_root / "chat.db-wal")
            if shm_src.exists():
                shutil.copy2(shm_src, tmp_root / "chat.db-shm")

            conn = sqlite3.connect(str(snap_db))
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [tuple(r) for r in rows]
            finally:
                conn.close()
