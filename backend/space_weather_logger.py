"""
space_weather_logger.py — Chronological recorder for Schumann (VLF) and solar weather.

Logs a snapshot every LOG_INTERVAL seconds (default 300 = 5 min) into Postgres.
Table is created on first run (CREATE TABLE IF NOT EXISTS).

Columns:
  recorded_at          — UTC timestamp of the reading
  vlf_shm_ok           — whether sos70.ru shm.jpg was reachable
  vlf_srf_ok           — whether sos70.ru srf.jpg was reachable
  solar_flare_class    — e.g. "C2.5", "M1.3"
  solar_flare_letter   — "A","B","C","M","X"
  solar_flare_intensity— 0–1 normalized
  solar_flare_begin    — ISO timestamp of flare start
  solar_flare_max      — ISO timestamp of flare peak
  solar_kp_index       — planetary geomagnetic index (0–9)
  solar_kp_label       — "quiet", "unsettled", "active", …
"""

import asyncio
import csv
import io
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx  # type: ignore

logger = logging.getLogger("omega.space_weather_logger")

LOG_INTERVAL = 300  # seconds between recordings
_VLF_PROBE_URL = "https://sos70.ru/provider.php?file={}"
_NOAA_FLARE_URL = "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json"
_NOAA_KP_URL    = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
_last_schumann_pull = 0.0

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS space_weather_log (
    id               SERIAL PRIMARY KEY,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    vlf_shm_ok       BOOLEAN,
    vlf_srf_ok       BOOLEAN,
    solar_flare_class  TEXT,
    solar_flare_letter CHAR(1),
    solar_flare_intensity DOUBLE PRECISION,
    solar_flare_begin  TIMESTAMPTZ,
    solar_flare_max    TIMESTAMPTZ,
    solar_kp_index     DOUBLE PRECISION,
    solar_kp_label     TEXT
);
CREATE INDEX IF NOT EXISTS space_weather_log_recorded_at_idx
    ON space_weather_log (recorded_at DESC);
