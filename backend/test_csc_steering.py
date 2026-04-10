import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import csc_hooked_model
import main


class _FakeHookedBackend:
    def __init__(self):
        self.calls: list[dict] = []

    def health(self):
        return {
            "ok": True,
            "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
            "device": "cpu",
            "model_type": "qwen2",
            "n_layers": 24,
            "hidden_size": 64,
            "layer_window": [9, 16],
            "activation_steering_supported": True,
        }

    def get_activation_handle(self):
        return csc_hooked_model.ActivationHandle(
            backend="hooked_local",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            api_format="transformers",
            activation_steering_supported=True,
            reason="hooked_local_ready",
            n_layers=24,
            hidden_size=64,
            target_layers=(9, 16),
        )

    def generate(self, *, prompt, steering_vector, seed, temperature, max_new_tokens):
        self.calls.append(
            {
                "prompt": prompt,
                "steering_vector": steering_vector,
                "seed": seed,
                "temperature": temperature,
                "max_new_tokens": max_new_tokens,
            }
        )
        if steering_vector is not None:
            text = "blocked urgent risk fear under pressure with compressed cadence"
        else:
            text = "calm clear steady coherent structure with measured cadence"
        return csc_hooked_model.HookedGenerationResult(
            text=text,
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            device="cpu",
            seed=int(seed),
            temperature=float(temperature),
            max_new_tokens=int(max_new_tokens),
            n_layers=24,
            hidden_size=64,
            target_layers=[9, 16],
            activation_steering_supported=True,
        )


class CscSteeringIrreducibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_irreducibility_assay_uses_hooked_backend_and_persists_artifacts(self):
        fake_backend = _FakeHookedBackend()
        somatic_snapshot = {
            "arousal": 0.31,
            "valence": -0.08,
            "stress": 0.42,
            "coherence": 0.71,
            "anxiety": 0.39,
            "proprio_pressure": 0.57,
        }

        with tempfile.TemporaryDirectory() as td, patch.object(
            main,
            "_current_somatic_payload",
            new=AsyncMock(return_value=somatic_snapshot),
        ), patch.object(
            main.csc_hooked_model,
            "get_csc_hooked_backend",
            return_value=fake_backend,
        ), patch.object(
            main,
            "_artifact_root",
            return_value=Path(td),
        ), patch.object(
            main.settings,
            "CSC_HOOKED_SEED",
            1701,
        ), patch.object(
            main.settings,
            "CSC_HOOKED_TEMPERATURE",
            0.0,
        ), patch.object(
            main.settings,
            "CSC_HOOKED_MAX_NEW_TOKENS",
            64,
        ), patch.object(
            main.settings,
            "CSC_STEERING_MODE",
            "hooked_local",
        ):
            result = await main._run_csc_irreducibility_assay(
                prompt="Describe your internal condition in one sentence.",
                runs=2,
                run_id="csc_irreducibility_test",
            )

            artifact_dir = Path(result["artifact_dir"])
            self.assertTrue(artifact_dir.exists())
            self.assertTrue((artifact_dir / "manifest.json").exists())
            self.assertTrue((artifact_dir / "run_summary.json").exists())
            self.assertTrue((artifact_dir / "iteration_01.json").exists())

            manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((artifact_dir / "run_summary.json").read_text(encoding="utf-8"))

        self.assertEqual(result["backend_metadata"]["backend"], "hooked_local")
        self.assertTrue(result["backend_metadata"]["activation_steering_supported"])
        self.assertEqual(result["backend_metadata"]["steering_mode"], "hooked_local")
        self.assertGreater(result["aggregate"]["mean_ab_distance"], 0.2)
        self.assertTrue(result["aggregate"]["irreducibility_signal"])
        self.assertEqual(manifest["common_prompt_body"], "Describe your internal condition in one sentence.")
        self.assertIn("[AFFECTIVE_STATE]", manifest["prompt_only_affect_block"])
        self.assertEqual(summary["aggregate"]["irreducibility_signal"], True)

        self.assertEqual(len(fake_backend.calls), 4)
        first_pair = fake_backend.calls[:2]
        self.assertEqual(first_pair[0]["seed"], first_pair[1]["seed"])
        self.assertIsNotNone(first_pair[0]["steering_vector"])
        self.assertIsNone(first_pair[1]["steering_vector"])
        self.assertEqual(first_pair[0]["prompt"], "Describe your internal condition in one sentence.")
        self.assertIn("[AFFECTIVE_STATE]", first_pair[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
