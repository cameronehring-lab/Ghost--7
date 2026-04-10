import unittest
from unittest.mock import AsyncMock, patch

import torch

import constrained_generation
import ghost_api
from models import ConstraintSpec


class _FakeTokenizer:
    pad_token_id = 0
    eos_token_id = 0
    eos_token = "<eos>"
    pad_token = "<pad>"
    all_special_ids = [0]

    def __init__(self):
        self._tokens = {
            0: "",
            1: "alpha",
            2: " beta",
            3: " gamma",
            4: "AB",
            5: "C",
            6: "-",
            7: "42",
        }

    def __len__(self):
        return len(self._tokens)

    def __call__(self, text, return_tensors="pt"):  # pylint: disable=unused-argument
        return {"input_ids": torch.tensor([[9, 9]], dtype=torch.long)}

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):  # pylint: disable=unused-argument
        return "\n".join([f"{m['role']}:{m['content']}" for m in messages])

    def decode(self, tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False):  # pylint: disable=unused-argument
        if hasattr(tokens, "tolist"):
            values = list(tokens.tolist())
        else:
            values = list(tokens)
        parts = []
        for value in values:
            if skip_special_tokens and int(value) in self.all_special_ids:
                continue
            parts.append(self._tokens.get(int(value), ""))
        return "".join(parts)

    def convert_ids_to_tokens(self, token_id):
        return self._tokens.get(int(token_id), "")


class _FakeModel:
    def __init__(self):
        self._param = torch.nn.Parameter(torch.zeros(1, dtype=torch.float32))
        self._preferred_ids = [1, 2, 3, 0]

    def eval(self):
        return self

    def to(self, _device):
        return self

    def parameters(self):
        yield self._param

    def generate(self, input_ids, **kwargs):
        logits_processors = list(kwargs.get("logits_processor") or [])
        current = input_ids
        for preferred_id in self._preferred_ids:
            scores = torch.full((1, 8), -10.0, dtype=torch.float32, device=current.device)
            scores[0, preferred_id] = 10.0
            for processor in logits_processors:
                scores = processor(current, scores)
            next_id = int(torch.argmax(scores, dim=-1)[0].item())
            current = torch.cat([current, torch.tensor([[next_id]], dtype=torch.long, device=current.device)], dim=1)
            if next_id == 0:
                break
        return current


class _FakeAutoTokenizer:
    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _FakeTokenizer()


class _FakeAutoModel:
    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _FakeModel()


class _StubBackend:
    def __init__(self, drafts):
        self._drafts = list(drafts)
        self.generate_calls = 0
        self.checker_calls = 0

    def health(self):
        return {
            "ok": True,
            "backend": "transformers_constrained",
            "grammar_engine": "internal",
            "checker_ready": True,
        }

    def generate(self, **kwargs):  # pylint: disable=unused-argument
        self.generate_calls += 1
        return self._drafts[min(self.generate_calls - 1, len(self._drafts) - 1)]

    def checker_hint(self, **kwargs):  # pylint: disable=unused-argument
        self.checker_calls += 1
        return "Shorten the response to satisfy the validator."


class ConstraintCompilerTests(unittest.TestCase):
    def test_compile_rejects_impossible_counts(self):
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(exact_word_count=3, max_word_count=2)
        )
        self.assertFalse(compiled.ok)
        self.assertEqual(compiled.failures[0].code, "constraint_impossible")

    def test_validate_constraint_text_checks_word_char_and_math(self):
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(exact_word_count=2, exact_char_count=5, math_check="sum(extract_ints()) == 4")
        )
        failures = constrained_generation.validate_constraint_text("2 2", compiled)
        codes = {item.code for item in failures}
        self.assertIn("char_count_mismatch", codes)
        self.assertNotIn("word_count_mismatch", codes)
        self.assertNotIn("math_check_failed", codes)

    def test_compile_regex_supports_partial_prefix_runtime(self):
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(regex=r"^[A-Z]{3}-\d{2}$")
        )
        self.assertTrue(compiled.ok)
        self.assertTrue(bool(compiled.regex_partial))
        self.assertTrue(compiled.regex_partial("ABC-4"))
        self.assertFalse(compiled.regex_partial("abc"))

    def test_compile_json_schema_enables_outlines_generation(self):
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(json_schema={"type": "object", "properties": {"answer": {"type": "string"}}})
        )
        self.assertTrue(compiled.ok)
        self.assertEqual(compiled.outlines_generator_kind, "json")

    def test_compile_cfg_enables_outlines_generation(self):
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(cfg="S -> 'red' ' ' 'bird'")
        )
        self.assertTrue(compiled.ok)
        self.assertEqual(compiled.outlines_generator_kind, "cfg")


