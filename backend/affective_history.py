"""
affective_history.py
Rolling affective-state history buffer with optional InfluxDB backing.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Optional

from influxdb_client.client.influxdb_client import InfluxDBClient  # type: ignore
from influxdb_client.client.write_api import SYNCHRONOUS  # type: ignore

from config import settings  # type: ignore

logger = logging.getLogger("omega.affective_history")

_AFFECT_AXES = ("arousal", "valence", "stress", "coherence", "anxiety")


def _clip01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _clip11(value: Any) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _escape_lp_token(raw: str) -> str:
    return str(raw).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _normalize_affect(sample: dict[str, Any] | None) -> dict[str, float]:
    src = dict(sample or {})
    return {
        "arousal": _clip01(src.get("arousal", 0.0)),
        "valence": _clip11(src.get("valence", 0.0)),
        "stress": _clip01(src.get("stress", 0.0)),
        "coherence": _clip01(src.get("coherence", 1.0)),
        "anxiety": _clip01(src.get("anxiety", 0.0)),
    }


class AffectiveHistoryBuffer:
    def __init__(self, max_points: int = 480):
        self.max_points = max(32, int(max_points))
        self._rows: deque[dict[str, Any]] = deque(maxlen=self.max_points)
        self._lock = threading.Lock()
        self._influx_client: Optional[InfluxDBClient] = None
        self._write_api = None  # Cached SYNCHRONOUS write_api
        self._hydrated = False
        self._last_persist_ts = 0.0

    def set_influx_client(self, client: Optional[InfluxDBClient]) -> None:
        with self._lock:
            self._influx_client = client
            # Pre-create SYNCHRONOUS write_api once to avoid RxPY thread leak
            self._write_api = client.write_api(write_options=SYNCHRONOUS) if client else None

    def hydrate_from_influx(self, limit: int = 180, force: bool = False) -> int:
        with self._lock:
            if self._hydrated and not force:
                return 0
            client = self._influx_client

        if client is None:
            with self._lock:
                self._hydrated = True
            return 0

        query = f'''
        from(bucket: "{settings.INFLUXDB_BUCKET}")
          |> range(start: -6h)
          |> filter(fn: (r) => r["_measurement"] == "affective_state")
          |> filter(fn: (r) => r["_field"] == "arousal" or r["_field"] == "valence" or r["_field"] == "stress" or r["_field"] == "coherence" or r["_field"] == "anxiety" or r["_field"] == "surprise")
          |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
          |> sort(columns:["_time"], desc: false)
          |> limit(n:{max(1, min(int(limit), self.max_points))})
        '''

        loaded: list[dict[str, Any]] = []
        try:
            query_api = client.query_api()
            tables = query_api.query(query, org=settings.INFLUXDB_ORG)
            for table in tables:
                for rec in table.records:
                    values = dict(getattr(rec, "values", {}) or {})
                    ts_raw = values.get("_time")
                    ts = float(getattr(ts_raw, "timestamp", lambda: time.time())()) if ts_raw else time.time()
                    affect = _normalize_affect(values)
                    row = {
                        "timestamp": float(ts),
                        **affect,
                        "surprise": _clip01(values.get("surprise", 0.0)),
                        "source": "influx",
                    }
                    loaded.append(row)
        except Exception as exc:
            logger.debug("Affective history hydration skipped: %s", exc)
            loaded = []

        with self._lock:
            if loaded:
                self._rows.clear()
                for row in loaded[-self.max_points:]:
                    self._rows.append(row)
            self._hydrated = True
        return len(loaded)

    def append(
        self,
        affect: dict[str, Any],
        *,
        predicted: Optional[dict[str, Any]] = None,
        error: Optional[dict[str, Any]] = None,
        surprise: Optional[float] = None,
        timestamp: Optional[float] = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        sample = _normalize_affect(affect)
        row = {
            "timestamp": float(timestamp if timestamp is not None else time.time()),
            **sample,
            "surprise": _clip01(0.0 if surprise is None else surprise),
            "predicted": dict(predicted or {}),
            "error": dict(error or {}),
            "source": "runtime",
        }
        with self._lock:
            self._rows.append(row)

        if persist:
            should_persist = False
            with self._lock:
                if (row["timestamp"] - self._last_persist_ts) >= 1.0:
                    should_persist = True
            if should_persist and self._persist_row(row):
                with self._lock:
                    self._last_persist_ts = float(row["timestamp"])
        return row

    def recent(self, limit: int = 120) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._rows)
        safe_limit = max(1, min(int(limit), self.max_points))
        return rows[-safe_limit:]

    def axis_history(self, limit: int = 120) -> list[dict[str, float]]:
        rows = self.recent(limit=limit)
        out: list[dict[str, float]] = []
        for row in rows:
            out.append(
                {
                    "timestamp": float(row.get("timestamp", 0.0) or 0.0),
                    "arousal": _clip01(row.get("arousal", 0.0)),
                    "valence": _clip11(row.get("valence", 0.0)),
                    "stress": _clip01(row.get("stress", 0.0)),
                    "coherence": _clip01(row.get("coherence", 1.0)),
                    "anxiety": _clip01(row.get("anxiety", 0.0)),
                }
            )
        return out

    def _persist_row(self, row: dict[str, Any]) -> bool:
        with self._lock:
            client = self._influx_client

        if client is None:
            return False

        try:
            ts_ns = int(float(row.get("timestamp", time.time()) or time.time()) * 1e9)
            fields = [
                f"arousal={float(row.get('arousal', 0.0) or 0.0)}",
                f"valence={float(row.get('valence', 0.0) or 0.0)}",
                f"stress={float(row.get('stress', 0.0) or 0.0)}",
                f"coherence={float(row.get('coherence', 0.0) or 0.0)}",
                f"anxiety={float(row.get('anxiety', 0.0) or 0.0)}",
                f"surprise={float(row.get('surprise', 0.0) or 0.0)}",
            ]
            line = (
                f"affective_state,ghost_id={_escape_lp_token(str(settings.GHOST_ID or 'omega-7'))} "
                f"{','.join(fields)} {ts_ns}"
            )
            write_api = self._write_api or client.write_api(write_options=SYNCHRONOUS)
            write_api.write(
                bucket=settings.INFLUXDB_BUCKET,
                org=settings.INFLUXDB_ORG,
                record=line,
            )
            return True
        except Exception as exc:
            logger.debug("Affective history persist skipped: %s", exc)
            return False


_history = AffectiveHistoryBuffer()


def get_affective_history() -> AffectiveHistoryBuffer:
    return _history


def set_influx_client(client: Optional[InfluxDBClient]) -> None:
    _history.set_influx_client(client)
