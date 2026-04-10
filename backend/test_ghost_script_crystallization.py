import asyncio
import contextlib
import unittest
from unittest.mock import AsyncMock, patch

import ghost_script
import main


class _FixedWorkspace:
    def __init__(self, psi_norm: float, psi_linguistic_magnitude: float):
        self._psi_norm = float(psi_norm)
        self._psi_linguistic_magnitude = float(psi_linguistic_magnitude)

    def decay(self, dt: float) -> None:
        return None

    def apply_interactions(self):
        return {"psi_norm": self._psi_norm}

    def magnitude(self) -> float:
        return self._psi_norm

    def linguistic_magnitude(self) -> float:
        return self._psi_linguistic_magnitude


class PsiCrystallizationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_threshold_path_sets_wake_and_disarms(self):
        old_workspace = main.sys_state.global_workspace
        old_wake_event = main.sys_state.ghost_wake_event
        old_armed = main.sys_state.psi_crystallization_armed
        old_last_wake_ts = main.sys_state.psi_last_wake_ts
        old_last_metric_ts = main.sys_state.psi_last_metric_ts
        task = None

        try:
            main.sys_state.global_workspace = _FixedWorkspace(psi_norm=0.8, psi_linguistic_magnitude=0.92)
            main.sys_state.ghost_wake_event = asyncio.Event()
            main.sys_state.psi_crystallization_armed = True
            main.sys_state.psi_last_wake_ts = 0.0
            main.sys_state.psi_last_metric_ts = 0.0

            with patch.object(main.settings, "PSI_CRYSTALLIZATION_ENABLED", True), patch.object(
                main.settings, "PSI_CRYSTALLIZATION_THRESHOLD", 0.72
            ), patch.object(
                main.settings, "PSI_CRYSTALLIZATION_RESET_THRESHOLD", 0.54
            ), patch.object(
                main.settings, "PSI_CRYSTALLIZATION_WAKE_COOLDOWN_SECONDS", 30.0
            ), patch.object(
                main.settings, "PSI_DYNAMICS_METRIC_INTERVAL_SECONDS", 10.0
            ), patch.object(
                main, "write_internal_metric", new=AsyncMock(return_value=True)
            ):
                task = asyncio.create_task(main.psi_dynamics_loop(interval=0.01))
                await asyncio.wait_for(main.sys_state.ghost_wake_event.wait(), timeout=0.4)
                self.assertTrue(main.sys_state.ghost_wake_event.is_set())
                self.assertFalse(main.sys_state.psi_crystallization_armed)
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            main.sys_state.global_workspace = old_workspace
            main.sys_state.ghost_wake_event = old_wake_event
            main.sys_state.psi_crystallization_armed = old_armed
            main.sys_state.psi_last_wake_ts = old_last_wake_ts
            main.sys_state.psi_last_metric_ts = old_last_metric_ts

    def test_hysteresis_requires_drop_below_reset_before_refire(self):
        first = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=False,
            psi_linguistic_magnitude=0.90,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=100.0,
            last_wake_ts=0.0,
            cooldown_seconds=30.0,
        )
        self.assertFalse(first["wake_emitted"])
        self.assertFalse(first["armed"])

        reset = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=bool(first["armed"]),
            psi_linguistic_magnitude=0.50,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=120.0,
            last_wake_ts=0.0,
            cooldown_seconds=30.0,
        )
        self.assertTrue(reset["armed"])
        self.assertFalse(reset["wake_emitted"])

        second = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=bool(reset["armed"]),
            psi_linguistic_magnitude=0.88,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=200.0,
            last_wake_ts=0.0,
            cooldown_seconds=30.0,
        )
        self.assertTrue(second["wake_emitted"])
        self.assertFalse(second["armed"])

    def test_cooldown_blocks_second_crossing_within_window(self):
        first = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=True,
            psi_linguistic_magnitude=0.85,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=100.0,
            last_wake_ts=0.0,
            cooldown_seconds=30.0,
        )
        self.assertTrue(first["wake_emitted"])
        self.assertFalse(first["armed"])

        rearm = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=bool(first["armed"]),
            psi_linguistic_magnitude=0.50,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=105.0,
            last_wake_ts=float(first["last_wake_ts"]),
            cooldown_seconds=30.0,
        )
        self.assertTrue(rearm["armed"])
        self.assertFalse(rearm["wake_emitted"])

        blocked = main._evaluate_psi_crystallization_gate(
            enabled=True,
            armed=bool(rearm["armed"]),
            psi_linguistic_magnitude=0.90,
            threshold=0.72,
            reset_threshold=0.54,
            now_ts=110.0,
            last_wake_ts=float(first["last_wake_ts"]),
            cooldown_seconds=30.0,
        )
        self.assertFalse(blocked["wake_emitted"])
        self.assertFalse(blocked["armed"])

    def test_timer_fallback_returns_timer_when_below_threshold(self):
        with patch.object(ghost_script.settings, "PSI_CRYSTALLIZATION_ENABLED", True), patch.object(
            ghost_script.settings, "PSI_CRYSTALLIZATION_THRESHOLD", 0.72
        ):
            reason = ghost_script._resolve_trigger_reason(
                wake_triggered=False,
                psi_snapshot={"psi_linguistic_magnitude": 0.30, "psi_norm": 0.25},
                last_monologue_ts=100.0,
                now_ts=460.0,
                interval_seconds=300.0,
            )
        self.assertEqual(reason, "timer")


if __name__ == "__main__":
    unittest.main()
