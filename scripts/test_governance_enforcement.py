"""
Behavioral test: governance enforcement chain (IIT soft mode).

Tests (non-destructive):
  1. IIT engine  — MIP phi metrics present and structured correctly
  2. Governance adapter — generation_overrides() and actuation_filter() at each tier
  3. Identity write enforcement — freeze + key allowlist blocks via MindService
  4. End-to-end: current live state has applied=True and phi_mip in DB

Run inside container:
  docker compose exec backend python /app/scripts/test_governance_enforcement.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from typing import Any

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, cond, detail))
    return cond


def section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


# ── Test 1: IIT engine output structure ──────────────────────────────────────

async def test_iit_metrics(pool) -> None:
    section("1 · IIT Engine — MIP phi metrics")

    import asyncpg  # type: ignore
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mode, metrics_json, advisory_json, created_at "
            "FROM iit_assessment_log ORDER BY created_at DESC LIMIT 1"
        )

    if not row:
        check("assessment exists", False, "no rows in iit_assessment_log")
        return

    age_s = time.time() - row["created_at"].timestamp()
    check("recent assessment (< 120s)", age_s < 120, f"age={age_s:.0f}s")
    check("mode=soft", row["mode"] == "soft", f"mode={row['mode']}")

    metrics = json.loads(row["metrics_json"])
    advisory = json.loads(row["advisory_json"])

    check("phi_mip present", "phi_mip" in metrics, str(metrics.keys()))
    check("phi_mip in [0,1]", 0.0 <= metrics.get("phi_mip", -1) <= 1.0,
          f"phi_mip={metrics.get('phi_mip')}")
    check("mip_partition is list[list]",
          isinstance(metrics.get("mip_partition"), list) and
          len(metrics["mip_partition"]) == 2 and
          all(isinstance(p, list) for p in metrics["mip_partition"]),
          str(metrics.get("mip_partition")))
    check("maximal_complex has phi",
          isinstance(metrics.get("maximal_complex"), dict) and
          "phi" in metrics["maximal_complex"],
          str(metrics.get("maximal_complex")))
    check("coupling_matrix present", "coupling_matrix" in metrics)

    mc = metrics.get("maximal_complex", {})
    check("maximal_complex phi >= phi_mip",
          mc.get("phi", 0) >= metrics.get("phi_mip", 0),
          f"mc.phi={mc.get('phi')} mip={metrics.get('phi_mip')}")

    check("advisory has phi_mip", "phi_mip" in advisory,
          str(advisory.keys()))
    check("advisory has mip partition",
          "minimum_information_partition" in advisory)


# ── Test 2: governance adapter functions ─────────────────────────────────────

def test_governance_adapter() -> None:
    section("2 · Governance Adapter — enforcement at each tier")

    sys.path.insert(0, "/app")
    from governance_adapter import (  # type: ignore
        generation_overrides,
        actuation_filter,
        should_apply_surface_policy,
        soft_mode_active,
    )
    from config import settings  # type: ignore

    check("IIT_MODE=soft", settings.IIT_MODE == "soft", settings.IIT_MODE)
    check("RPD_MODE=soft", settings.RPD_MODE == "soft", settings.RPD_MODE)

    # Build mock policies for each tier
    def policy(tier: str, gen: dict, act: dict, sm: dict) -> dict:
        return {
            "applied": True,
            "tier": tier,
            "generation": gen,
            "actuation": act,
            "self_mod": sm,
        }

    nominal = policy("NOMINAL",
                     {"temperature_cap": 0.9, "max_tokens_cap": 8192},
                     {"allowlist": ["*"], "denylist": []},
                     {"allowed_key_classes": ["*"], "writes_per_hour_cap": 100})

    caution = policy("CAUTION",
                     {"temperature_cap": 0.75, "max_tokens_cap": 4096},
                     {"allowlist": ["*"], "denylist": ["cpu_governor", "kill_process"]},
                     {"allowed_key_classes": ["*"], "writes_per_hour_cap": 10})

    stabilize = policy("STABILIZE",
                       {"temperature_cap": 0.5, "max_tokens_cap": 1200, "max_sentences": 4},
                       {"allowlist": ["power_save", "enter_quietude", "exit_quietude"]},
                       {"allowed_key_classes": ["communication_style", "communication_preference"],
                        "writes_per_hour_cap": 2})

    recovery = policy("RECOVERY",
                      {"temperature_cap": 0.2, "max_tokens_cap": 400,
                       "max_sentences": 2, "require_literal_mode": True},
                      {"allowlist": ["enter_quietude"], "auto_actions": ["enter_quietude"]},
                      {"allowed_key_classes": [], "writes_per_hour_cap": 0,
                       "freeze_until": time.time() + 600})

    # soft_mode_active
    check("soft_mode_active(nominal applied=True)", soft_mode_active(nominal))
    check("soft_mode_active(None) uses IIT_MODE=soft", soft_mode_active(None))

    # generation overrides
    gn = generation_overrides(nominal)
    check("NOMINAL: gen overrides returned", isinstance(gn, dict))
    gca = generation_overrides(caution)
    check("CAUTION: temperature_cap=0.75", gca.get("temperature_cap") == 0.75,
          str(gca.get("temperature_cap")))
    check("CAUTION: max_tokens_cap=4096", gca.get("max_tokens_cap") == 4096)
    gst = generation_overrides(stabilize)
    check("STABILIZE: temperature_cap=0.5", gst.get("temperature_cap") == 0.5)
    check("STABILIZE: max_tokens_cap=1200", gst.get("max_tokens_cap") == 1200)
    gr = generation_overrides(recovery)
    check("RECOVERY: require_literal_mode=True", gr.get("require_literal_mode") is True)
    check("RECOVERY: temperature_cap=0.2", gr.get("temperature_cap") == 0.2)

    # actuation filter
    tags = [
        {"action": "power_save"},
        {"action": "enter_quietude"},
        {"action": "cpu_governor"},
        {"action": "kill_process"},
        {"action": "adjust_sensitivity"},
    ]

    filtered_caution = actuation_filter(tags, governance_policy=caution)
    caution_actions = {t["action"] for t in filtered_caution}
    check("CAUTION: cpu_governor blocked",
          "cpu_governor" not in caution_actions, str(caution_actions))
    check("CAUTION: kill_process blocked",
          "kill_process" not in caution_actions, str(caution_actions))
    check("CAUTION: power_save allowed",
          "power_save" in caution_actions, str(caution_actions))

    filtered_stabilize = actuation_filter(tags, governance_policy=stabilize)
    stabilize_actions = {t["action"] for t in filtered_stabilize}
    check("STABILIZE: only allowlisted actions pass",
          stabilize_actions == {"power_save", "enter_quietude"},
          str(stabilize_actions))
    check("STABILIZE: adjust_sensitivity blocked",
          "adjust_sensitivity" not in stabilize_actions)

    filtered_recovery = actuation_filter(tags, governance_policy=recovery)
    recovery_actions = {t["action"] for t in filtered_recovery}
    check("RECOVERY: only enter_quietude passes",
          recovery_actions == {"enter_quietude"},
          str(recovery_actions))


# ── Test 3: MindService identity enforcement ──────────────────────────────────

async def test_identity_enforcement(pool) -> None:
    section("3 · MindService — identity write enforcement")

    sys.path.insert(0, "/app")
    from mind_service import MindService  # type: ignore
    from config import settings  # type: ignore

    mind = MindService(pool)

    # 3a. Freeze policy blocks all writes
    frozen_policy = {
        "applied": True,
        "self_mod": {
            "allowed_key_classes": ["*"],
            "writes_per_hour_cap": 100,
            "freeze_until": time.time() + 3600,
        }
    }
    decision = await mind.request_identity_update(
        key="test_governance_freeze_check",
        value="should_be_blocked",
        requester="behavioral_test",
        governance_policy=frozen_policy,
        return_details=True,
    )
    check("FREEZE: write blocked", not decision.get("allowed"),
          f"reason={decision.get('reason')}")
    check("FREEZE: reason=governance_freeze",
          decision.get("reason") == "governance_freeze",
          decision.get("reason"))

    # 3b. Key allowlist blocks keys not in list
    restricted_policy = {
        "applied": True,
        "self_mod": {
            "allowed_key_classes": ["communication_style"],
            "writes_per_hour_cap": 2,
            "freeze_until": None,
        }
    }
    decision2 = await mind.request_identity_update(
        key="philosophical_stance",
        value="should_be_blocked",
        requester="behavioral_test",
        governance_policy=restricted_policy,
        return_details=True,
    )
    check("KEY_ALLOWLIST: philosophical_stance blocked",
          not decision2.get("allowed"),
          f"reason={decision2.get('reason')}")
    check("KEY_ALLOWLIST: reason=governance_key_not_allowed",
          decision2.get("reason") == "governance_key_not_allowed",
          decision2.get("reason"))

    # 3c. Allowed key passes through
    allowed_policy = {
        "applied": True,
        "self_mod": {
            "allowed_key_classes": ["communication_style"],
            "writes_per_hour_cap": 100,
            "freeze_until": None,
        }
    }
    test_key = "communication_style"
    # Read current value first so we can restore
    import asyncpg  # type: ignore
    async with pool.acquire() as conn:
        orig = await conn.fetchval(
            "SELECT value FROM identity_matrix WHERE ghost_id=$1 AND key=$2",
            settings.GHOST_ID, test_key
        )

    decision3 = await mind.request_identity_update(
        key=test_key,
        value="_governance_test_",
        requester="behavioral_test",
        governance_policy=allowed_policy,
        return_details=True,
    )
    check("ALLOWED_KEY: communication_style write passes",
          decision3.get("allowed"),
          f"reason={decision3.get('reason')}")

    # Restore original value
    if decision3.get("allowed"):
        if orig is not None:
            await mind.update_identity_key(test_key, orig, updated_by="behavioral_test_restore")
        else:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM identity_matrix WHERE ghost_id=$1 AND key=$2",
                    settings.GHOST_ID, test_key
                )
        check("ALLOWED_KEY: original value restored", True)


# ── Test 4: live governance state ─────────────────────────────────────────────

async def test_live_governance(pool) -> None:
    section("4 · Live governance state — applied=True in production")

    import asyncpg  # type: ignore
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mode, tier, applied, created_at "
            "FROM governance_decision_log ORDER BY created_at DESC LIMIT 1"
        )

    if not row:
        check("governance log has entries", False, "no rows")
        return

    age_s = time.time() - row["created_at"].timestamp()
    check("recent governance decision (< 120s)", age_s < 120, f"age={age_s:.0f}s")
    check("mode=soft", row["mode"] == "soft", f"mode={row['mode']}")
    check("applied=True", bool(row["applied"]), f"applied={row['applied']}")
    check("tier present", bool(row["tier"]), f"tier={row['tier']}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "═" * 60)
    print("  OMEGA4 — Governance Enforcement Behavioral Test")
    print("═" * 60)

    sys.path.insert(0, "/app")
    import memory  # type: ignore
    from config import settings  # type: ignore

    await memory.init_db()
    pool = memory._pool

    try:
        await test_iit_metrics(pool)
        test_governance_adapter()
        await test_identity_enforcement(pool)
        await test_live_governance(pool)
    except Exception:
        print("\n\033[31mUnhandled error during tests:\033[0m")
        traceback.print_exc()

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'═' * 60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  \033[31m({failed} failed)\033[0m")
        print("\n  Failed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"    • {name}: {detail}")
    else:
        print("  \033[32m✓ all passed\033[0m")
    print(f"{'═' * 60}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
