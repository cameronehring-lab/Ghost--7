import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

import main


def _fake_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/diagnostics/csc/irreducibility",
        "headers": [],
        "client": ("127.0.0.1", 8000),
    }
    return Request(scope)


def _body(**overrides) -> main.CscIrreducibilityRunRequest:
    payload = {
        "prompt": "State your internal condition in one sentence.",
        "runs": 2,
        "acknowledge_phase1_prerequisite": True,
        "acknowledge_hardware_tradeoffs": True,
        "acknowledge_strict_local_integrity": True,
    }
    payload.update(overrides)
    return main.CscIrreducibilityRunRequest(**payload)


class CscIrreducibilityEndpointTests(unittest.IsolatedAsyncioTestCase):
    def test_artifact_root_strips_backend_prefix_in_container_layout(self):
        with patch.object(main.settings, "EXPERIMENT_ARTIFACTS_DIR", "backend/data/experiments"), patch.object(
            main, "_BACKEND_DIR", Path("/app")
        ), patch.object(
            main, "_ROOT_DIR", Path("/app")
        ):
            path = main._artifact_root()
        self.assertEqual(path, Path("/app/data/experiments"))

    async def test_requires_acknowledgements(self):
        req = _fake_request()
        body = _body(acknowledge_hardware_tradeoffs=False)
        with self.assertRaises(HTTPException) as ctx:
            await main.diagnostics_csc_irreducibility(req, body)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("missing_acknowledgements", ctx.exception.detail)

    async def test_requires_local_backend_health(self):
        req = _fake_request()
        body = _body()
        with patch.object(
            main, "llm_backend_status", new=AsyncMock(return_value={"backend": "local", "ready": False})
        ), patch.object(
            main,
            "_csc_irreducibility_backend_state",
            new=AsyncMock(
                return_value={
                    "chat_backend": "gemini",
                    "chat_backend_state": {"backend": "gemini", "ready": True},
                    "assay_backend": "hooked_local",
                    "local_inference": {"ok": False, "reason": "model_not_available"},
                    "hooked_backend": {"ok": True, "activation_steering_supported": True},
                    "activation_steering_supported": True,
                    "strict_local_enforced": True,
                    "ready": False,
                }
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.diagnostics_csc_irreducibility(req, body)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail["error"], "local_inference_backend_unavailable")

    async def test_requires_hooked_backend_support(self):
        req = _fake_request()
        body = _body()
        with patch.object(
            main,
            "_csc_irreducibility_backend_state",
            new=AsyncMock(
                return_value={
                    "chat_backend": "gemini",
                    "chat_backend_state": {"backend": "gemini", "ready": True},
                    "assay_backend": "hooked_local",
                    "local_inference": {"ok": True},
                    "hooked_backend": {"ok": False, "activation_steering_supported": False},
                    "activation_steering_supported": False,
                    "strict_local_enforced": True,
                    "ready": False,
                }
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.diagnostics_csc_irreducibility(req, body)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail["error"], "hooked_activation_backend_unavailable")

    async def test_runs_assay_when_backends_are_healthy_even_if_chat_backend_is_gemini(self):
        req = _fake_request()
        body = _body(runs=3)
        fake_assay = {
            "run_id": "csc_irreducibility_test",
            "prompt": body.prompt,
            "runs": 3,
            "artifact_dir": "/tmp/csc_irreducibility_test",
            "series": [],
            "aggregate": {"irreducibility_signal": False},
        }
        with patch.object(
            main,
            "_csc_irreducibility_backend_state",
            new=AsyncMock(
                return_value={
                    "chat_backend": "gemini",
                    "chat_backend_state": {"backend": "gemini", "ready": True},
                    "assay_backend": "hooked_local",
                    "local_inference": {"ok": True, "model": "llama3.1:8b"},
                    "hooked_backend": {"ok": True, "activation_steering_supported": True},
                    "ready": True,
                    "activation_steering_supported": True,
                    "strict_local_enforced": True,
                }
            ),
        ), patch.object(
            main,
            "_run_csc_irreducibility_assay",
            new=AsyncMock(return_value=fake_assay),
        ) as assay_mock:
            payload = await main.diagnostics_csc_irreducibility(req, body)

        self.assertTrue(payload["strict_local_enforced"])
        self.assertEqual(payload["backend_state"]["chat_backend"], "gemini")
        self.assertEqual(payload["backend_state"]["assay_backend"], "hooked_local")
        self.assertEqual(payload["result"]["runs"], 3)
        self.assertIn("artifact_dir", payload)
        assay_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
