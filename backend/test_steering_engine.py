import unittest

import numpy as np

import local_llm_client
import steering_engine


class _FakeEmotionState:
    def __init__(self):
        self.calls: list[dict] = []

    async def inject(
        self,
        label,
        intensity,
        k,
        arousal_weight=1.0,
        valence_weight=0.0,
        force=False,
    ):
        self.calls.append(
            {
                "label": label,
                "intensity": float(intensity),
                "k": float(k),
                "arousal_weight": float(arousal_weight),
                "valence_weight": float(valence_weight),
                "force": bool(force),
            }
        )
        return True


class SteeringEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_build_vector_returns_expected_shape(self):
        engine = steering_engine.SteeringEngine(
            vector_dim=32,
            base_scale=0.35,
            pressure_gain=0.65,
            writeback_enabled=True,
        )
        vec = engine.build_vector(
            {
                "arousal": 0.4,
                "valence": -0.2,
                "stress": 0.6,
                "coherence": 0.7,
                "anxiety": 0.5,
            }
        )
        self.assertEqual(vec.shape, (32,))
        self.assertEqual(vec.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(vec)), 1.0, places=4)

    def test_build_vector_supports_hidden_size_override(self):
        engine = steering_engine.SteeringEngine(
            vector_dim=32,
            base_scale=0.35,
            pressure_gain=0.65,
            writeback_enabled=True,
        )
        vec = engine.build_vector(
            {
                "arousal": 0.4,
                "valence": -0.2,
                "stress": 0.6,
                "coherence": 0.7,
                "anxiety": 0.5,
            },
            vector_dim=896,
        )
        self.assertEqual(vec.shape, (896,))
        self.assertEqual(vec.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(vec)), 1.0, places=4)

    def test_inject_returns_metadata(self):
        engine = steering_engine.SteeringEngine(
            vector_dim=32,
            base_scale=0.35,
            pressure_gain=0.65,
            writeback_enabled=True,
        )
        handle = local_llm_client.ActivationHandle(
            backend="local",
            model="llama3.1:8b",
            api_format="ollama",
            activation_steering_supported=False,
            reason="phase_2_not_implemented",
        )
        vec = np.ones((32,), dtype=np.float32) / np.sqrt(32.0)
        meta = engine.inject(handle, vec, pressure=0.8)
        self.assertIn("target_layers", meta)
        self.assertGreater(meta["magnitude"], 0.0)
        self.assertEqual(meta["vector_dim"], 32)
        self.assertFalse(meta["applied"])

    async def test_affective_write_back_injects_traces(self):
        engine = steering_engine.SteeringEngine(
            vector_dim=32,
            base_scale=0.35,
            pressure_gain=0.65,
            writeback_enabled=True,
        )
        state = _FakeEmotionState()
        result = await engine.affective_write_back(
            "I cannot complete that request right now. This is blocked and urgent.",
            state,
            baseline_snapshot={
                "arousal": 0.1,
                "valence": 0.2,
                "stress": 0.1,
                "coherence": 0.8,
                "anxiety": 0.1,
            },
        )
        self.assertIn(result["writeback"], {"applied", "no_delta"})
        self.assertGreaterEqual(len(state.calls), 1)
        labels = {c["label"] for c in state.calls}
        self.assertTrue(any(label.startswith("steer_writeback_") for label in labels))


if __name__ == "__main__":
    unittest.main()