"""

_INSERT_SQL = """
INSERT INTO space_weather_log (
    recorded_at, vlf_shm_ok, vlf_srf_ok,
    solar_flare_class, solar_flare_letter, solar_flare_intensity,
    solar_flare_begin, solar_flare_max,
    solar_kp_index, solar_kp_label
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
"""


async def _ensure_table(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)


async def _probe_vlf(client: httpx.AsyncClient) -> Dict[str, bool]:
    results = {}
    for key in ("shm.jpg", "srf.jpg"):
        try:
            r = await client.get(_VLF_PROBE_URL.format(key), timeout=8.0)
            ct = r.headers.get("content-type", "")
            results[key] = r.status_code == 200 and "html" not in ct
        except Exception:
            results[key] = False
    return results


async def _fetch_solar() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(_NOAA_FLARE_URL)
            if r.status_code == 200:
                flares = r.json()
                if flares:
                    f = flares[-1]
                    cls = f.get("current_class") or f.get("max_class") or ""
                    letter = cls[0].upper() if cls and cls[0].upper() in "ABCMX" else "A"
                    # Normalise intensity
                    base = {"A": 0.05, "B": 0.15, "C": 0.35, "M": 0.65, "X": 0.90}.get(letter, 0.05)
                    try:
                        suffix = float(cls[1:]) if len(cls) > 1 else 1.0
                        intensity = min(1.0, base + (suffix / 10.0) * 0.08)
                    except ValueError:
                        intensity = base
                    out["solar_flare_class"] = cls
                    out["solar_flare_letter"] = letter
                    out["solar_flare_intensity"] = round(intensity, 4)
                    raw_begin = f.get("begin_time")
                    raw_max   = f.get("max_time")
                    out["solar_flare_begin"] = _parse_ts(raw_begin)
                    out["solar_flare_max"]   = _parse_ts(raw_max)
        except Exception as e:
            logger.debug("Flare fetch failed: %s", e)

        try:
            r = await client.get(_NOAA_KP_URL)
            if r.status_code == 200:
                kp_data = r.json()
                if kp_data:
                    latest = kp_data[-1]
                    kp = latest.get("estimated_kp") or latest.get("kp_index")
                    if kp is not None:
                        kp_f = float(kp)
                        labels = ["quiet","quiet","quiet","unsettled","active",
                                  "minor storm","moderate storm","strong storm","severe storm","extreme storm"]
                        out["solar_kp_index"] = round(kp_f, 1)
                        out["solar_kp_label"] = labels[min(9, max(0, int(round(kp_f))))]
        except Exception as e:
            logger.debug("Kp fetch failed: %s", e)

    return out


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # NOAA uses "2026-03-27T19:13:00Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def _record_snapshot(pool) -> None:
    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient(timeout=8.0) as client:
        vlf = await _probe_vlf(client)

    solar = await _fetch_solar()

    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_SQL,
            now,
            vlf.get("shm.jpg", False),
            vlf.get("srf.jpg", False),
            solar.get("solar_flare_class"),
            solar.get("solar_flare_letter"),
            solar.get("solar_flare_intensity"),
            solar.get("solar_flare_begin"),
            solar.get("solar_flare_max"),
            solar.get("solar_kp_index"),
            solar.get("solar_kp_label"),
        )

    logger.info(
        "Space weather snapshot: flare=%s Kp=%s vlf_shm=%s vlf_srf=%s",
        solar.get("solar_flare_class", "–"),
        solar.get("solar_kp_index", "–"),
        vlf.get("shm.jpg"),
        vlf.get("srf.jpg"),
    )

    # Trigger structural OCR extraction of Schumann data every ~4 hours
    global _last_schumann_pull
    if time.time() - _last_schumann_pull > 3600 * 4:
        try:
            from schumann_extractor import update_schumann_history
            import subprocess
            from pathlib import Path

            await asyncio.to_thread(update_schumann_history)
            _last_schumann_pull = time.time()
            
            # Automatically push physical data into the regression validation matrix
            backend_dir = Path(__file__).resolve().parent
            script_path = backend_dir / "diagnostic_scripts" / "schumann_solar_validation.py"
            env_python = backend_dir.parent / ".venv" / "bin" / "python3"
            
            # Fallback to system python if venv isn't strict 
            py_bin = str(env_python) if env_python.exists() else "python3"
            
            proc = await asyncio.create_subprocess_exec(
                py_bin, str(script_path), "--fetch",
                cwd=str(backend_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("Successfully cascaded empirical metrics into active regression pipeline.")
            else:
                logger.error(f"Failed to cascade regression matrix: {stderr.decode()}")

        except Exception as e:
            logger.error("Failed to run optical schumann extraction and regression: %s", e)


async def space_weather_log_loop(pool, interval: int = LOG_INTERVAL) -> None:
    """Background task — record a snapshot every `interval` seconds."""
    await _ensure_table(pool)
    logger.info("Space weather logger starting (interval=%ds)", interval)

    # First snapshot immediately
    try:
        await _record_snapshot(pool)
    except Exception as e:
        logger.error("Initial space weather snapshot failed: %s", e)

    while True:
        await asyncio.sleep(interval)
        try:
            await _record_snapshot(pool)
        except Exception as e:
            logger.error("Space weather snapshot failed: %s", e)


# ── Query helpers (used by API endpoints) ──────────────────────────────────────

async def get_log(pool, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
    """Return recent log entries as a list of dicts, newest first."""
    rows = await pool.fetch(
        """
        SELECT id, recorded_at, vlf_shm_ok, vlf_srf_ok,
               solar_flare_class, solar_flare_letter, solar_flare_intensity,
               solar_flare_begin, solar_flare_max,
               solar_kp_index, solar_kp_label
        FROM space_weather_log
        ORDER BY recorded_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    return [_row_to_dict(r) for r in rows]


async def get_log_count(pool) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM space_weather_log")


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "recorded_at": row["recorded_at"].isoformat() if row["recorded_at"] else None,
        "vlf_shm_ok": row["vlf_shm_ok"],
        "vlf_srf_ok": row["vlf_srf_ok"],
        "solar_flare_class": row["solar_flare_class"],
        "solar_flare_letter": row["solar_flare_letter"],
        "solar_flare_intensity": row["solar_flare_intensity"],
        "solar_flare_begin": row["solar_flare_begin"].isoformat() if row["solar_flare_begin"] else None,
        "solar_flare_max": row["solar_flare_max"].isoformat() if row["solar_flare_max"] else None,
        "solar_kp_index": row["solar_kp_index"],
        "solar_kp_label": row["solar_kp_label"],
    }


def rows_to_csv(rows: List[Dict[str, Any]]) -> str:
    """Serialise log rows to CSV string."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
