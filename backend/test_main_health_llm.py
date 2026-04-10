import base64
import unittest
from unittest.mock import AsyncMock, patch

import httpx

import main


def _share_auth_headers() -> dict[str, str]:
    if not bool(getattr(main.settings, "SHARE_MODE_ENABLED", False)):
        return {}
    user = str(getattr(main.settings, "SHARE_MODE_USERNAME", "") or "")
    password = str(getattr(main.settings, "SHARE_MODE_PASSWORD", "") or "")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class MainHealthLlmTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_degraded_local_runtime(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        llm_state = {
            "ready": True,
            "default_backend": "local",
            "default_model": "llama3.1:8b",
            "effective_backend": "gemini",
            "effective_model": "gemini-2.5-flash",
            "active_backend": "gemini",
            "active_model": "gemini-2.5-flash",
            "last_generation_reason": "prompt_budget_exceeded",
            "local_model_ready": False,
            "degraded_reason": "model_not_available",
        }
        with patch.object(main, "llm_backend_status", new=AsyncMock(return_value=llm_state)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["llm_ready"])
        self.assertEqual(payload["llm_backend"], "gemini")
        self.assertEqual(payload["model"], "gemini-2.5-flash")
        self.assertEqual(payload["llm_default_backend"], "local")
        self.assertEqual(payload["llm_effective_backend"], "gemini")
        self.assertEqual(payload["llm_active_backend"], "gemini")
        self.assertEqual(payload["llm_active_model"], "gemini-2.5-flash")
        self.assertEqual(payload["llm_last_reason"], "prompt_budget_exceeded")
        self.assertFalse(payload["local_model_ready"])
        self.assertTrue(payload["llm_degraded"])
        self.assertEqual(payload["llm_degraded_reason"], "model_not_available")

    async def test_health_reports_local_runtime_when_ready(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        llm_state = {
            "ready": True,
            "default_backend": "local",
            "default_model": "llama3.1:8b",
            "effective_backend": "local",
            "effective_model": "llama3.1:8b",
            "active_backend": "local",
            "active_model": "llama3.1:8b",
            "last_generation_reason": "",
            "local_model_ready": True,
            "degraded_reason": "",
        }
        with patch.object(main, "llm_backend_status", new=AsyncMock(return_value=llm_state)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["llm_backend"], "local")
        self.assertEqual(payload["model"], "llama3.1:8b")
        self.assertEqual(payload["llm_effective_backend"], "local")
        self.assertEqual(payload["llm_active_backend"], "local")
        self.assertEqual(payload["llm_active_model"], "llama3.1:8b")
        self.assertTrue(payload["local_model_ready"])
        self.assertFalse(payload["llm_degraded"])


if __name__ == "__main__":
    unittest.main()
