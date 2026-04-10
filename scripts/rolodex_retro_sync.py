#!/usr/bin/env python3
"""
Retroactive Rolodex entity audit/backfill runner.

Usage:
  docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py
  python scripts/rolodex_retro_sync.py
  python scripts/rolodex_retro_sync.py --apply
  python scripts/rolodex_retro_sync.py --apply --max-messages 800
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_IMPORT_ROOT: Path | None = None
for candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (candidate / "memory.py").exists():
        BACKEND_IMPORT_ROOT = candidate
        break
if BACKEND_IMPORT_ROOT is None:
    raise RuntimeError(f"Could not locate backend module root from {REPO_ROOT}")
if str(BACKEND_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_IMPORT_ROOT))

try:
    import memory  # type: ignore
    import person_rolodex  # type: ignore
    from config import settings  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    missing = str(exc)
    raise SystemExit(
        "Missing backend runtime dependency ("
        + missing
        + "). Run this script inside the backend container:\n"
        + "  docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py"
    )


def _compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    current = report.get("current") or {}
    missing = report.get("missing") or {}
    projection = report.get("topology_projection") or {}
    scan = report.get("scan") or {}
    return {
        "scan": {
            "message_rows_scanned": scan.get("message_rows_scanned"),
            "vector_rows_scanned": scan.get("vector_rows_scanned"),
        },
        "current": {
            "profiles": current.get("profiles"),
            "facts": current.get("facts"),
            "places": current.get("places"),
            "things": current.get("things"),
        },
        "missing": {
            "profiles_count": missing.get("profiles_count"),
            "facts_count": missing.get("facts_count"),
            "places_count": missing.get("places_count"),
            "things_count": missing.get("things_count"),
        },
        "projection": projection,
    }


async def _run(args: argparse.Namespace) -> int:
    await memory.init_db()
    try:
        pool = memory._pool
        if pool is None:
            raise RuntimeError("Database pool unavailable after init")

        if args.apply:
            result = await person_rolodex.apply_retro_sync(
                pool,
                ghost_id=settings.GHOST_ID,
                max_messages=args.max_messages,
            )
            print(json.dumps(result, indent=2))
            return 0

        report = await person_rolodex.audit_retro_entities(
            pool,
            ghost_id=settings.GHOST_ID,
            max_messages=args.max_messages,
            max_memory_rows=args.max_memory_rows,
        )
        if args.full_json:
            print(json.dumps(report, indent=2))
        else:
            print(json.dumps(_compact_summary(report), indent=2))
        return 0
    finally:
        await memory.close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/backfill missing Rolodex entities from historical memory.")
    parser.add_argument("--apply", action="store_true", help="Apply backfill inserts for missing entities.")
    parser.add_argument("--max-messages", type=int, default=0, help="Optional cap on user messages scanned (0=all).")
    parser.add_argument(
        "--max-memory-rows",
        type=int,
        default=1500,
        help="Optional cap on vector memories scanned for memory-only candidates.",
    )
    parser.add_argument("--full-json", action="store_true", help="Print full audit payload (not compact summary).")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
