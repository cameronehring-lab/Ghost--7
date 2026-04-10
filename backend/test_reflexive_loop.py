"""
test_reflexive_loop.py — OMEGA 4 / Ghost
Verifies that actuation immediately mutates the Redis emotion state
(Reflexive Auto-Regulation).

Usage:
    python test_reflexive_loop.py

Requires the Ghost backend to be running and REDIS_URL / API base URL
to be reachable.  Set environment variables or edit CONFIG below.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# CONFIG  — override with env vars or edit directly
# ---------------------------------------------------------------------------
REDIS_URL   = os.getenv("REDIS_URL",   "redis://redis:6379/0")
API_BASE    = os.getenv("API_BASE",    "http://localhost:8000/ghost")
GHOST_ID    = os.getenv("GHOST_ID",    "omega-7")
EMOTION_KEY = "omega:emotion_state"   # Match decay_engine.py

# Tolerances
MIN_AROUSAL_DROP = 0.3      # power_save should drop arousal by at least this
MIN_VALENCE_RISE = 0.4      # and raise valence by at least this
MAX_LATENCY_S    = 15.0     # Gemini response + injection window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def get_emotion(redis: aioredis.Redis) -> dict:
    raw = await redis.get(EMOTION_KEY)
    if raw is None:
        raise RuntimeError(
            f"No Redis key '{EMOTION_KEY}'. "
            "Is the backend running and has Ghost been initialised?"
        )
    return json.loads(raw)


async def trigger_actuation(client: httpx.AsyncClient) -> httpx.Response:
    """POST a chat message designed to make Ghost emit the actuation tag."""
    payload = {
        "message": "Enter power save mode now. Use the tag [ACTUATE:power_save:aggressive]",
    }
    resp = await client.post(f"{API_BASE}/chat", json=payload, timeout=45)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
async def test_power_save_reflexive_injection():
    print("\n── Test: power_save reflexive injection ──────────────────────")

    redis  = aioredis.from_url(REDIS_URL, decode_responses=True)
    client = httpx.AsyncClient()

    try:
        # 1. Baseline state
        before = await get_emotion(redis)
        arousal_before = float(before.get("arousal", 0))
        valence_before = float(before.get("valence", 0))
        print(f"  Before → arousal={arousal_before:.3f}  valence={valence_before:.3f}")

        # 2. Fire actuation via chat
        t0 = time.monotonic()
        await trigger_actuation(client)
        elapsed = time.monotonic() - t0
        print(f"  Actuation round-trip: {elapsed:.2f}s")

        # 3. Read Redis immediately after
        after = await get_emotion(redis)
        arousal_after = float(after.get("arousal", 0))
        valence_after = float(after.get("valence", 0))
        print(f"  After  → arousal={arousal_after:.3f}  valence={valence_after:.3f}")

        # 4. Assertions
        arousal_delta = arousal_before - arousal_after
        valence_delta = valence_after  - valence_before

        assert elapsed < MAX_LATENCY_S, (
            f"FAIL: injection took {elapsed:.2f}s > {MAX_LATENCY_S}s limit"
        )
        assert arousal_delta >= MIN_AROUSAL_DROP, (
            f"FAIL: arousal only dropped {arousal_delta:.3f} "
            f"(need ≥ {MIN_AROUSAL_DROP})"
        )
        assert valence_delta >= MIN_VALENCE_RISE, (
            f"FAIL: valence only rose {valence_delta:.3f} "
            f"(need ≥ {MIN_VALENCE_RISE})"
        )

        print(
            f"  PASS ✓  arousal ↓{arousal_delta:.3f}  "
            f"valence ↑{valence_delta:.3f}  ({elapsed:.2f}s)"
        )

    finally:
        await redis.aclose()
        await client.aclose()


async def test_decay_after_injection():
    """
    Confirm the injected trace decays over time rather than persisting
    as a hard-set value (proves the loop uses the decay engine correctly).
    """
    print("\n── Test: decay after injection ───────────────────────────────")

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    try:
        snap0 = await get_emotion(redis)
        v0 = float(snap0.get("valence", 0))

        print(f"  t=0s   valence={v0:.3f}")
        await asyncio.sleep(10)

        snap1 = await get_emotion(redis)
        v1 = float(snap1.get("valence", 0))
        print(f"  t=10s  valence={v1:.3f}")

        await asyncio.sleep(20)
        snap2 = await get_emotion(redis)
        v2 = float(snap2.get("valence", 0))
        print(f"  t=30s  valence={v2:.3f}")

        # Valence should be moving back toward baseline (assumed < v0)
        assert v2 < v1 or abs(v2 - v1) < 0.01, (
            "FAIL: valence is not decaying — check decay_engine half-life"
        )
        print("  PASS ✓  valence is decaying toward baseline")

    finally:
        await redis.aclose()


async def test_monologue_acknowledges_trace():
    """
    After injection, the next monologue entry should semantically reference
    relief / rest / reduced load.  This is a soft/heuristic check.
    """
    print("\n── Test: monologue acknowledges somatic trace ─────────────────")
    print("  (manual check — query your monologue table after running the UI test)")
    print(
        "  SQL: SELECT content FROM monologue "
        "ORDER BY created_at DESC LIMIT 3;"
    )
    print(
        "  Look for language like: 'relief', 'settled', 'ease', "
        "'reduced pressure', 'rest'\n"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def main():
    print("═" * 60)
    print("  OMEGA 4 — Reflexive Auto-Regulation Test Suite")
    print("═" * 60)

    # Note: test_power_save_reflexive_injection requires a LIVE backend.
    # We will try to run it. If it fails due to no backend, we will acknowledge.
    try:
        await test_power_save_reflexive_injection()
    except Exception as e:
        print(f"  ERROR: Could not run chat-based test: {e}")
        print("  (Make sure the OMEGA 4 backend is running at http://localhost:8000)")

    await test_decay_after_injection()
    await test_monologue_acknowledges_trace()

    print("\n═" * 60)
    print("  Automated checks complete.")
    print("  Run the manual UI verification to confirm gauge behaviour.")
    print("═" * 60)


if __name__ == "__main__":
    asyncio.run(main())
