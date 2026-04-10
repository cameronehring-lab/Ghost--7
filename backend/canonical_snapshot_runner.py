"""
Automatic canonical snapshot ingestion runner.

Discovers canonical snapshot scripts and ingests pending ones into the world model.
Each script is executed with `--live` and tracked in Postgres so it only applies once.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import subprocess
import sys
from typing import Any

import asyncpg  # type: ignore

logger = logging.getLogger("omega.snapshot_runner")

SNAPSHOT_PATTERN = "canonical_snapshot_*.py"
SNAPSHOT_NAME_REGEX = re.compile(r"^canonical_snapshot_\d+\.py$")


async def _ensure_tracking_table(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_model_ingest_log (
                snapshot_name TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                details TEXT NOT NULL DEFAULT ''
            )
            """
        )


async def _already_applied(pool: asyncpg.Pool, snapshot_name: str) -> bool:
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM world_model_ingest_log WHERE snapshot_name = $1",
            snapshot_name,
        )
        return status == "applied"


async def _record_status(pool: asyncpg.Pool, snapshot_name: str, status: str, details: str) -> None:
    details_trimmed = (details or "")[:5000]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO world_model_ingest_log (snapshot_name, status, applied_at, details)
            VALUES ($1, $2, now(), $3)
            ON CONFLICT (snapshot_name)
            DO UPDATE SET status = EXCLUDED.status, applied_at = now(), details = EXCLUDED.details
            """,
            snapshot_name,
            status,
            details_trimmed,
        )


def _discover_snapshot_scripts(base_dir: str = ".") -> list[str]:
    pattern = os.path.join(base_dir, SNAPSHOT_PATTERN)
    scripts = sorted(glob.glob(pattern))
    filtered: list[str] = []
    for script in scripts:
        if not os.path.isfile(script):
            continue
        name = os.path.basename(script)
        if not SNAPSHOT_NAME_REGEX.match(name):
            continue
        filtered.append(script)
    return filtered


def _run_snapshot_script(script_path: str) -> tuple[int, str]:
    """Run a snapshot script in live mode and return (returncode, combined_output)."""
    proc = subprocess.run(  # nosec B603
        [sys.executable, script_path, "--live"],
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


async def run_pending_snapshots(pool: asyncpg.Pool, base_dir: str = ".") -> dict[str, Any]:
    """
    Discover and ingest any pending canonical snapshots.
    Returns counts and names for observability.
    """
    await _ensure_tracking_table(pool)

    scripts = _discover_snapshot_scripts(base_dir=base_dir)
    applied_now: list[str] = []
    skipped_applied: list[str] = []
    failed_now: list[str] = []

    for script in scripts:
        name = os.path.basename(script)
        if await _already_applied(pool, name):
            skipped_applied.append(name)
            continue

        logger.info("Snapshot runner: ingesting %s", name)
        rc, out = await asyncio.to_thread(_run_snapshot_script, script)
        if rc == 0:
            await _record_status(pool, name, "applied", out)
            applied_now.append(name)
            logger.info("Snapshot runner: applied %s", name)
        else:
            await _record_status(pool, name, "failed", out)
            failed_now.append(name)
            logger.error("Snapshot runner: failed %s (rc=%d)", name, rc)

    return {
        "discovered": len(scripts),
        "applied": len(applied_now),
        "failed": len(failed_now),
        "already_applied": len(skipped_applied),
        "applied_names": applied_now,
        "failed_names": failed_now,
    }


async def auto_ingest_loop(
    pool: asyncpg.Pool,
    base_dir: str = ".",
    interval_seconds: float = 300.0,
) -> None:
    """
    Periodically ingest pending snapshots so users don't have to remember.
    """
    logger.info(
        "Snapshot runner started (pattern=%s, interval=%ss)",
        SNAPSHOT_PATTERN,
        interval_seconds,
    )
    # Initial pass shortly after startup
    await asyncio.sleep(5)

    while True:
        try:
            summary = await run_pending_snapshots(pool, base_dir=base_dir)
            if summary["applied"] or summary["failed"]:
                logger.info("Snapshot runner summary: %s", summary)
        except Exception as e:
            logger.error("Snapshot runner loop error: %s", e)

        await asyncio.sleep(max(30.0, interval_seconds))
