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


class MainConstraintDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_exposes_constraint_backend_fields(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        llm_state = {
            "ready": True,
            "default_backend": "gemini",
            "default_model": "gemini-2.5-flash",
            "effective_backend": "gemini",
            "effective_model": "gemini-2.5-flash",
            "active_backend": "gemini",
            "active_model": "gemini-2.5-flash",
            "last_generation_reason": "",
            "local_model_ready": False,
            "degraded_reason": "",
            "constrained_backend_ready": True,
            "constraint_grammar_engine": "internal",
            "constraint_checker_ready": True,
            "last_constraint_route_reason": "constraint_satisfied",
        }
        with patch.object(main, "llm_backend_status", new=AsyncMock(return_value=llm_state)):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health", headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["constrained_backend_ready"])
        self.assertEqual(payload["constraint_grammar_engine"], "internal")
        self.assertTrue(payload["constraint_checker_ready"])
        self.assertEqual(payload["constraint_last_route_reason"], "constraint_satisfied")

    async def test_constraints_run_endpoint_returns_controller_result(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        controller = type(
            "Controller",
            (),
            {
                "health": lambda self: {"ok": True, "grammar_engine": "internal"},  # pylint: disable=unnecessary-lambda
                "run": AsyncMock(
                    return_value={
                        "model_dump": lambda: {
                            "success": True,
                            "text": "alpha beta",
                            "attempts_used": 1,
                            "route": "local_transformers",
                            "grammar_engine": "internal",
                            "checker_used": False,
                            "validation_passed": True,
                        }
                    }
                ),
            },
        )()
        result_obj = type(
            "Result",
            (),
            {
                "success": True,
                "model_dump": lambda self: {
                    "success": True,
                    "text": "alpha beta",
                    "attempts_used": 1,
                    "route": "local_transformers",
                    "grammar_engine": "internal",
                    "checker_used": False,
                    "validation_passed": True,
                },
            },
        )()
        controller.run = AsyncMock(return_value=result_obj)
        with patch.object(main, "_require_local_request"), patch.object(
            main.constrained_generation,
            "get_constraint_controller",
            return_value=controller,
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/diagnostics/constraints/run",
                    headers=headers,
                    json={
                        "prompt": "Say two words.",
                        "constraints": {"exact_word_count": 2},
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["text"], "alpha beta")

    async def test_constraints_benchmark_endpoint_returns_summary(self):
        transport = httpx.ASGITransport(app=main.app)
        headers = _share_auth_headers()
        benchmark = {
            "suite_name": "gordian_knot",
            "records": [],
            "metrics": {"exact_pass_rate": 1.0},
        }
        controller = type("Controller", (), {"health": lambda self: {"ok": True}})()  # pylint: disable=unnecessary-lambda
        with patch.object(main, "_require_local_request"), patch.object(
            main.constrained_generation,
            "get_constraint_controller",
            return_value=controller,
        ), patch.object(
            main.constrained_generation,
            "run_gordian_knot_benchmark",
            new=AsyncMock(return_value=benchmark),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/diagnostics/constraints/benchmark",
                    headers=headers,
                    json={"persist_artifacts": False},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["benchmark"]["suite_name"], "gordian_knot")


if __name__ == "__main__":
    unittest.main()
