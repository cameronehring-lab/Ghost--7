import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import local_llm_client


class _Part:
    def __init__(self, text: str):
        self.text = text


class _Content:
    def __init__(self, role: str, parts):
        self.role = role
        self.parts = parts


class LocalLlmClientTests(unittest.TestCase):
    def setUp(self):
        local_llm_client._local_client = None  # type: ignore[attr-defined]
        local_llm_client._local_client_fingerprint = ""  # type: ignore[attr-defined]
        local_llm_client._reset_local_model_state()  # type: ignore[attr-defined]

    def test_extract_messages_maps_model_to_assistant(self):
        messages = local_llm_client._extract_messages(
            [
                _Content("user", [_Part("hello")]),
                _Content("model", [_Part("world")]),
            ],
            system_instruction="system guidance",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "world")

    def test_extract_messages_handles_dict_content(self):
        payload = [
            {"role": "user", "content": "u1"},
            {"role": "model", "parts": [{"text": "m1"}]},
            {"role": "tool", "parts": [{"function_response": {"status": "ok"}}]},
        ]
        messages = local_llm_client._extract_messages(payload)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("status", messages[2]["content"])

    def test_local_backend_ready_hint_local_mode_requires_base_url_and_model(self):
        with patch.object(local_llm_client.settings, "LLM_BACKEND", "local"), patch.object(
            local_llm_client.settings, "LOCAL_LLM_BASE_URL", "http://ollama:11434"
        ), patch.object(local_llm_client.settings, "LOCAL_LLM_MODEL", "llama3.1:8b"):
            self.assertTrue(local_llm_client.local_backend_ready_hint())

        with patch.object(local_llm_client.settings, "LLM_BACKEND", "local"), patch.object(
            local_llm_client.settings, "LOCAL_LLM_BASE_URL", ""
        ), patch.object(local_llm_client.settings, "LOCAL_LLM_MODEL", "llama3.1:8b"):
            self.assertFalse(local_llm_client.local_backend_ready_hint())

    def test_model_available_ollama_requires_configured_model(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b",
            api_format="ollama",
            timeout_seconds=30,
        )

        class _Resp:
            def json(self):
                return {"models": []}

        ok, details = client._model_available(_Resp())
        self.assertFalse(ok)
        self.assertEqual(details.get("reason"), "model_not_available")
        self.assertEqual(details.get("available_models"), [])

    def test_model_available_ollama_accepts_matching_name(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b",
            api_format="ollama",
            timeout_seconds=30,
        )

        class _Resp:
            def json(self):
                return {
                    "models": [
                        {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                    ]
                }

        ok, details = client._model_available(_Resp())
        self.assertTrue(ok)
        self.assertIn("llama3.1:8b", details.get("available_models", []))

    def test_model_available_ollama_accepts_instruct_alias_for_legacy_config(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b-instruct",
            api_format="ollama",
            timeout_seconds=30,
        )

        class _Resp:
            def json(self):
                return {
                    "models": [
                        {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                    ]
                }

        ok, details = client._model_available(_Resp())
        self.assertTrue(ok)
        self.assertIn("llama3.1:8b", details.get("available_models", []))

    def test_estimate_prompt_tokens_counts_system_and_messages(self):
        estimate = local_llm_client.estimate_prompt_tokens(
            contents=[
                {"role": "user", "content": "hello world"},
                {"role": "model", "content": "response"},
            ],
            config={"system_instruction": "system block"},
        )
        self.assertGreaterEqual(estimate, 10)


class LocalLlmProvisioningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        local_llm_client._local_client = None  # type: ignore[attr-defined]
        local_llm_client._local_client_fingerprint = ""  # type: ignore[attr-defined]
        local_llm_client._reset_local_model_state()  # type: ignore[attr-defined]

    async def asyncTearDown(self):
        await local_llm_client.wait_for_active_pull(timeout=0.1)
        local_llm_client._local_client = None  # type: ignore[attr-defined]
        local_llm_client._local_client_fingerprint = ""  # type: ignore[attr-defined]
        local_llm_client._reset_local_model_state()  # type: ignore[attr-defined]

    async def test_schedule_background_pull_transitions_to_ready(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b",
            api_format="ollama",
            timeout_seconds=30,
        )
        local_llm_client._reset_local_model_state(client)  # type: ignore[attr-defined]

        async def _fake_pull(_client, _reason):
            await asyncio.sleep(0)
            local_llm_client._update_local_model_state(  # type: ignore[attr-defined]
                status="ready",
                model_ready=True,
                reason="",
                last_error="",
                completed_at=123.0,
            )

        with patch.object(local_llm_client.settings, "LOCAL_LLM_AUTO_PULL_ENABLED", True), patch.object(
            local_llm_client, "get_local_client", return_value=client
        ), patch.object(
            local_llm_client, "_pull_missing_model", new=AsyncMock(side_effect=_fake_pull)
        ):
            state = await local_llm_client._schedule_background_pull("unit_test")  # type: ignore[attr-defined]
            self.assertEqual(state["status"], "pulling")
            await local_llm_client.wait_for_active_pull(timeout=0.2)

        final_state = local_llm_client.get_local_model_state()
        self.assertEqual(final_state["status"], "ready")
        self.assertTrue(final_state["model_ready"])

    async def test_health_missing_model_marks_not_ready_and_schedules_pull(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b",
            api_format="ollama",
            timeout_seconds=30,
        )
        local_llm_client._reset_local_model_state(client)  # type: ignore[attr-defined]

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"models": []}

        class _AsyncClient:
            def __init__(self, *args, **kwargs):  # pylint: disable=unused-argument
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):  # pylint: disable=unused-argument
                return False

            async def get(self, url):  # pylint: disable=unused-argument
                return _Resp()

        with patch.object(local_llm_client.settings, "LLM_BACKEND", "local"), patch.object(
            local_llm_client.settings, "LOCAL_LLM_AUTO_PULL_ENABLED", True
        ), patch.object(
            local_llm_client.httpx, "AsyncClient", _AsyncClient
        ), patch.object(
            local_llm_client, "_schedule_background_pull", new=AsyncMock(return_value={"status": "pulling"})
        ) as schedule_mock:
            health = await client.health()

        self.assertFalse(health["ok"])
        self.assertEqual(health["reason"], "model_not_available")
        self.assertEqual(local_llm_client.get_local_model_state()["status"], "idle")
        schedule_mock.assert_awaited_once()

    async def test_ensure_model_provisioning_returns_error_state_when_pull_fails(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.1:8b",
            api_format="ollama",
            timeout_seconds=30,
        )
        local_llm_client._reset_local_model_state(client)  # type: ignore[attr-defined]

        with patch.object(
            local_llm_client, "get_local_client", return_value=client
        ), patch.object(
            client, "health", new=AsyncMock(return_value={"ok": False, "reason": "model_not_available"})
        ), patch.object(
            local_llm_client, "_schedule_background_pull", new=AsyncMock()
        ):
            await local_llm_client.ensure_model_provisioning("unit_test")

        local_llm_client._update_local_model_state(  # type: ignore[attr-defined]
            status="error",
            reason="pull_http_500",
            last_error="pull_http_500",
            completed_at=321.0,
        )
        state = local_llm_client.get_local_model_state()
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["last_error"], "pull_http_500")

    async def test_generate_ollama_includes_keep_alive(self):
        client = local_llm_client.LocalLLMClient(
            base_url="http://ollama:11434",
            model="llama3.2:3b",
            api_format="ollama",
            timeout_seconds=30,
        )
        captured = {}

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"message": {"content": "ok"}}

        class _AsyncClient:
            def __init__(self, *args, **kwargs):  # pylint: disable=unused-argument
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):  # pylint: disable=unused-argument
                return False

            async def post(self, url, json):  # pylint: disable=redefined-builtin,unused-argument
                captured["payload"] = dict(json)
                return _Resp()

        with patch.object(local_llm_client.settings, "LOCAL_LLM_KEEP_ALIVE", "30m"), patch.object(
            local_llm_client.httpx, "AsyncClient", _AsyncClient
        ):
            response = await client.generate(contents="hello", config={})

        self.assertEqual(response.text, "ok")
        self.assertEqual(captured["payload"]["keep_alive"], "30m")


if __name__ == "__main__":
    unittest.main()
