import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import scripts.share_tunnel_watchdog as watchdog


class TunnelHealthClassificationTests(unittest.TestCase):
    def test_classify_healthy_on_401(self):
        state = watchdog._classify_tunnel_health("https://demo.trycloudflare.com", 401)
        self.assertEqual(state, "healthy")

    def test_classify_local_dns_mismatch(self):
        with (
            mock.patch.object(watchdog, "_local_dns_resolves", return_value=False),
            mock.patch.object(watchdog, "_public_dns_resolves", return_value=True),
        ):
            state = watchdog._classify_tunnel_health("https://demo.trycloudflare.com", None)
        self.assertEqual(state, "local_dns_mismatch")

    def test_classify_unreachable_when_dns_fails_everywhere(self):
        with (
            mock.patch.object(watchdog, "_local_dns_resolves", return_value=False),
            mock.patch.object(watchdog, "_public_dns_resolves", return_value=False),
        ):
            state = watchdog._classify_tunnel_health("https://demo.trycloudflare.com", None)
        self.assertEqual(state, "unreachable")


class EnsureOnceBehaviorTests(unittest.TestCase):
    def test_ensure_once_does_not_restart_on_local_dns_mismatch(self):
        tunnel_url = "https://demo.trycloudflare.com"
        with (
            mock.patch.object(watchdog, "_read_pid", return_value=123),
            mock.patch.object(watchdog, "_is_pid_alive", return_value=True),
            mock.patch.object(watchdog, "_wait_for_tunnel_url", return_value=tunnel_url),
            mock.patch.object(watchdog, "_run_curl_head", return_value=None),
            mock.patch.object(watchdog, "_classify_tunnel_health", return_value="local_dns_mismatch"),
            mock.patch.object(watchdog, "_stop_cloudflared") as stop_mock,
            mock.patch.object(watchdog, "_start_cloudflared_safe") as start_mock,
            mock.patch.object(watchdog, "_write_text"),
            mock.patch.object(watchdog, "_update_handoff"),
        ):
            url, status_code, restarted, resolver_issue = watchdog._ensure_once(restart_on_unhealthy=True)

        self.assertEqual(url, tunnel_url)
        self.assertIsNone(status_code)
        self.assertFalse(restarted)
        self.assertEqual(resolver_issue, "local_dns_mismatch")
        start_mock.assert_not_called()
        stop_mock.assert_not_called()

    def test_ensure_once_restarts_on_unreachable(self):
        tunnel_url = "https://demo.trycloudflare.com"
        with (
            mock.patch.object(watchdog, "_read_pid", return_value=123),
            mock.patch.object(watchdog, "_is_pid_alive", return_value=True),
            mock.patch.object(watchdog, "_wait_for_tunnel_url", side_effect=[tunnel_url, tunnel_url]),
            mock.patch.object(watchdog, "_run_curl_head", side_effect=[None, 401]),
            mock.patch.object(watchdog, "_classify_tunnel_health", side_effect=["unreachable", "healthy"]),
            mock.patch.object(watchdog, "_stop_cloudflared") as stop_mock,
            mock.patch.object(watchdog, "_start_cloudflared_safe", return_value=True) as start_mock,
            mock.patch.object(watchdog, "_write_text"),
            mock.patch.object(watchdog, "_update_handoff"),
        ):
            _, status_code, restarted, resolver_issue = watchdog._ensure_once(restart_on_unhealthy=True)

        self.assertEqual(status_code, 401)
        self.assertTrue(restarted)
        self.assertEqual(resolver_issue, "healthy")
        stop_mock.assert_called_once()
        start_mock.assert_called_once()


