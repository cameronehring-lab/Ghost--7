import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.docker_recovery_watchdog as watchdog


def _healthy_probe() -> dict[str, object]:
    return {
        "healthy": True,
        "health_code": 200,
        "somatic_code": 200,
        "push_ok": True,
        "push_detail": "event:ping",
    }


def _unhealthy_probe() -> dict[str, object]:
    return {
        "healthy": False,
        "health_code": 200,
        "somatic_code": 200,
        "push_ok": False,
        "push_detail": "timeout_waiting_for_event",
    }


class _FakeStreamingResponse:
    def __init__(self, lines: list[bytes], status: int = 200):
        self._lines = list(lines)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""


class CycleStateMachineTests(unittest.TestCase):
    def test_no_restart_on_first_or_second_failure(self):
        restart_mock = mock.Mock(return_value=(True, "ok"))
        state = watchdog._default_state()
        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=100.0, restart_fn=restart_mock)
        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=120.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], 2)
        self.assertEqual(state["last_cycle_note"], "unhealthy")
        restart_mock.assert_not_called()

    def test_third_failure_restarts_backend_and_enters_grace(self):
        restart_mock = mock.Mock(return_value=(True, "backend restarted"))
        state = watchdog._default_state()
        state["consecutive_failures"] = 2

        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=300.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], 0)
        self.assertTrue(state["escalate_to_full_stack"])
        self.assertEqual(state["last_cycle_note"], "restart_backend")
        self.assertEqual(state["grace_until"], 360.0)
        restart_mock.assert_called_once_with("backend")

    def test_grace_window_suppresses_new_failures(self):
        restart_mock = mock.Mock(return_value=(True, "unused"))
        state = watchdog._default_state()
        state["grace_until"] = 260.0
        state["escalate_to_full_stack"] = True

        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=220.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], 0)
        self.assertEqual(state["last_cycle_note"], "grace_window")
        restart_mock.assert_not_called()

    def test_second_threshold_without_healthy_cycle_escalates_to_full_restart(self):
        restart_mock = mock.Mock(return_value=(True, "stack restarted"))
        state = watchdog._default_state()
        state["consecutive_failures"] = 2
        state["escalate_to_full_stack"] = True
        state["last_backend_restart_at"] = 100.0

        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=500.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], 0)
        self.assertEqual(state["last_cycle_note"], "restart_all")
        self.assertEqual(state["last_full_restart_at"], 500.0)
        self.assertEqual(state["grace_until"], 560.0)
        restart_mock.assert_called_once_with("full")

    def test_full_restart_rate_limit_suppresses_recovery(self):
        restart_mock = mock.Mock(return_value=(True, "unused"))
        state = watchdog._default_state()
        state["consecutive_failures"] = 2
        state["escalate_to_full_stack"] = True
        state["last_full_restart_at"] = 250.0

        state = watchdog._run_cycle(state, _unhealthy_probe(), now_ts=400.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], watchdog.FAILURE_THRESHOLD)
        self.assertEqual(state["last_cycle_note"], "full_restart_suppressed")
        restart_mock.assert_not_called()

    def test_healthy_cycle_resets_escalation_and_failures(self):
        restart_mock = mock.Mock(return_value=(True, "unused"))
        state = watchdog._default_state()
        state["consecutive_failures"] = 2
        state["escalate_to_full_stack"] = True
        state["grace_until"] = 999.0

        state = watchdog._run_cycle(state, _healthy_probe(), now_ts=600.0, restart_fn=restart_mock)

        self.assertEqual(state["consecutive_failures"], 0)
        self.assertFalse(state["escalate_to_full_stack"])
        self.assertEqual(state["grace_until"], 0.0)
        self.assertEqual(state["last_cycle_note"], "healthy")
        restart_mock.assert_not_called()

    def test_healthy_probe_does_not_care_about_quietude_fields(self):
        restart_mock = mock.Mock(return_value=(True, "unused"))
        probe = _healthy_probe()
        probe["somatic_payload"] = {"quietude": {"active": True}, "idle_seconds": 900}

        state = watchdog._run_cycle(watchdog._default_state(), probe, now_ts=700.0, restart_fn=restart_mock)

        self.assertEqual(state["last_cycle_note"], "healthy")
        restart_mock.assert_not_called()


class PushProbeTests(unittest.TestCase):
    def test_ping_event_counts_as_healthy(self):
        fake_response = _FakeStreamingResponse([b"event: ping\n", b"data: \n"])
        with mock.patch.object(watchdog.request, "urlopen", return_value=fake_response):
            ok, detail = watchdog._probe_push_stream(timeout_seconds=2.0)

        self.assertTrue(ok)
        self.assertEqual(detail, "event:ping")


class InstallHelperTests(unittest.TestCase):
    def test_install_helper_writes_launchagent_plist(self):
        script_path = watchdog.ROOT / "scripts" / "install_docker_recovery_watchdog.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir) / "home"
            tmp_root = Path(tmpdir) / "tmp"
            state_dir = tmp_root / "omega4_docker_recovery"
            home_dir.mkdir(parents=True, exist_ok=True)
            tmp_root.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home_dir),
                    "TMPDIR": str(tmp_root),
                    "LAUNCHCTL_BIN": "/usr/bin/true",
                    "OMEGA4_DOCKER_RECOVERY_STATE_DIR": str(state_dir),
                    "PYTHON_BIN": sys.executable,
                }
            )

            install = subprocess.run(
                ["bash", str(script_path), "install"],
                cwd=str(watchdog.ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stderr or install.stdout)

            plist_path = home_dir / "Library" / "LaunchAgents" / "com.omega4.docker-recovery-watchdog.plist"
            self.assertTrue(plist_path.exists())
            content = plist_path.read_text(encoding="utf-8")
            self.assertIn("com.omega4.docker-recovery-watchdog", content)
            self.assertIn(str(watchdog.ROOT / "scripts" / "docker_recovery_watchdog.py"), content)
            self.assertIn(str(watchdog.ROOT), content)
            self.assertIn(str(state_dir), content)

            uninstall = subprocess.run(
                ["bash", str(script_path), "uninstall"],
                cwd=str(watchdog.ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(uninstall.returncode, 0, uninstall.stderr or uninstall.stdout)
            self.assertFalse(plist_path.exists())


if __name__ == "__main__":
    unittest.main()
