import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "omega_expert_tool.py"


class OmegaExpertToolTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_overview_command_contains_expected_spine(self) -> None:
        result = self._run("overview")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("OVERVIEW", result.stdout)
        self.assertIn("browser -> /ghost/chat", result.stdout)
        self.assertIn("backend/main.py", result.stdout)

    def test_quick_read_order_json_shape(self) -> None:
        result = self._run("read-order", "--profile", "quick", "--json")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["section"], "read_order")
        self.assertEqual(payload["profile"], "quick")
        self.assertEqual(len(payload["steps"]), 5)
        refs = [ref["path"] for step in payload["steps"] for ref in step["refs"]]
        self.assertIn("backend/main.py", refs)
        self.assertIn("backend/ghost_api.py", refs)

    def test_chat_trace_json_includes_route_and_stream(self) -> None:
        result = self._run("chat-trace", "--json")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["section"], "chat_trace")
        self.assertGreaterEqual(len(payload["steps"]), 8)
        joined = " ".join(step["summary"] for step in payload["steps"])
        self.assertIn("/ghost/chat", joined)
        self.assertIn("SSE", joined)


if __name__ == "__main__":
    unittest.main()
