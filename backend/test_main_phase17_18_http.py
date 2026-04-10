import asyncio
import base64
import unittest
from unittest.mock import patch

import httpx

import main


def _share_auth_headers() -> dict[str, str]:
    if not bool(getattr(main.settings, "SHARE_MODE_ENABLED", False)):
        return {}
    user = str(getattr(main.settings, "SHARE_MODE_USERNAME", "") or "")
    password = str(getattr(main.settings, "SHARE_MODE_PASSWORD", "") or "")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class MainPhase1718HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._prev_queue = main.sys_state.external_event_queue
        self._prev_negotiating = main.sys_state.is_negotiating_rest
        self._prev_intent = main.sys_state.quietude_intent

        main.sys_state.external_event_queue = asyncio.Queue()
        main.sys_state.is_negotiating_rest = False
        main.sys_state.quietude_intent = None

    async def asyncTearDown(self):
        main.sys_state.external_event_queue = self._prev_queue
        main.sys_state.is_negotiating_rest = self._prev_negotiating
        main.sys_state.quietude_intent = self._prev_intent

    async def test_quietude_intent_and_grant_http_routes(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with patch.object(main, "_schedule_self_quietude", return_value={"scheduled": True}):
                intent = await client.post(
                    "/ghost/quietude/intent",
                    json={"depth": "profound", "message": "integration window"},
                    headers=headers,
                )
                grant = await client.post("/ghost/quietude/grant", headers=headers)

        self.assertEqual(intent.status_code, 200)
        self.assertEqual(grant.status_code, 200)
        self.assertEqual(intent.json().get("status"), "ok")
        self.assertEqual(grant.json().get("status"), "ok")

    async def test_dream_assets_http_route_serves_sample(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/dream_assets/sample.png", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(str(response.headers.get("content-type", "")).startswith("image/"))
        self.assertGreater(len(response.content), 0)


if __name__ == "__main__":
    unittest.main()
