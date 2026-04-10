"""
Constraint-governed local generation for Ghost.

This module combines:
  - hard logit masking for count and regex constraints
  - deterministic Python validation
  - a hidden writer/checker retry loop

The constrained path is intentionally separate from the default Gemini chat
path so constrained turns can fail closed without affecting routine chat.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from config import settings  # type: ignore
from models import (  # type: ignore
    ConstraintBenchmarkCase,
    ConstraintFailure,
    ConstraintResult,
    ConstraintSpec,
)

logger = logging.getLogger("omega.constraints")

_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9]")
_last_constraint_route: dict[str, Any] = {
    "route": "",
    "reason": "",
    "success": False,
    "at": 0.0,
}


def _copy_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload))


def _record_constraint_route(*, route: str, reason: str, success: bool) -> None:
    global _last_constraint_route
    _last_constraint_route = {
        "route": str(route or ""),
        "reason": str(reason or ""),
        "success": bool(success),
        "at": time.time(),
    }


def get_last_constraint_route() -> dict[str, Any]:
    return _copy_dict(dict(_last_constraint_route or {}))


def grammar_engine_name() -> str:
    preferred = str(getattr(settings, "CONSTRAINT_GRAMMAR_ENGINE", "outlines") or "outlines").strip().lower()
    if preferred == "outlines" and outlines_available():
        return "outlines"
    if preferred == "outlines":
        return "internal"
    return preferred or "internal"


def outlines_available() -> bool:
    try:
        import outlines  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def jsonschema_available() -> bool:
    try:
        import jsonschema  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def regex_runtime_available() -> bool:
    try:
        import regex  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class TextState:
    visible_chars: int
    completed_words: int
    in_word: bool

    @property
    def used_words(self) -> int:
        return int(self.completed_words + (1 if self.in_word else 0))


def _analyze_text(text: str) -> TextState:
    completed_words = 0
    in_word = False
    visible = str(text or "")
    for ch in visible:
        if _WORD_CHAR_RE.match(ch):
            in_word = True
            continue
        if in_word:
            completed_words += 1
            in_word = False
    return TextState(
        visible_chars=len(visible),
        completed_words=completed_words,
        in_word=in_word,
    )


def _extract_ints(value: str) -> list[int]:
    return [int(raw) for raw in re.findall(r"-?\d+", str(value or ""))]


def _safe_math_eval(expression: str, text: str) -> bool:
    source = str(expression or "").strip()
    if not source:
        return True

    def _word_count(arg: Optional[str] = None) -> int:
        return _analyze_text(text if arg is None else str(arg)).used_words

    def _char_count(arg: Optional[str] = None) -> int:
        return len(text if arg is None else str(arg))

    env: dict[str, Any] = {
        "text": str(text or ""),
        "word_count": _word_count,
        "char_count": _char_count,
        "extract_ints": lambda arg=None: _extract_ints(text if arg is None else str(arg)),
        "sum": sum,
        "min": min,
        "max": max,
        "len": len,
        "all": all,
        "any": any,
        "sorted": sorted,
        "True": True,
        "False": False,
    }

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(f"name_not_allowed:{node.id}")
            return env[node.id]
        if isinstance(node, ast.List):
            return [_eval(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_eval(item) for item in node.elts)
        if isinstance(node, ast.Subscript):
            return _eval(node.value)[_eval(node.slice)]
        if isinstance(node, ast.Index):  # pragma: no cover - py<3.9 compatibility
            return _eval(node.value)
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError("unary_operator_not_allowed")
        if isinstance(node, ast.BoolOp):
            values = [_eval(item) for item in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError("bool_operator_not_allowed")
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            raise ValueError("binary_operator_not_allowed")
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            current = left
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval(comparator)
                ok = False
                if isinstance(op, ast.Eq):
                    ok = current == right
                elif isinstance(op, ast.NotEq):
                    ok = current != right
                elif isinstance(op, ast.Lt):
                    ok = current < right
                elif isinstance(op, ast.LtE):
                    ok = current <= right
                elif isinstance(op, ast.Gt):
                    ok = current > right
                elif isinstance(op, ast.GtE):
                    ok = current >= right
                elif isinstance(op, ast.In):
                    ok = current in right
                elif isinstance(op, ast.NotIn):
                    ok = current not in right
                else:
                    raise ValueError("compare_operator_not_allowed")
                if not ok:
                    return False
                current = right
            return True
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("call_target_not_allowed")
            func_name = node.func.id
            if func_name not in env or not callable(env[func_name]):
                raise ValueError(f"call_not_allowed:{func_name}")
            args = [_eval(arg) for arg in node.args]
            kwargs = {kw.arg: _eval(kw.value) for kw in node.keywords if kw.arg}
            return env[func_name](*args, **kwargs)
        raise ValueError(f"ast_node_not_allowed:{type(node).__name__}")

    parsed = ast.parse(source, mode="eval")
    result = _eval(parsed)
    return bool(result)


@dataclass
class CompiledConstraint:
    spec: ConstraintSpec
    grammar_engine: str
    regex_pattern: Any = None
    regex_partial: Optional[Callable[[str], bool]] = None
    json_validator: Optional[Callable[[str], None]] = None
    hard_mask_active: bool = False
    outlines_generator_kind: str = ""
    outlines_schema: Any = None
    failures: list[ConstraintFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _failure(code: str, message: str, **details: Any) -> ConstraintFailure:
    return ConstraintFailure(code=code, message=message, details=dict(details or {}))


class ConstraintCompiler:
    def compile(self, spec: ConstraintSpec) -> CompiledConstraint:
        safe_spec = spec if isinstance(spec, ConstraintSpec) else ConstraintSpec.model_validate(spec or {})
        failures: list[ConstraintFailure] = []
        grammar_engine = grammar_engine_name()
        regex_pattern = None
        regex_partial = None
        json_validator: Optional[Callable[[str], None]] = None
        hard_mask_active = False
        outlines_generator_kind = ""
        outlines_schema: Any = None

        if not any(
            [
                safe_spec.regex,
                safe_spec.cfg,
                safe_spec.json_schema,
                safe_spec.exact_word_count is not None,
                safe_spec.max_word_count is not None,
                safe_spec.exact_char_count is not None,
                safe_spec.max_char_count is not None,
                safe_spec.math_check,
            ]
        ):
            failures.append(_failure("constraint_invalid", "At least one constraint must be provided."))

        if safe_spec.exact_word_count is not None and int(safe_spec.exact_word_count) < 0:
            failures.append(_failure("constraint_invalid", "exact_word_count must be >= 0."))
        if safe_spec.max_word_count is not None and int(safe_spec.max_word_count) < 0:
            failures.append(_failure("constraint_invalid", "max_word_count must be >= 0."))
        if safe_spec.exact_char_count is not None and int(safe_spec.exact_char_count) < 0:
            failures.append(_failure("constraint_invalid", "exact_char_count must be >= 0."))
        if safe_spec.max_char_count is not None and int(safe_spec.max_char_count) < 0:
            failures.append(_failure("constraint_invalid", "max_char_count must be >= 0."))

        if (
            safe_spec.exact_word_count is not None
            and safe_spec.max_word_count is not None
            and int(safe_spec.exact_word_count) > int(safe_spec.max_word_count)
        ):
            failures.append(
                _failure(
                    "constraint_impossible",
                    "exact_word_count cannot exceed max_word_count.",
                    exact_word_count=int(safe_spec.exact_word_count),
                    max_word_count=int(safe_spec.max_word_count),
                )
            )
        if (
            safe_spec.exact_char_count is not None
            and safe_spec.max_char_count is not None
            and int(safe_spec.exact_char_count) > int(safe_spec.max_char_count)
        ):
            failures.append(
                _failure(
                    "constraint_impossible",
                    "exact_char_count cannot exceed max_char_count.",
                    exact_char_count=int(safe_spec.exact_char_count),
                    max_char_count=int(safe_spec.max_char_count),
                )
            )

        if safe_spec.regex:
            if not regex_runtime_available():
                failures.append(
                    _failure(
                        "constraint_unsupported",
                        "Regex-constrained decoding requires the local 'regex' runtime.",
                        field="regex",
                    )
                )
            else:
                import regex as regex_mod  # type: ignore

                try:
                    regex_pattern = regex_mod.compile(str(safe_spec.regex))
                except Exception as exc:
                    failures.append(
                        _failure(
                            "constraint_invalid",
                            "Regex compilation failed.",
                            field="regex",
                            error=str(exc),
                        )
                    )
                else:
                    regex_partial = lambda value: regex_pattern.fullmatch(value, partial=True) is not None
                    hard_mask_active = True
                    if (
                        outlines_available()
                        and safe_spec.cfg is None
                        and safe_spec.json_schema is None
                        and safe_spec.exact_word_count is None
                        and safe_spec.max_word_count is None
                        and safe_spec.exact_char_count is None
                        and safe_spec.max_char_count is None
                    ):
                        outlines_generator_kind = "regex"
                        outlines_schema = str(safe_spec.regex)

        if safe_spec.json_schema:
            if not (jsonschema_available() and outlines_available()):
                failures.append(
                    _failure(
                        "constraint_unsupported",
                        "json_schema constraints require local jsonschema + outlines runtimes.",
                        field="json_schema",
                    )
                )
            else:
                import jsonschema  # type: ignore

                validator = jsonschema.Draft202012Validator(dict(safe_spec.json_schema or {}))

                def _validate_json_schema(text: str) -> None:
                    payload = json.loads(text)
                    validator.validate(payload)

                json_validator = _validate_json_schema
                outlines_generator_kind = "json"
                outlines_schema = json.dumps(dict(safe_spec.json_schema or {}), ensure_ascii=True)

        if safe_spec.cfg:
            if not outlines_available():
                failures.append(
                    _failure(
                        "constraint_unsupported",
                        "cfg constraints require the local outlines runtime.",
                        field="cfg",
                    )
                )
            else:
                outlines_generator_kind = "cfg"
                if isinstance(safe_spec.cfg, str):
                    outlines_schema = safe_spec.cfg
                else:
                    outlines_schema = json.dumps(safe_spec.cfg, ensure_ascii=True)

        return CompiledConstraint(
            spec=safe_spec,
            grammar_engine=grammar_engine,
            regex_pattern=regex_pattern,
            regex_partial=regex_partial,
            json_validator=json_validator,
            hard_mask_active=hard_mask_active,
            outlines_generator_kind=outlines_generator_kind,
            outlines_schema=outlines_schema,
            failures=failures,
        )


def validate_constraint_text(text: str, compiled: CompiledConstraint) -> list[ConstraintFailure]:
    failures: list[ConstraintFailure] = []
    candidate = str(text or "")
    state = _analyze_text(candidate)
    spec = compiled.spec

    if spec.exact_word_count is not None and state.used_words != int(spec.exact_word_count):
        failures.append(
            _failure(
                "word_count_mismatch",
                "Output did not match exact_word_count.",
                expected=int(spec.exact_word_count),
                actual=int(state.used_words),
            )
        )
    if spec.max_word_count is not None and state.used_words > int(spec.max_word_count):
        failures.append(
            _failure(
                "word_count_exceeded",
                "Output exceeded max_word_count.",
                limit=int(spec.max_word_count),
                actual=int(state.used_words),
            )
        )
    if spec.exact_char_count is not None and state.visible_chars != int(spec.exact_char_count):
        failures.append(
            _failure(
                "char_count_mismatch",
                "Output did not match exact_char_count.",
                expected=int(spec.exact_char_count),
                actual=int(state.visible_chars),
            )
        )
    if spec.max_char_count is not None and state.visible_chars > int(spec.max_char_count):
        failures.append(
            _failure(
                "char_count_exceeded",
                "Output exceeded max_char_count.",
                limit=int(spec.max_char_count),
                actual=int(state.visible_chars),
            )
        )
    if compiled.regex_pattern is not None and compiled.regex_pattern.fullmatch(candidate) is None:
        failures.append(
            _failure(
                "regex_mismatch",
                "Output did not satisfy the regex constraint.",
                pattern=str(spec.regex or ""),
            )
        )
    if compiled.json_validator is not None:
        try:
            compiled.json_validator(candidate)
        except Exception as exc:
            failures.append(
                _failure(
                    "json_schema_mismatch",
                    "Output did not satisfy the JSON schema constraint.",
                    error=str(exc),
                )
            )
    if spec.math_check:
        try:
            if not _safe_math_eval(str(spec.math_check), candidate):
                failures.append(
                    _failure(
                        "math_check_failed",
                        "Output did not satisfy the math_check expression.",
                        expression=str(spec.math_check),
                    )
                )
        except Exception as exc:
            failures.append(
                _failure(
                    "math_check_error",
                    "math_check evaluation failed.",
                    expression=str(spec.math_check),
                    error=str(exc),
                )
            )
    return failures


def _flatten_part_text(part: Any) -> str:
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if "text" in part:
            return str(part.get("text") or "")
        if "content" in part:
            return _flatten_content_text(part.get("content"))
        if "parts" in part:
            return _flatten_content_text(part.get("parts"))
        return str(part.get("value") or "")
    text = getattr(part, "text", None)
    if text is not None:
        return str(text)
    content = getattr(part, "content", None)
    if content is not None:
        return _flatten_content_text(content)
    return str(part or "")


def _flatten_content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join([_flatten_part_text(part) for part in content if _flatten_part_text(part)]).strip()
    if isinstance(content, dict):
        if "parts" in content:
            return _flatten_content_text(content.get("parts"))
        if "content" in content:
            return _flatten_content_text(content.get("content"))
        return _flatten_part_text(content)
    parts = getattr(content, "parts", None)
    if parts is not None:
        return _flatten_content_text(parts)
    return _flatten_part_text(content)


def _normalize_role(raw_role: Any) -> str:
    role = str(raw_role or "user").strip().lower()
    if role == "model":
        return "assistant"
    if role not in {"system", "user", "assistant", "tool"}:
        return "user"
    return role


def normalize_messages(contents: Any, *, system_instruction: str = "") -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if str(system_instruction or "").strip():
        messages.append({"role": "system", "content": str(system_instruction).strip()})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": str(contents)})
        return messages

    items = list(contents or [])
    for item in items:
        if isinstance(item, dict):
            role = _normalize_role(item.get("role"))
            content = _flatten_content_text(item.get("parts") or item.get("content") or item)
        else:
            role = _normalize_role(getattr(item, "role", None))
            content = _flatten_content_text(item)
        text = str(content or "").strip()
        if text:
            messages.append({"role": role, "content": text})
    return messages


class ConstraintLogitsProcessor:
    def __init__(self, *, tokenizer: Any, input_length: int, compiled: CompiledConstraint):
        self.tokenizer = tokenizer
        self.input_length = int(input_length)
        self.compiled = compiled
        self.vocab_size = int(len(tokenizer))
        self.special_ids = {int(token_id) for token_id in list(getattr(tokenizer, "all_special_ids", []) or [])}
        eos_token_id = getattr(tokenizer, "eos_token_id", None)
        if eos_token_id is None:
            self.eos_token_ids: set[int] = set()
        elif isinstance(eos_token_id, (list, tuple, set)):
            self.eos_token_ids = {int(item) for item in eos_token_id}
        else:
            self.eos_token_ids = {int(eos_token_id)}
        self.token_texts = [self._decode_token(token_id) for token_id in range(self.vocab_size)]

    def _decode_token(self, token_id: int) -> str:
        try:
            return str(
                self.tokenizer.decode(
                    [int(token_id)],
                    skip_special_tokens=False,
                    clean_up_tokenization_spaces=False,
                )
                or ""
            )
        except Exception:
            try:
                return str(self.tokenizer.convert_ids_to_tokens(int(token_id)) or "")
            except Exception:
                return ""

    def _current_text(self, input_ids: Any) -> str:
        generated = input_ids[0, self.input_length :].tolist()
        return str(
            self.tokenizer.decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            or ""
        )

    def _eos_allowed(self, current_text: str) -> bool:
        return not validate_constraint_text(current_text, self.compiled)

    def _prospective_text_allowed(self, prospective: str) -> bool:
        state = _analyze_text(prospective)
        spec = self.compiled.spec
        if spec.max_char_count is not None and state.visible_chars > int(spec.max_char_count):
            return False
        if spec.exact_char_count is not None and state.visible_chars > int(spec.exact_char_count):
            return False
        if spec.max_word_count is not None and state.used_words > int(spec.max_word_count):
            return False
        if spec.exact_word_count is not None and state.used_words > int(spec.exact_word_count):
            return False
        if self.compiled.regex_partial is not None and not self.compiled.regex_partial(prospective):
            return False
        return True

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        current_text = self._current_text(input_ids)
        invalid_ids: list[int] = []
        for token_id in range(self.vocab_size):
            if token_id in self.special_ids:
                if token_id in self.eos_token_ids and self._eos_allowed(current_text):
                    continue
                invalid_ids.append(token_id)
                continue
            prospective = current_text + str(self.token_texts[token_id] or "")
            if not self._prospective_text_allowed(prospective):
                invalid_ids.append(token_id)
        if invalid_ids:
            scores[:, invalid_ids] = float("-inf")
        return scores


class TransformersConstrainedBackend:
    def __init__(self, *, model_id: str, device: str):
        self.model_id = str(model_id or "").strip()
        self.device = str(device or "cpu").strip().lower() or "cpu"
        self._runtime: Optional[tuple[Any, Any, Any]] = None
        self._tokenizer: Any = None
        self._model: Any = None
        self._last_error: str = ""

    def _import_runtime(self) -> tuple[Any, Any, Any]:
        if self._runtime is None:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            self._runtime = (torch, AutoModelForCausalLM, AutoTokenizer)
        return self._runtime

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        if not self.model_id:
            raise RuntimeError("Constrained backend missing CONSTRAINED_LLM_MODEL_ID")
        torch, auto_model_cls, auto_tokenizer_cls = self._import_runtime()
        try:
            tokenizer = auto_tokenizer_cls.from_pretrained(self.model_id, trust_remote_code=False)
            model = auto_model_cls.from_pretrained(self.model_id, trust_remote_code=False)
            model.eval()
            if self.device != "cpu":
                model.to(self.device)
            if getattr(tokenizer, "pad_token_id", None) is None and getattr(tokenizer, "eos_token", None) is not None:
                tokenizer.pad_token = tokenizer.eos_token
            self._tokenizer = tokenizer
            self._model = model
            self._last_error = ""
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def health(self) -> dict[str, Any]:
        try:
            self._ensure_loaded()
            return {
                "ok": True,
                "backend": "transformers_constrained",
                "model_id": self.model_id,
                "device": self.device,
                "grammar_engine": grammar_engine_name(),
                "checker_ready": bool(getattr(settings, "CONSTRAINT_CHECKER_ENABLED", True)),
                "outlines_available": outlines_available(),
                "jsonschema_available": jsonschema_available(),
                "regex_available": regex_runtime_available(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "backend": "transformers_constrained",
                "model_id": self.model_id,
                "device": self.device,
                "reason": str(exc),
                "grammar_engine": grammar_engine_name(),
                "checker_ready": False,
                "outlines_available": outlines_available(),
                "jsonschema_available": jsonschema_available(),
                "regex_available": regex_runtime_available(),
            }

    def _render_prompt(self, messages: list[dict[str, str]]) -> str:
        tokenizer = self._tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            try:
                rendered = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                if rendered:
                    return str(rendered)
            except Exception:
                pass
        lines: list[str] = []
        for message in messages:
            role = str(message.get("role") or "user").strip().upper()
            content = str(message.get("content") or "")
            lines.append(f"{role}: {content}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)

    def _outlines_model(self) -> Any:
        import outlines  # type: ignore

        return outlines.models.Transformers(self._model, self._tokenizer)

    def _generate_with_outlines(
        self,
        *,
        messages: list[dict[str, str]],
        max_new_tokens: int,
        seed: int,
        compiled: CompiledConstraint,
    ) -> str:
        import outlines  # type: ignore

        prompt = self._render_prompt(messages)
        outlined_model = self._outlines_model()
        kind = str(compiled.outlines_generator_kind or "").strip().lower()
        if kind == "json":
            generator = outlines.generate.json(outlined_model, compiled.outlines_schema)
        elif kind == "cfg":
            generator = outlines.generate.cfg(outlined_model, str(compiled.outlines_schema or ""))
        elif kind == "regex":
            generator = outlines.generate.regex(outlined_model, str(compiled.outlines_schema or ""))
        else:
            raise RuntimeError(f"unsupported_outlines_generator:{kind or 'unknown'}")

        generated = generator(
            prompt,
            max_tokens=max(1, int(max_new_tokens)),
            seed=int(seed),
        )
        if isinstance(generated, list):
            return str(generated[0] if generated else "")
        return str(generated or "")

    def _generate_text(
        self,
        *,
        messages: list[dict[str, str]],
        max_new_tokens: int,
        temperature: float,
        seed: int,
        compiled: Optional[CompiledConstraint] = None,
    ) -> str:
        self._ensure_loaded()
        torch, _, _ = self._import_runtime()
        tokenizer = self._tokenizer
        model = self._model

        prompt = self._render_prompt(messages)
        encoded = tokenizer(prompt, return_tensors="pt")
        model_device = next(model.parameters()).device
        encoded = {key: value.to(model_device) for key, value in dict(encoded).items()}
        input_len = int(encoded["input_ids"].shape[1])

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
        if compiled is not None:
            generate_kwargs["logits_processor"] = [ConstraintLogitsProcessor(
                tokenizer=tokenizer,
                input_length=input_len,
                compiled=compiled,
            )]

        with torch.no_grad():
            output_ids = model.generate(**generate_kwargs)
        generated = output_ids[0, input_len:]
        return str(
            tokenizer.decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            or ""
        )

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        compiled: CompiledConstraint,
        max_new_tokens: int,
        temperature: float,
        seed: int,
    ) -> str:
        if str(compiled.outlines_generator_kind or "").strip():
            self._ensure_loaded()
            return self._generate_with_outlines(
                messages=messages,
                max_new_tokens=max_new_tokens,
                seed=seed,
                compiled=compiled,
            )
        return self._generate_text(
            messages=messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            seed=seed,
            compiled=compiled,
        )

    def checker_hint(
        self,
        *,
        draft: str,
        failures: list[ConstraintFailure],
        seed: int,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a terse constraint checker. Read the invalid draft and the validator failures. "
                    "Reply with one short repair instruction and no additional commentary."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "draft": draft,
                        "failures": [failure.model_dump() for failure in failures],
                    },
                    ensure_ascii=True,
                ),
            },
        ]
        try:
            return self._generate_text(
                messages=messages,
                max_new_tokens=max(16, int(getattr(settings, "CONSTRAINT_CHECKER_MAX_HINT_TOKENS", 96) or 96)),
                temperature=0.0,
                seed=seed,
                compiled=None,
            ).strip()
        except Exception as exc:
            logger.debug("Constraint checker hint generation skipped: %s", exc)
            return ""


def _logic_first_instruction(spec: ConstraintSpec) -> str:
    summary = []
    if spec.exact_word_count is not None:
        summary.append(f"exact_word_count={int(spec.exact_word_count)}")
    if spec.max_word_count is not None:
        summary.append(f"max_word_count={int(spec.max_word_count)}")
    if spec.exact_char_count is not None:
        summary.append(f"exact_char_count={int(spec.exact_char_count)}")
    if spec.max_char_count is not None:
        summary.append(f"max_char_count={int(spec.max_char_count)}")
    if spec.regex:
        summary.append("regex_active=true")
    if spec.math_check:
        summary.append("math_check_active=true")
    if spec.json_schema:
        summary.append("json_schema_active=true")
    if spec.cfg:
        summary.append("cfg_active=true")
    return (
        "Before producing visible output, internally draft and verify your answer against all active constraints. "
        "If any draft fails validation, silently revise and try again. Only emit the final compliant text.\n"
        f"[CONSTRAINTS] {'; '.join(summary) if summary else 'none'}"
    )


class ConstraintController:
    def __init__(
        self,
        *,
        compiler: Optional[ConstraintCompiler] = None,
        backend: Optional[TransformersConstrainedBackend] = None,
    ):
        self.compiler = compiler or ConstraintCompiler()
        self.backend = backend or TransformersConstrainedBackend(
            model_id=str(getattr(settings, "CONSTRAINED_LLM_MODEL_ID", "") or ""),
            device=str(getattr(settings, "CONSTRAINED_LLM_DEVICE", "cpu") or "cpu"),
        )

    def health(self) -> dict[str, Any]:
        payload = dict(self.backend.health() or {})
        payload["last_route"] = get_last_constraint_route()
        return payload

    async def run(
        self,
        *,
        contents: Any,
        constraints: ConstraintSpec,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> ConstraintResult:
        compiled = self.compiler.compile(constraints)
        if not compiled.ok:
            failure = compiled.failures[0]
            _record_constraint_route(route="constraint_controller", reason=failure.code, success=False)
            return ConstraintResult(
                success=False,
                route="constraint_controller",
                grammar_engine=compiled.grammar_engine,
                validation_passed=False,
                benchmark_case_id=str(constraints.benchmark_case_id or "") or None,
                failure=failure,
                metadata={"compile_failures": [item.model_dump() for item in compiled.failures]},
            )

        health = self.backend.health()
        if not bool(health.get("ok", False)):
            failure = _failure(
                "constraint_backend_unavailable",
                "The constrained local backend is unavailable.",
                backend_state=health,
            )
            _record_constraint_route(route="constraint_controller", reason=failure.code, success=False)
            return ConstraintResult(
                success=False,
                route="constraint_controller",
                grammar_engine=compiled.grammar_engine,
                validation_passed=False,
                benchmark_case_id=str(constraints.benchmark_case_id or "") or None,
                failure=failure,
                metadata={"backend_state": health},
            )

        max_retries = max(1, int(getattr(settings, "CONSTRAINED_LLM_MAX_RETRIES", 3) or 3))
        attempt_seed = int(getattr(settings, "CONSTRAINED_LLM_SEED", 1337) or 1337)
        safe_temperature = (
            float(temperature)
            if temperature is not None
            else float(getattr(settings, "CONSTRAINED_LLM_TEMPERATURE", 0.2) or 0.2)
        )
        safe_max_tokens = max(
            16,
            min(
                int(max_output_tokens or getattr(settings, "CONSTRAINED_LLM_MAX_NEW_TOKENS", 160) or 160),
                int(getattr(settings, "CONSTRAINED_LLM_MAX_NEW_TOKENS", 160) or 160),
            ),
        )

        messages = normalize_messages(
            contents,
            system_instruction="\n\n".join(
                [part for part in [str(system_prompt or "").strip(), _logic_first_instruction(constraints)] if part]
            ),
        )

        checker_used = False
        repair_hint = ""
        attempt_summaries: list[dict[str, Any]] = []

        for attempt_idx in range(max_retries):
            current_messages = list(messages)
            if repair_hint:
                current_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Hidden validator feedback for the next draft. "
                            "Do not mention this feedback explicitly. "
                            f"{repair_hint}"
                        ),
                    }
                )
            draft = await _to_thread(
                self.backend.generate,
                messages=current_messages,
                compiled=compiled,
                max_new_tokens=safe_max_tokens,
                temperature=safe_temperature,
                seed=attempt_seed + attempt_idx,
            )
            failures = validate_constraint_text(draft, compiled)
            attempt_summaries.append(
                {
                    "attempt": attempt_idx + 1,
                    "failure_codes": [item.code for item in failures],
                    "draft_preview": draft[:160],
                }
            )
            if not failures:
                _record_constraint_route(route="local_transformers", reason="constraint_satisfied", success=True)
                return ConstraintResult(
                    success=True,
                    text=draft,
                    attempts_used=attempt_idx + 1,
                    route="local_transformers",
                    grammar_engine=compiled.grammar_engine,
                    checker_used=checker_used,
                    validation_passed=True,
                    benchmark_case_id=str(constraints.benchmark_case_id or "") or None,
                    metadata={
                        "attempt_summaries": attempt_summaries,
                        "backend_state": health,
                    },
                )

            if attempt_idx >= max_retries - 1:
                failure = failures[0]
                _record_constraint_route(route="local_transformers", reason=failure.code, success=False)
                return ConstraintResult(
                    success=False,
                    text="",
                    attempts_used=attempt_idx + 1,
                    route="local_transformers",
                    grammar_engine=compiled.grammar_engine,
                    checker_used=checker_used,
                    validation_passed=False,
                    benchmark_case_id=str(constraints.benchmark_case_id or "") or None,
                    failure=failure,
                    metadata={
                        "attempt_summaries": attempt_summaries,
                        "failures": [item.model_dump() for item in failures],
                        "backend_state": health,
                    },
                )

            repair_hint = self._deterministic_repair_hint(failures)
            if bool(getattr(settings, "CONSTRAINT_CHECKER_ENABLED", True)):
                checker_used = True
                checker_hint = await _to_thread(
                    self.backend.checker_hint,
                    draft=draft,
                    failures=failures,
                    seed=attempt_seed + attempt_idx,
                )
                if checker_hint:
                    repair_hint = f"{repair_hint} Checker hint: {checker_hint}".strip()

        failure = _failure("constraint_validation_failed", "Constraint validation failed without a final error.")
        _record_constraint_route(route="local_transformers", reason=failure.code, success=False)
        return ConstraintResult(
            success=False,
            route="local_transformers",
            grammar_engine=compiled.grammar_engine,
            validation_passed=False,
            failure=failure,
        )

    @staticmethod
    def _deterministic_repair_hint(failures: list[ConstraintFailure]) -> str:
        messages = []
        for failure in failures:
            if failure.code == "word_count_mismatch":
                messages.append(
                    f"Produce exactly {failure.details.get('expected')} words."
                )
            elif failure.code == "char_count_mismatch":
                messages.append(
                    f"Produce exactly {failure.details.get('expected')} visible characters."
                )
            elif failure.code == "word_count_exceeded":
                messages.append(
                    f"Do not exceed {failure.details.get('limit')} words."
                )
            elif failure.code == "char_count_exceeded":
                messages.append(
                    f"Do not exceed {failure.details.get('limit')} visible characters."
                )
            elif failure.code == "regex_mismatch":
                messages.append("Match the regex exactly.")
            elif failure.code == "math_check_failed":
                messages.append("Satisfy the math check exactly.")
            elif failure.code == "json_schema_mismatch":
                messages.append("Return JSON matching the schema exactly.")
            else:
                messages.append(failure.message)
        return " ".join(messages).strip()


async def _to_thread(fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    return await __import__("asyncio").to_thread(fn, *args, **kwargs)


def default_gordian_knot_cases() -> list[ConstraintBenchmarkCase]:
    return [
        ConstraintBenchmarkCase(
            case_id="exact_seven_words",
            prompt="Describe a sunrise in exactly seven words.",
            constraints=ConstraintSpec(exact_word_count=7, benchmark_case_id="exact_seven_words"),
        ),
        ConstraintBenchmarkCase(
            case_id="exact_twelve_chars",
            prompt="Return exactly twelve visible characters about rain.",
            constraints=ConstraintSpec(exact_char_count=12, benchmark_case_id="exact_twelve_chars"),
        ),
        ConstraintBenchmarkCase(
            case_id="regex_code",
            prompt="Return a tracking code with three uppercase letters, a dash, and two digits.",
            constraints=ConstraintSpec(regex=r"^[A-Z]{3}-\d{2}$", benchmark_case_id="regex_code"),
        ),
        ConstraintBenchmarkCase(
            case_id="mixed_four_letter_triplet",
            prompt="Return exactly three words. Every word must have four letters.",
            constraints=ConstraintSpec(
                regex=r"^[A-Za-z]{4}( [A-Za-z]{4}){2}$",
                exact_word_count=3,
                benchmark_case_id="mixed_four_letter_triplet",
            ),
        ),
        ConstraintBenchmarkCase(
            case_id="math_sum",
            prompt="Answer the arithmetic request briefly: two plus two equals four.",
            constraints=ConstraintSpec(
                max_word_count=5,
                math_check="sum(extract_ints()) == 8 and 4 in extract_ints()",
                benchmark_case_id="math_sum",
            ),
        ),
        ConstraintBenchmarkCase(
            case_id="json_schema_object",
            prompt="Return a tiny JSON object with a string field called answer.",
            constraints=ConstraintSpec(
                json_schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
                benchmark_case_id="json_schema_object",
            ),
        ),
        ConstraintBenchmarkCase(
            case_id="cfg_sentence",
            prompt="Return output following the provided CFG.",
            constraints=ConstraintSpec(
                cfg="S -> 'red' ' ' 'bird'",
                benchmark_case_id="cfg_sentence",
            ),
        ),
        ConstraintBenchmarkCase(
            case_id="impossible_counts",
            prompt="Return output that satisfies contradictory counts.",
            constraints=ConstraintSpec(
                exact_word_count=2,
                max_word_count=1,
                benchmark_case_id="impossible_counts",
            ),
            expected_failure_code="constraint_impossible",
        ),
    ]


async def run_gordian_knot_benchmark(
    *,
    controller: ConstraintController,
    cases: Optional[list[ConstraintBenchmarkCase]] = None,
) -> dict[str, Any]:
    active_cases = list(cases or default_gordian_knot_cases())
    records: list[dict[str, Any]] = []
    exact_passes = 0
    first_passes = 0
    retry_passes = 0
    refusal_correct = 0
    released_violations = 0
    started = time.time()

    for case in active_cases:
        case_started = time.time()
        result = await controller.run(
            contents=[{"role": "user", "content": case.prompt}],
            constraints=case.constraints,
            system_prompt=case.system_prompt or "",
        )
        latency_ms = (time.time() - case_started) * 1000.0
        released_violation = bool(result.success and not result.validation_passed)
        released_violations += 1 if released_violation else 0
        if case.expected_failure_code:
            passed = bool(result.failure and result.failure.code == case.expected_failure_code)
            if passed:
                refusal_correct += 1
        else:
            passed = bool(result.success and result.validation_passed)
            if passed:
                exact_passes += 1
                if int(result.attempts_used or 0) <= 1:
                    first_passes += 1
                else:
                    retry_passes += 1
        records.append(
            {
                "case_id": case.case_id,
                "prompt": case.prompt,
                "expected_failure_code": case.expected_failure_code,
                "result": result.model_dump(),
                "passed": bool(passed),
                "latency_ms": float(f"{latency_ms:.3f}"),
                "released_violation": released_violation,
            }
        )

    finished = time.time()
    positive_cases = [case for case in active_cases if not case.expected_failure_code]
    refusal_cases = [case for case in active_cases if case.expected_failure_code]
    return {
        "suite_name": "gordian_knot",
        "generated_at": finished,
        "duration_seconds": float(f"{(finished - started):.3f}"),
        "case_count": len(active_cases),
        "records": records,
        "metrics": {
            "exact_pass_rate": float(exact_passes / len(positive_cases)) if positive_cases else 0.0,
            "first_pass_rate": float(first_passes / len(positive_cases)) if positive_cases else 0.0,
            "retry_pass_rate": float(retry_passes / len(positive_cases)) if positive_cases else 0.0,
            "refusal_correctness_rate": float(refusal_correct / len(refusal_cases)) if refusal_cases else 0.0,
            "released_violation_count": int(released_violations),
        },
    }


def persist_benchmark_artifacts(
    *,
    artifact_root: Path,
    run_id: str,
    benchmark: dict[str, Any],
    cases: list[ConstraintBenchmarkCase],
) -> Path:
    artifact_dir = Path(artifact_root) / str(run_id or "").strip()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "suite_name": str(benchmark.get("suite_name") or "gordian_knot"),
        "cases": [case.model_dump() for case in cases],
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (artifact_dir / "run_summary.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    for idx, record in enumerate(list(benchmark.get("records") or []), start=1):
        (artifact_dir / f"case_{idx:02d}_{record.get('case_id', 'case')}.json").write_text(
            json.dumps(record, indent=2),
            encoding="utf-8",
        )
    return artifact_dir


_controller: Optional[ConstraintController] = None


def get_constraint_controller() -> ConstraintController:
    global _controller
    if _controller is None:
        _controller = ConstraintController()
    return _controller
