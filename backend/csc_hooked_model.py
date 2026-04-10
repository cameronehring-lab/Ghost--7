"""
Diagnostics-only hooked local model for CSC irreducibility assays.

This backend is intentionally separate from Ghost's normal generation path.
It lazy-loads a tiny local transformer and applies additive residual steering
through forward hooks on a bounded mid-layer window.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from config import settings  # type: ignore

logger = logging.getLogger("omega.csc_hooked_model")


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


def _normalize_device(raw: Any) -> str:
    value = str(raw or "cpu").strip().lower()
    if value in {"cpu", "mps", "cuda"}:
        return value
    return "cpu"


def _apply_residual_to_output(output: Any, residual: Any) -> Any:
    if isinstance(output, tuple):
        if not output:
            return output
        hidden = output[0]
        return (hidden + residual.to(dtype=hidden.dtype), *output[1:])
    if output is None:
        return output
    return output + residual.to(dtype=output.dtype)


@dataclass
class HookedGenerationResult:
    text: str
    model_id: str
    device: str
    seed: int
    temperature: float
    max_new_tokens: int
    n_layers: int
    hidden_size: int
    target_layers: list[int]
    activation_steering_supported: bool


class CscHookedModelBackend:
    def __init__(self, *, model_id: str, device: str):
        self.model_id = str(model_id or "").strip()
        self.device = _normalize_device(device)
        self._runtime: Optional[tuple[Any, Any, Any]] = None
        self._tokenizer: Any = None
        self._model: Any = None
        self._layers: list[Any] = []
        self._hidden_size: int = 0
        self._n_layers: int = 0
        self._layer_window: tuple[int, int] = (0, 0)
        self._model_type: str = ""
        self._last_error: str = ""

    @property
    def hidden_size(self) -> int:
        return int(self._hidden_size or 0)

    @property
    def n_layers(self) -> int:
        return int(self._n_layers or 0)

    @property
    def layer_window(self) -> tuple[int, int]:
        return (int(self._layer_window[0]), int(self._layer_window[1]))

    def _import_runtime(self) -> tuple[Any, Any, Any]:
        if self._runtime is None:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            self._runtime = (torch, AutoModelForCausalLM, AutoTokenizer)
        return self._runtime

    def _resolve_layers(self, model: Any) -> list[Any]:
        config = getattr(model, "config", None)
        model_type = str(getattr(config, "model_type", "") or "").strip().lower()
        if not model_type.startswith("qwen"):
            raise RuntimeError(
                "unsupported_csc_hooked_architecture:"
                f"{model_type or 'unknown'} (expected Qwen causal LM family)"
            )

        base_model = getattr(model, "model", None)
        layers = getattr(base_model, "layers", None)
        if layers is None:
            raise RuntimeError("unsupported_csc_hooked_architecture:model.model.layers_missing")

        resolved = list(layers)
        if not resolved:
            raise RuntimeError("unsupported_csc_hooked_architecture:no_transformer_layers")

        self._model_type = model_type
        return resolved

    def _infer_hidden_size(self, model: Any, layers: list[Any]) -> int:
        config = getattr(model, "config", None)
        hidden_size = int(getattr(config, "hidden_size", 0) or 0)
        if hidden_size > 0:
            return hidden_size

        first = layers[0]
        layernorm = getattr(first, "input_layernorm", None)
        weight = getattr(layernorm, "weight", None)
        shape = getattr(weight, "shape", None)
        if shape and len(shape) >= 1:
            return int(shape[0])

        raise RuntimeError("unsupported_csc_hooked_architecture:hidden_size_unavailable")

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None and self._layers:
            return

        if not self.model_id:
            raise RuntimeError("CSC hooked backend missing CSC_HOOKED_MODEL_ID")

        torch, auto_model_cls, auto_tokenizer_cls = self._import_runtime()
        try:
            tokenizer = auto_tokenizer_cls.from_pretrained(self.model_id, trust_remote_code=False)
            model = auto_model_cls.from_pretrained(self.model_id, trust_remote_code=False)
            model.eval()
            if self.device != "cpu":
                model.to(self.device)
            layers = self._resolve_layers(model)
            hidden_size = self._infer_hidden_size(model, layers)
            if getattr(tokenizer, "pad_token_id", None) is None and getattr(tokenizer, "eos_token", None) is not None:
                tokenizer.pad_token = tokenizer.eos_token

            n_layers = len(layers)
            start = max(0, int(math.floor(0.4 * n_layers)))
            end = max(start, int(math.floor(0.7 * n_layers)))

            self._tokenizer = tokenizer
            self._model = model
            self._layers = layers
            self._hidden_size = int(hidden_size)
            self._n_layers = int(n_layers)
            self._layer_window = (int(start), int(end))
            self._last_error = ""
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def health(self) -> dict[str, Any]:
        try:
            self._ensure_loaded()
            return {
                "ok": True,
                "model_id": self.model_id,
                "device": self.device,
                "model_type": self._model_type,
                "n_layers": self.n_layers,
                "hidden_size": self.hidden_size,
                "layer_window": [self.layer_window[0], self.layer_window[1]],
                "activation_steering_supported": True,
            }
        except Exception as exc:
            return {
                "ok": False,
                "model_id": self.model_id,
                "device": self.device,
                "reason": str(exc),
                "activation_steering_supported": False,
            }

    def get_activation_handle(self) -> ActivationHandle:
        health = self.health()
        if not bool(health.get("ok", False)):
            return ActivationHandle(
                backend="hooked_local",
                model=self.model_id,
                api_format="transformers",
                activation_steering_supported=False,
                reason=str(health.get("reason") or "hooked_backend_unavailable"),
                n_layers=int(health.get("n_layers", 0) or 0),
                hidden_size=int(health.get("hidden_size", 0) or 0),
                target_layers=tuple(health.get("layer_window", [0, 0])),
            )

        return ActivationHandle(
            backend="hooked_local",
            model=self.model_id,
            api_format="transformers",
            activation_steering_supported=True,
            reason="hooked_local_ready",
            n_layers=self.n_layers,
            hidden_size=self.hidden_size,
            target_layers=self.layer_window,
        )

    def generate(
        self,
        *,
        prompt: str,
        steering_vector: Optional[np.ndarray],
        seed: int,
        temperature: float,
        max_new_tokens: int,
    ) -> HookedGenerationResult:
        self._ensure_loaded()
        torch, _, _ = self._import_runtime()
        tokenizer = self._tokenizer
        model = self._model
        layers = self._layers
        start, end = self.layer_window

        encoded = tokenizer(str(prompt or ""), return_tensors="pt")
        model_device = next(model.parameters()).device
        encoded = {key: value.to(model_device) for key, value in dict(encoded).items()}
        input_len = int(encoded["input_ids"].shape[1])

        hook_handles: list[Any] = []
        try:
            if steering_vector is not None:
                vector = np.asarray(steering_vector, dtype=np.float32).reshape(-1)
                if len(vector) != self.hidden_size:
                    raise RuntimeError(
                        "invalid_steering_vector_dim:"
                        f"expected={self.hidden_size} actual={len(vector)}"
                    )
                residual = torch.tensor(
                    vector,
                    dtype=next(model.parameters()).dtype,
                    device=model_device,
                ).view(1, 1, -1)

                def _hook(_module: Any, _inputs: Any, output: Any) -> Any:
                    return _apply_residual_to_output(output, residual)

                for idx in range(start, end + 1):
                    hook_handles.append(layers[idx].register_forward_hook(_hook))

            do_sample = float(temperature) > 0.0
            if do_sample:
                torch.manual_seed(int(seed))
                if hasattr(torch, "cuda") and callable(getattr(torch.cuda, "is_available", None)) and torch.cuda.is_available():
                    try:
                        torch.cuda.manual_seed_all(int(seed))
                    except Exception:
                        pass
            generate_kwargs = {
                **encoded,
                "max_new_tokens": max(1, int(max_new_tokens)),
                "do_sample": do_sample,
                "temperature": max(0.0, float(temperature)),
                "pad_token_id": getattr(tokenizer, "pad_token_id", None) or getattr(tokenizer, "eos_token_id", None),
                "eos_token_id": getattr(tokenizer, "eos_token_id", None),
                "use_cache": True,
            }
            with torch.no_grad():
                output_ids = model.generate(**generate_kwargs)
            generated = output_ids[0, input_len:]
            text = str(tokenizer.decode(generated, skip_special_tokens=True) or "").strip()
        finally:
            for handle in hook_handles:
                try:
                    handle.remove()
                except Exception:
                    pass

        return HookedGenerationResult(
            text=text,
            model_id=self.model_id,
            device=self.device,
            seed=int(seed),
            temperature=float(temperature),
            max_new_tokens=max(1, int(max_new_tokens)),
            n_layers=self.n_layers,
            hidden_size=self.hidden_size,
            target_layers=[start, end],
            activation_steering_supported=True,
        )


_backend: Optional[CscHookedModelBackend] = None
_backend_fp: str = ""


def _fingerprint() -> str:
    return "|".join(
        [
            str(getattr(settings, "CSC_HOOKED_MODEL_ID", "") or ""),
            str(getattr(settings, "CSC_HOOKED_DEVICE", "cpu") or "cpu"),
        ]
    )


def get_csc_hooked_backend() -> CscHookedModelBackend:
    global _backend, _backend_fp
    fp = _fingerprint()
    if _backend is None or _backend_fp != fp:
        _backend = CscHookedModelBackend(
            model_id=str(getattr(settings, "CSC_HOOKED_MODEL_ID", "") or ""),
            device=str(getattr(settings, "CSC_HOOKED_DEVICE", "cpu") or "cpu"),
        )
        _backend_fp = fp
    return _backend
