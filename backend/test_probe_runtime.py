import unittest
from unittest.mock import patch

import probe_runtime


class ProbeRuntimeTests(unittest.TestCase):
    def tearDown(self):
        probe_runtime.clear_probe()

    def test_latency_probe_overrides_ambient_and_generation_latency(self):
        probe_runtime.activate_probe(
            "latency_spike",
            label="latency-test",
            duration_seconds=10,
            params={"latency_ms": 2200, "spread_ms": 900},
        )
        ambient = probe_runtime.apply_ambient_overlay({"internet_mood": "calm", "global_latency_avg_ms": 12.0})
        self.assertEqual(ambient["internet_mood"], "stormy")
        self.assertEqual(float(ambient["global_latency_avg_ms"]), 2200.0)
        self.assertEqual(float(probe_runtime.effective_generation_latency_ms(120.0)), 2200.0)

    def test_probe_overlay_expires_and_returns_original_values(self):
        with patch.object(probe_runtime.time, "time", return_value=100.0):
            probe_runtime.activate_probe(
                "barometric_storm",
                label="storm-test",
                duration_seconds=5,
                params={"pressure_hpa": 992.0},
            )
        with patch.object(probe_runtime.time, "time", return_value=102.0):
            active = probe_runtime.get_active_probe()
            self.assertIsNotNone(active)
            ambient = probe_runtime.apply_ambient_overlay({"barometric_pressure_hpa": 1014.0})
            self.assertEqual(float(ambient["barometric_pressure_hpa"]), 992.0)
        with patch.object(probe_runtime.time, "time", return_value=106.5):
            self.assertIsNone(probe_runtime.get_active_probe())
            ambient = probe_runtime.apply_ambient_overlay({"barometric_pressure_hpa": 1014.0})
            self.assertEqual(float(ambient["barometric_pressure_hpa"]), 1014.0)
            self.assertEqual(float(probe_runtime.effective_generation_latency_ms(88.0)), 88.0)


if __name__ == "__main__":
    unittest.main()