class StatusOutputTests(unittest.TestCase):
    def test_status_includes_resolver_issue_field(self):
        with (
            mock.patch.object(watchdog, "SHARE_TUNNEL_MODE", "quick"),
            mock.patch.object(watchdog, "_read_pid", return_value=777),
            mock.patch.object(watchdog, "_is_pid_alive", return_value=True),
            mock.patch.object(watchdog, "_read_text", return_value="https://demo.trycloudflare.com\n"),
            mock.patch.object(watchdog, "_run_curl_head", return_value=None),
            mock.patch.object(watchdog, "_classify_tunnel_health", return_value="local_dns_mismatch"),
            mock.patch.object(watchdog, "_origin_status", return_value=200),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = watchdog._cmd_status()

        out = buf.getvalue().strip()
        self.assertEqual(rc, 0)
        self.assertIn("pid=777", out)
        self.assertIn("alive=True", out)
        self.assertIn("status=None", out)
        self.assertIn("resolver_issue=local_dns_mismatch", out)
        self.assertIn("tunnel_mode=quick", out)
        self.assertIn("connector_health=healthy", out)
        self.assertIn("origin_health=healthy", out)


class CrossPlatformBehaviorTests(unittest.TestCase):
    def test_state_dir_uses_system_tempdir(self):
        self.assertEqual(watchdog.STATE_DIR, Path(tempfile.gettempdir()) / "omega4_share_tunnel")

    def test_stop_cloudflared_uses_taskkill_on_windows(self):
        with (
            mock.patch.object(watchdog, "_read_pid", return_value=456),
            mock.patch.object(watchdog, "_is_pid_alive", side_effect=[True, True]),
            mock.patch.object(watchdog.os, "kill") as kill_mock,
            mock.patch.object(watchdog, "_kill_pid_windows") as taskkill_mock,
            mock.patch.object(watchdog.time, "time", side_effect=[0, 7]),
            mock.patch.object(watchdog.time, "sleep"),
            mock.patch.object(watchdog, "_write_text") as write_mock,
            mock.patch.object(watchdog.sys, "platform", "win32"),
        ):
            watchdog._stop_cloudflared()

        kill_mock.assert_called_once_with(456, watchdog.signal.SIGTERM)
        taskkill_mock.assert_called_once_with(456)
        write_mock.assert_called_once_with(watchdog.PID_PATH, "")

    def test_stop_cloudflared_uses_sigkill_on_unix(self):
        with (
            mock.patch.object(watchdog, "_read_pid", return_value=456),
            mock.patch.object(watchdog, "_is_pid_alive", side_effect=[True, True]),
            mock.patch.object(watchdog.os, "kill") as kill_mock,
            mock.patch.object(watchdog, "_kill_pid_windows") as taskkill_mock,
            mock.patch.object(watchdog.time, "time", side_effect=[0, 7]),
            mock.patch.object(watchdog.time, "sleep"),
            mock.patch.object(watchdog, "_write_text") as write_mock,
            mock.patch.object(watchdog.sys, "platform", "darwin"),
        ):
            watchdog._stop_cloudflared()

        self.assertEqual(kill_mock.call_count, 2)
        kill_mock.assert_any_call(456, watchdog.signal.SIGTERM)
        kill_mock.assert_any_call(456, watchdog.signal.SIGKILL)
        taskkill_mock.assert_not_called()
        write_mock.assert_called_once_with(watchdog.PID_PATH, "")


class NamedModeTests(unittest.TestCase):
    def test_wait_for_tunnel_url_returns_fixed_url_in_named_mode(self):
        with (
            mock.patch.object(watchdog, "SHARE_TUNNEL_MODE", "named"),
            mock.patch.object(watchdog, "SHARE_TUNNEL_FIXED_HOSTNAME_RAW", "omega-protocol-ghost.com"),
        ):
            url = watchdog._wait_for_tunnel_url(timeout_seconds=0)

        self.assertEqual(url, "https://omega-protocol-ghost.com")

    def test_named_mode_config_error_requires_token(self):
        with (
            mock.patch.object(watchdog, "SHARE_TUNNEL_MODE", "named"),
            mock.patch.object(watchdog, "SHARE_TUNNEL_FIXED_HOSTNAME_RAW", "omega-protocol-ghost.com"),
            mock.patch.object(watchdog, "CLOUDFLARE_TUNNEL_TOKEN", ""),
            mock.patch.object(watchdog, "CLOUDFLARED_BIN", "/opt/homebrew/bin/cloudflared"),
            mock.patch.object(watchdog.Path, "exists", return_value=True),
        ):
            err = watchdog._named_mode_config_error()

        self.assertEqual(
            err,
            "CLOUDFLARE_TUNNEL_TOKEN is required when SHARE_TUNNEL_MODE=named.",
        )

    def test_start_cloudflared_in_named_mode_sets_token_env(self):
        popen_mock = mock.Mock()
        popen_mock.pid = 9876
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            with (
                mock.patch.object(watchdog, "SHARE_TUNNEL_MODE", "named"),
                mock.patch.object(watchdog, "SHARE_TUNNEL_FIXED_HOSTNAME_RAW", "omega-protocol-ghost.com"),
                mock.patch.object(watchdog, "CLOUDFLARE_TUNNEL_TOKEN", "secret-token"),
                mock.patch.object(watchdog, "STATE_DIR", state_dir),
                mock.patch.object(watchdog, "LOG_PATH", state_dir / "cloudflared.log"),
                mock.patch.object(watchdog, "PID_PATH", state_dir / "cloudflared.pid"),
                mock.patch.object(watchdog.subprocess, "Popen", return_value=popen_mock) as popen_ctor,
            ):
                pid = watchdog._start_cloudflared()

        self.assertEqual(pid, 9876)
        cmd = popen_ctor.call_args.args[0]
        kwargs = popen_ctor.call_args.kwargs
        self.assertEqual(cmd, [watchdog.CLOUDFLARED_BIN, "tunnel", "run", "--url", "http://localhost:8000"])
        self.assertIn("TUNNEL_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["env"]["TUNNEL_TOKEN"], "secret-token")


class EnvLoadingTests(unittest.TestCase):
    def test_load_env_defaults_sets_missing_keys_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("A=one\nB='two'\n#C=three\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"B": "existing"}, clear=False):
                watchdog._load_env_defaults(env_file)
                self.assertEqual(os.environ.get("A"), "one")
                self.assertEqual(os.environ.get("B"), "existing")


if __name__ == "__main__":
    unittest.main()
