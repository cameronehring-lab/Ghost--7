"""
Local LLM adapter for OMEGA4.

Phase 1 scope:
  - Route text generation to a local inference server (Ollama or OpenAI-compatible API).
  - Preserve ghost_api call shape by returning an object with `.text` and `.candidates`.
  - Expose a placeholder activation handle for future steering integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncGenerator, Optional

import httpx  # type: ignore

from config import settings  # type: ignore

logger = logging.getLogger("omega.local_llm")


_OLLAMA_MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "llama3.1:8b-instruct": ("llama3.1:8b",),
    "llama3.1:70b-instruct": ("llama3.1:70b",),
    "llama3.2:3b-instruct": ("llama3.2:3b",),
    "llama3.2:1b-instruct": ("llama3.2:1b",),
}


@dataclass
class ActivationHandle:
    backend: str
    model: str
    api_format: str
    activation_steering_supported: bool
    reason: str = "phase_2_not_implemented"
    n_layers: int = 32
    hidden_size: int = 0
    target_layers: tuple[int, int] = (12, 22)


@dataclass
class LocalPart:
    text: str = ""
    function_call: Any = None


@dataclass
class LocalContent:
    role: str = "model"
    parts: list[LocalPart] = field(default_factory=list)


@dataclass
class LocalCandidate:
    content: LocalContent
    grounding_metadata: Any = None


@dataclass
class LocalLLMResponse:
    text: str
    candidates: list[LocalCandidate] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalModelState:
    status: str = "idle"  # idle|pulling|ready|error
    model: str = ""
    api_format: str = "ollama"
    base_url: str = ""
    service_reachable: bool = False
    model_ready: bool = False
    available_models: list[str] = field(default_factory=list)
    reason: str = ""
    last_error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    last_checked_at: float = 0.0


def _normalize_api_format(raw: Any) -> str:
    value = str(raw or "ollama").strip().lower()
    if value in {"openai", "openai_compatible"}:
        return "openai"
    return "ollama"


def _cfg_get(config: Any, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _normalize_role(raw_role: Any) -> str:
    role = str(raw_role or "user").strip().lower()
    if role == "model":
        return "assistant"
    if role not in {"system", "user", "assistant", "tool"}:
        return "user"
    return role


def _flatten_part_text(part: Any) -> str:
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if "text" in part and str(part.get("text") or "").strip():
            return str(part.get("text") or "")
        if "function_response" in part:
            try:
                return json.dumps(part.get("function_response") or {}, ensure_ascii=False)
            except Exception:
                return str(part.get("function_response") or "")
        if "content" in part:
            return _flatten_content_text(part.get("content"))
        return str(part.get("value") or "")

    text = getattr(part, "text", None)
    if str(text or "").strip():
        return str(text)

    function_response = getattr(part, "function_response", None)
    if function_response is not None:
        payload = getattr(function_response, "response", function_response)
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return str(payload)

    return str(part or "")


def _flatten_content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(s for s in (_flatten_part_text(p).strip() for p in content) if s).strip()
    if isinstance(content, dict):
        if "parts" in content:
            return _flatten_content_text(content.get("parts"))
        if "content" in content:
            return _flatten_content_text(content.get("content"))
        return _flatten_part_text(content).strip()

    parts = getattr(content, "parts", None)
    if parts is not None:
        return _flatten_content_text(parts)

    return _flatten_part_text(content).strip()


def estimate_prompt_tokens(contents: Any, config: Any) -> int:
    system_instruction = _extract_system_instruction(config)
    messages = _extract_messages(contents, system_instruction=system_instruction)
    total_chars = 0
    for message in messages:
        total_chars += len(str(message.get("role") or ""))
        total_chars += len(str(message.get("content") or ""))
        total_chars += 8
    # Coarse character-based estimate. Good enough for preflight routing.
    return max(1, int((total_chars + 3) // 4))


def _extract_messages(contents: Any, system_instruction: str = "") -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if str(system_instruction or "").strip():
        messages.append({"role": "system", "content": str(system_instruction).strip()})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
        return messages

    if not isinstance(contents, (list, tuple)):
        contents = [contents]

    for item in contents:
        if isinstance(item, dict):
            role = _normalize_role(item.get("role"))
            text = _flatten_content_text(item.get("parts") or item.get("content") or item).strip()
        else:
            role = _normalize_role(getattr(item, "role", None))
            text = _flatten_content_text(item).strip()
        if text:
            messages.append({"role": role, "content": text})
    return messages


def _extract_temperature(config: Any, default: float = 0.7) -> float:
    raw = _cfg_get(config, "temperature", default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _extract_max_tokens(config: Any, default: int = 2048) -> int:
    raw = _cfg_get(config, "max_output_tokens", None)
    if raw is None:
        raw = _cfg_get(config, "max_tokens", default)
    try:
        return max(64, int(raw))
    except Exception:
        return int(default)


def _extract_system_instruction(config: Any) -> str:
    raw = _cfg_get(config, "system_instruction", "")
    return _flatten_content_text(raw).strip()


def _fallback_to_gemini_enabled() -> bool:
    return bool(getattr(settings, "LOCAL_LLM_FALLBACK_TO_GEMINI_ENABLED", True))


def _ollama_model_candidates(model_name: str) -> list[str]:
    base = str(model_name or "").strip()
    if not base:
        return []
    candidates: list[str] = [base]
    for alias in _OLLAMA_MODEL_ALIASES.get(base, ()):
        if alias not in candidates:
            candidates.append(alias)
    if base.endswith("-instruct"):
        stripped = base[: -len("-instruct")]
        if stripped and stripped not in candidates:
            candidates.append(stripped)
    return candidates


def _resolve_ollama_model_name(model_name: str, available_models: Optional[list[str]] = None) -> str:
    candidates = _ollama_model_candidates(model_name)
    if not candidates:
        return ""
    available = [str(item or "").strip() for item in list(available_models or []) if str(item or "").strip()]
    if available:
        for candidate in candidates:
            if candidate in available:
                return candidate
    return candidates[-1]


def local_backend_ready_hint() -> bool:
    if str(settings.LLM_BACKEND or "").strip().lower() != "local":
        return bool(str(settings.GOOGLE_API_KEY or "").strip())
    return bool(str(settings.LOCAL_LLM_BASE_URL or "").strip() and str(settings.LOCAL_LLM_MODEL or "").strip())


class LocalLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_format: str,
        timeout_seconds: float,
    ):
        self.base_url = str(base_url or "").rstrip("/")
        self.model = str(model or "").strip()
        self.api_format = _normalize_api_format(api_format)
        self.timeout_seconds = max(5.0, float(timeout_seconds or 90.0))

    async def health(self) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "reason": "missing_base_url"}
        path = "/api/tags" if self.api_format == "ollama" else "/v1/models"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(f"{self.base_url}{path}")
            ok = 200 <= int(resp.status_code) < 300
            payload: dict[str, Any] = {
                "ok": ok,
                "status_code": int(resp.status_code),
                "base_url": self.base_url,
                "api_format": self.api_format,
                "model": self.model,
            }
            if ok:
                model_ok, details = self._model_available(resp)
                payload.update(details)
                payload["ok"] = bool(model_ok)
            _merge_model_state_from_health(self, payload)
            if (
                self.api_format == "ollama"
                and str(settings.LLM_BACKEND or "").strip().lower() == "local"
                and bool(getattr(settings, "LOCAL_LLM_AUTO_PULL_ENABLED", True))
                and str(payload.get("reason") or "") == "model_not_available"
            ):
                await _schedule_background_pull("health_probe")
            return payload
        except Exception as exc:
            payload = {
                "ok": False,
                "reason": f"request_error:{exc}",
                "base_url": self.base_url,
                "api_format": self.api_format,
                "model": self.model,
            }
            _merge_model_state_from_health(self, payload)
            return payload

    def _model_available(self, response: httpx.Response) -> tuple[bool, dict[str, Any]]:
        try:
            data = response.json()
        except Exception:
            return False, {"reason": "invalid_health_payload"}

        if self.api_format == "ollama":
            models = data.get("models") if isinstance(data, dict) else []
            if not isinstance(models, list):
                return False, {"reason": "invalid_health_payload"}
            available = []
            for item in models:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                model = str(item.get("model") or "").strip()
                if name:
                    available.append(name)
                if model and model not in available:
                    available.append(model)
            if not self.model:
                return False, {"reason": "missing_model_name", "available_models": available}
            accepted = _ollama_model_candidates(self.model)
            if not any(candidate in available for candidate in accepted):
                return False, {"reason": "model_not_available", "available_models": available}
            return True, {"available_models": available}

        models = data.get("data") if isinstance(data, dict) else []
        if not isinstance(models, list):
            return False, {"reason": "invalid_health_payload"}
        available = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if model_id:
                available.append(model_id)
        if not self.model:
            return False, {"reason": "missing_model_name", "available_models": available}
        if self.model not in available:
            return False, {"reason": "model_not_available", "available_models": available}
        return True, {"available_models": available}

    def get_activation_handle(self) -> ActivationHandle:
        return ActivationHandle(
            backend="local",
            model=self.model,
            api_format=self.api_format,
            activation_steering_supported=False,
            reason="phase_2_not_implemented",
        )

    async def generate(self, contents: Any, config: Any, model: Optional[str] = None) -> LocalLLMResponse:
        if not self.base_url:
            raise RuntimeError("Local LLM backend missing LOCAL_LLM_BASE_URL")
        selected_model = str(model or self.model or "").strip()
        if not selected_model:
            raise RuntimeError("Local LLM backend missing LOCAL_LLM_MODEL")

        system_instruction = _extract_system_instruction(config)
        messages = _extract_messages(contents, system_instruction=system_instruction)
        if not messages:
            messages = [{"role": "user", "content": ""}]

        temperature = _extract_temperature(config)
        max_tokens = _extract_max_tokens(config)

        if self.api_format == "openai":
            return await self._generate_openai(selected_model, messages, temperature, max_tokens)
        return await self._generate_ollama(selected_model, messages, temperature, max_tokens)

    async def generate_stream(
        self,
        prompt: str,
        config: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        response = await self.generate(prompt, config or {}, model=model)
        if response.text:
            yield response.text

    async def _generate_ollama(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> LocalLLMResponse:
        resolved_model = _resolve_ollama_model_name(model)
        payload = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "keep_alive": str(getattr(settings, "LOCAL_LLM_KEEP_ALIVE", "30m") or "30m"),
            "options": {
                "temperature": float(temperature),
                "num_predict": int(max_tokens),
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(f"Local LLM backend HTTP {resp.status_code}: {resp.text[:260]}")
        data = dict(resp.json() or {})
        text = str(((data.get("message") or {}).get("content")) or "").strip()
        return self._wrap_response(text, data)

    async def _generate_openai(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> LocalLLMResponse:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(f"Local LLM backend HTTP {resp.status_code}: {resp.text[:260]}")
        data = dict(resp.json() or {})
        choices = list(data.get("choices") or [])
        first = dict(choices[0] or {}) if choices else {}
        message = dict(first.get("message") or {})
        text = str(message.get("content") or "").strip()
        return self._wrap_response(text, data)

    @staticmethod
    def _wrap_response(text: str, raw: dict[str, Any]) -> LocalLLMResponse:
        content = LocalContent(role="model", parts=[LocalPart(text=text)] if text else [])
        candidate = LocalCandidate(content=content)
        return LocalLLMResponse(
            text=text,
            candidates=[candidate],
            raw=raw,
        )


_local_client: Optional[LocalLLMClient] = None
_local_client_fingerprint: str = ""
_local_model_state = LocalModelState()
_local_model_state_fingerprint: str = ""
_local_model_pull_lock = asyncio.Lock()
_local_model_pull_task: Optional[asyncio.Task[Any]] = None


def _fingerprint() -> str:
    return "|".join(
        [
            str(settings.LOCAL_LLM_BASE_URL or "").strip(),
            str(settings.LOCAL_LLM_MODEL or "").strip(),
            _normalize_api_format(settings.LOCAL_LLM_API_FORMAT),
            str(settings.LOCAL_LLM_TIMEOUT_SECONDS or "").strip(),
        ]
    )


def _reset_local_model_state(client: Optional[LocalLLMClient] = None) -> None:
    global _local_model_state, _local_model_state_fingerprint, _local_model_pull_task
    client = client or _local_client
    _local_model_state = LocalModelState(
        model=str(getattr(client, "model", "") or "").strip(),
        api_format=str(getattr(client, "api_format", "ollama") or "ollama").strip().lower(),
        base_url=str(getattr(client, "base_url", "") or "").rstrip("/"),
    )
    _local_model_state_fingerprint = _fingerprint()
    _local_model_pull_task = None


def _ensure_local_model_state(client: Optional[LocalLLMClient] = None) -> None:
    if _local_model_state_fingerprint != _fingerprint():
        _reset_local_model_state(client)


def _merge_model_state_from_health(client: LocalLLMClient, health: dict[str, Any]) -> None:
    _ensure_local_model_state(client)
    now = time.time()
    state = _local_model_state
    state.model = client.model
    state.api_format = client.api_format
    state.base_url = client.base_url
    state.last_checked_at = now
    state.service_reachable = bool(health.get("status_code")) and int(health.get("status_code") or 0) >= 200
    state.model_ready = bool(health.get("ok", False))
    state.available_models = [str(item) for item in list(health.get("available_models") or []) if str(item).strip()]
    state.reason = str(health.get("reason") or "").strip()

    if state.model_ready:
        state.status = "ready"
        state.last_error = ""
        state.completed_at = now
        return

    if state.status == "pulling" and state.reason == "model_not_available":
        return

    if state.reason == "model_not_available":
        state.status = "idle"
        return

    if state.reason:
        state.status = "error"
        state.last_error = state.reason
        state.completed_at = now


def _update_local_model_state(**updates: Any) -> None:
    _ensure_local_model_state()
    for key, value in updates.items():
        setattr(_local_model_state, key, value)


def get_local_model_state() -> dict[str, Any]:
    _ensure_local_model_state()
    return asdict(_local_model_state)


def _missing_model_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "model not found" in text or "model_not_available" in text


async def _schedule_background_pull(reason: str) -> dict[str, Any]:
    global _local_model_pull_task
    client = get_local_client()
    _ensure_local_model_state(client)
    if client.api_format != "ollama" or not bool(getattr(settings, "LOCAL_LLM_AUTO_PULL_ENABLED", True)):
        return get_local_model_state()

    async with _local_model_pull_lock:
        if _local_model_pull_task is not None and not _local_model_pull_task.done():
            return get_local_model_state()

        now = time.time()
        _update_local_model_state(
            status="pulling",
            reason="model_not_available",
            last_error="",
            started_at=now,
            completed_at=0.0,
        )
        logger.info("Local LLM auto-pull scheduled for model=%s reason=%s", client.model, reason)
        _local_model_pull_task = asyncio.create_task(_pull_missing_model(client, reason))
        _local_model_pull_task.add_done_callback(_clear_pull_task)
    return get_local_model_state()


def _clear_pull_task(task: asyncio.Task[Any]) -> None:
    global _local_model_pull_task
    if _local_model_pull_task is task:
        _local_model_pull_task = None
    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("Local LLM auto-pull task cancelled")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Local LLM auto-pull task failed: %s", exc)


async def _pull_missing_model(client: LocalLLMClient, reason: str) -> None:
    timeout_seconds = max(30.0, float(getattr(settings, "LOCAL_LLM_PULL_TIMEOUT_SECONDS", 1800.0) or 1800.0))
    try:
        pull_model = _resolve_ollama_model_name(client.model)
        async with httpx.AsyncClient(timeout=timeout_seconds) as http_client:
            resp = await http_client.post(
                f"{client.base_url}/api/pull",
                json={"model": pull_model, "stream": False},
            )
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(f"pull_http_{resp.status_code}:{resp.text[:260]}")
        health = await client.health()
        if bool(health.get("ok", False)):
            _update_local_model_state(
                status="ready",
                reason="",
                last_error="",
                completed_at=time.time(),
            )
            logger.info("Local LLM auto-pull complete for model=%s reason=%s", client.model, reason)
            return
        raise RuntimeError(str(health.get("reason") or "model_not_available_after_pull"))
    except Exception as exc:
        _update_local_model_state(
            status="error",
            last_error=str(exc),
            reason=str(exc),
            completed_at=time.time(),
        )
        logger.warning("Local LLM auto-pull failed for model=%s reason=%s error=%s", client.model, reason, exc)


async def ensure_model_provisioning(reason: str = "startup") -> dict[str, Any]:
    client = get_local_client()
    health = await client.health()
    if (
        client.api_format == "ollama"
        and str(settings.LLM_BACKEND or "").strip().lower() == "local"
        and bool(getattr(settings, "LOCAL_LLM_AUTO_PULL_ENABLED", True))
        and str(health.get("reason") or "") == "model_not_available"
    ):
        await _schedule_background_pull(reason)
    return get_local_model_state()


async def wait_for_active_pull(timeout: Optional[float] = None) -> None:
    task = _local_model_pull_task
    if task is None:
        return
    if timeout is None:
        await asyncio.shield(task)
        return
    await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def get_local_client() -> LocalLLMClient:
    global _local_client, _local_client_fingerprint
    fp = _fingerprint()
    if _local_client is None or _local_client_fingerprint != fp:
        _local_client = LocalLLMClient(
            base_url=str(settings.LOCAL_LLM_BASE_URL or "").strip(),
            model=str(settings.LOCAL_LLM_MODEL or "").strip(),
            api_format=str(settings.LOCAL_LLM_API_FORMAT or "ollama").strip(),
            timeout_seconds=float(settings.LOCAL_LLM_TIMEOUT_SECONDS or 90.0),
        )
        _local_client_fingerprint = fp
        _reset_local_model_state(_local_client)
    return _local_client


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("timeout", "timed out", "connection", "temporar", "503", "504", "502"))


async def generate_with_retry(
    *,
    contents: Any,
    config: Any,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> LocalLLMResponse:
    retries = max(1, int(max_retries))
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            client = get_local_client()
            return await client.generate(contents=contents, config=config, model=model)
        except Exception as exc:
            last_exc = exc
            if _missing_model_error(exc):
                await _schedule_background_pull("generation")
            if attempt < retries - 1 and _is_transient_error(exc):
                wait_s = (attempt + 1) * 1.5
                logger.warning(
                    "Local LLM transient error (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    retries,
                    exc,
                    wait_s,
                )
                await asyncio.sleep(wait_s)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Local LLM generation failed without exception")