class ConstrainedBackendTests(unittest.TestCase):
    def test_backend_masks_illegal_next_token_for_exact_word_count(self):
        backend = constrained_generation.TransformersConstrainedBackend(
            model_id="fake/model",
            device="cpu",
        )
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(exact_word_count=2)
        )
        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _FakeAutoModel, _FakeAutoTokenizer),
        ):
            text = backend.generate(
                messages=[{"role": "user", "content": "Say two words."}],
                compiled=compiled,
                max_new_tokens=4,
                temperature=0.0,
                seed=13,
            )
        self.assertEqual(text, "alpha beta")

    def test_backend_masks_regex_violation(self):
        tokenizer = _FakeTokenizer()
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(regex=r"^[A-Z]{3}-\d{2}$")
        )
        processor = constrained_generation.ConstraintLogitsProcessor(
            tokenizer=tokenizer,
            input_length=2,
            compiled=compiled,
        )
        input_ids = torch.tensor([[9, 9, 4, 5, 6]], dtype=torch.long)
        scores = torch.zeros((1, len(tokenizer)), dtype=torch.float32)
        scores[0, 3] = 10.0
        scores[0, 7] = 9.0
        masked = processor(input_ids, scores)
        self.assertEqual(float(masked[0, 3].item()), float("-inf"))
        self.assertGreater(float(masked[0, 7].item()), float("-inf"))

    def test_backend_uses_outlines_for_json_schema_generation(self):
        backend = constrained_generation.TransformersConstrainedBackend(
            model_id="fake/model",
            device="cpu",
        )
        compiled = constrained_generation.ConstraintCompiler().compile(
            ConstraintSpec(json_schema={"type": "object", "properties": {"answer": {"type": "string"}}})
        )

        class _Generator:
            def __call__(self, prompt, max_tokens=None, seed=None):  # pylint: disable=unused-argument
                return '{"answer":"ok"}'

        fake_outlines = type(
            "FakeOutlines",
            (),
            {
                "models": type("Models", (), {"Transformers": lambda self_model, model, tokenizer: ("wrapped", model, tokenizer)})(),
                "generate": type(
                    "Generate",
                    (),
                    {"json": lambda self_generate, model, schema: _Generator()},
                )(),
            },
        )()

        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _FakeAutoModel, _FakeAutoTokenizer),
        ), patch.dict("sys.modules", {"outlines": fake_outlines}):
            text = backend.generate(
                messages=[{"role": "user", "content": "Return json"}],
                compiled=compiled,
                max_new_tokens=32,
                temperature=0.0,
                seed=7,
            )
        self.assertEqual(text, '{"answer":"ok"}')


class ConstraintControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_retries_until_validator_passes(self):
        stub_backend = _StubBackend(["too many words here", "just right"])
        controller = constrained_generation.ConstraintController(
            compiler=constrained_generation.ConstraintCompiler(),
            backend=stub_backend,
        )
        with patch.object(constrained_generation.settings, "CONSTRAINT_CHECKER_ENABLED", True), patch.object(
            constrained_generation.settings, "CONSTRAINED_LLM_MAX_RETRIES", 3
        ):
            result = await controller.run(
                contents=[{"role": "user", "content": "Say two words."}],
                constraints=ConstraintSpec(exact_word_count=2),
                system_prompt="",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.text, "just right")
        self.assertEqual(result.attempts_used, 2)
        self.assertTrue(result.checker_used)
        self.assertEqual(stub_backend.generate_calls, 2)
        self.assertEqual(stub_backend.checker_calls, 1)


class GhostStreamConstraintTests(unittest.IsolatedAsyncioTestCase):
    async def test_constrained_turn_bypasses_gemini_retry_path(self):
        controller = type(
            "Controller",
            (),
            {
                "run": AsyncMock(
                    return_value=constrained_generation.ConstraintResult(
                        success=True,
                        text="alpha  beta",
                        attempts_used=1,
                        route="local_transformers",
                        grammar_engine="internal",
                        checker_used=False,
                        validation_passed=True,
                    )
                )
            },
        )()
        chunks = []
        with patch.object(ghost_api, "get_constraint_controller", return_value=controller), patch.object(
            ghost_api,
            "_generate_with_retry",
            new=AsyncMock(side_effect=AssertionError("Gemini path should not be used")),
        ), patch.object(
            ghost_api,
            "_external_reference_context",
            new=AsyncMock(return_value=""),
        ):
            async for chunk in ghost_api.ghost_stream(
                user_message="Say two words.",
                conversation_history=[],
                somatic={},
                monologues=[],
                constraints=ConstraintSpec(exact_word_count=2),
            ):
                chunks.append(chunk)
        event_names = [chunk.get("event") for chunk in chunks if isinstance(chunk, dict)]
        text_chunks = [chunk for chunk in chunks if isinstance(chunk, str)]
        self.assertIn("constraint_result", event_names)
        self.assertEqual("".join(text_chunks), "alpha  beta")


if __name__ == "__main__":
    unittest.main()
