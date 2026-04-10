import unittest
from unittest.mock import patch

import numpy as np
import torch

import csc_hooked_model


class _FakeHookHandle:
    def __init__(self, hooks, fn):
        self._hooks = hooks
        self._fn = fn

    def remove(self):
        if self._fn in self._hooks:
            self._hooks.remove(self._fn)


class _FakeLayer:
    def __init__(self):
        self._hooks = []
        self.input_layernorm = type(
            "LayerNorm",
            (),
            {"weight": torch.zeros(8)},
        )()

    def register_forward_hook(self, fn):
        self._hooks.append(fn)
        return _FakeHookHandle(self._hooks, fn)

    def forward(self, hidden):
        output = hidden
        for hook in list(self._hooks):
            output = hook(self, (), output)
        return output


class _FakeTokenizer:
    pad_token_id = 0
    eos_token_id = 3
    eos_token = "<eos>"
    pad_token = "<pad>"

    def __call__(self, text, return_tensors="pt"):  # pylint: disable=unused-argument
        return {"input_ids": torch.tensor([[10, 11]], dtype=torch.long)}

    def decode(self, tokens, skip_special_tokens=True):  # pylint: disable=unused-argument
        values = list(tokens.tolist())
        if 1 in values:
            return "steered path"
        if 2 in values:
            return "prompt only"
        return "empty"


class _FakeModel:
    def __init__(self, *, model_type="qwen2"):
        self.config = type("Config", (), {"model_type": model_type, "hidden_size": 8})()
        self.model = type("InnerModel", (), {"layers": [_FakeLayer() for _ in range(5)]})()
        self._param = torch.nn.Parameter(torch.zeros(1, dtype=torch.float32))

    def eval(self):
        return self

    def to(self, _device):
        return self

    def parameters(self):
        yield self._param

    def generate(self, input_ids, **kwargs):  # pylint: disable=unused-argument
        hidden = torch.zeros((1, 1, 8), dtype=torch.float32)
        for layer in self.model.layers:
            hidden = layer.forward(hidden)
        token = 1 if float(hidden.sum().item()) > 0.0 else 2
        generated = torch.tensor([[token]], dtype=torch.long)
        return torch.cat([input_ids, generated], dim=1)


class _NoGeneratorFakeModel(_FakeModel):
    def generate(self, input_ids, **kwargs):
        if "generator" in kwargs:
            raise AssertionError("generator kwarg should not be passed")
        return super().generate(input_ids, **kwargs)


class _FakeAutoTokenizer:
    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _FakeTokenizer()


class _FakeAutoModel:
    model_type = "qwen2"

    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _FakeModel()


class _NoGeneratorAutoModel:
    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _NoGeneratorFakeModel()


class _FakeBadAutoModel:
    @staticmethod
    def from_pretrained(*args, **kwargs):  # pylint: disable=unused-argument
        return _FakeModel(model_type="llama")


class CscHookedModelTests(unittest.TestCase):
    def test_lazy_load_happens_on_health(self):
        backend = csc_hooked_model.CscHookedModelBackend(
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            device="cpu",
        )
        self.assertIsNone(backend._model)  # pylint: disable=protected-access
        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _FakeAutoModel, _FakeAutoTokenizer),
        ):
            health = backend.health()
        self.assertTrue(health["ok"])
        self.assertIsNotNone(backend._model)  # pylint: disable=protected-access
        self.assertEqual(int(health["hidden_size"]), 8)

    def test_unsupported_architecture_hard_fails(self):
        backend = csc_hooked_model.CscHookedModelBackend(
            model_id="unsupported/model",
            device="cpu",
        )
        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _FakeBadAutoModel, _FakeAutoTokenizer),
        ):
            health = backend.health()
        self.assertFalse(health["ok"])
        self.assertIn("unsupported_csc_hooked_architecture", str(health["reason"]))

    def test_generate_changes_output_when_steering_vector_present(self):
        backend = csc_hooked_model.CscHookedModelBackend(
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            device="cpu",
        )
        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _FakeAutoModel, _FakeAutoTokenizer),
        ):
            baseline = backend.generate(
                prompt="state your condition",
                steering_vector=None,
                seed=13,
                temperature=0.0,
                max_new_tokens=8,
            )
            steered = backend.generate(
                prompt="state your condition",
                steering_vector=np.ones((8,), dtype=np.float32),
                seed=13,
                temperature=0.0,
                max_new_tokens=8,
            )
        self.assertEqual(baseline.text, "prompt only")
        self.assertEqual(steered.text, "steered path")
        self.assertEqual(steered.target_layers, [2, 3])

    def test_generate_sampling_path_does_not_pass_generator_kwarg(self):
        backend = csc_hooked_model.CscHookedModelBackend(
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            device="cpu",
        )
        with patch.object(
            backend,
            "_import_runtime",
            return_value=(torch, _NoGeneratorAutoModel, _FakeAutoTokenizer),
        ):
            result = backend.generate(
                prompt="state your condition",
                steering_vector=None,
                seed=13,
                temperature=0.7,
                max_new_tokens=8,
            )
        self.assertEqual(result.text, "prompt only")

    def test_apply_residual_to_tuple_output(self):
        hidden = torch.zeros((1, 1, 4), dtype=torch.float32)
        residual = torch.ones((1, 1, 4), dtype=torch.float32)
        output = csc_hooked_model._apply_residual_to_output((hidden, "meta"), residual)  # pylint: disable=protected-access
        self.assertEqual(output[1], "meta")
        self.assertTrue(torch.equal(output[0], torch.ones((1, 1, 4), dtype=torch.float32)))


if __name__ == "__main__":
    unittest.main()
