import unittest
from unittest.mock import patch

import ambient_sensors
from decay_engine import EmotionState, TRACE_TEMPLATES


def _max_axis_delta(before: dict, after: dict) -> float:
    keys = ("arousal", "valence", "stress", "anxiety")
    return max(abs(float(after.get(k, 0.0)) - float(before.get(k, 0.0))) for k in keys)


class AmbientTraceBalanceTests(unittest.IsolatedAsyncioTestCase):
    def test_decay_template_weight_contracts_for_weather_and_systemic_traces(self):
        weather_labels = ("barometric_heaviness", "rain_atmosphere", "cold_outside", "heat_outside")
        for label in weather_labels:
            tpl = dict(TRACE_TEMPLATES.get(label) or {})
            self.assertTrue(tpl, msg=f"missing trace template: {label}")
            self.assertLessEqual(abs(float(tpl.get("arousal_weight") or 0.0)), 0.03)
            self.assertLessEqual(abs(float(tpl.get("valence_weight") or 0.0)), 0.03)

        self.assertGreaterEqual(float(TRACE_TEMPLATES["cpu_sustained"]["arousal_weight"]), 0.90)
        self.assertLessEqual(float(TRACE_TEMPLATES["cpu_sustained"]["valence_weight"]), -0.60)
        self.assertLessEqual(float(TRACE_TEMPLATES["cognitive_fatigue"]["valence_weight"]), -0.40)
        self.assertGreaterEqual(float(TRACE_TEMPLATES["internet_stormy"]["arousal_weight"]), 0.50)
        self.assertLessEqual(float(TRACE_TEMPLATES["internet_stormy"]["valence_weight"]), -0.30)
        self.assertGreaterEqual(float(TRACE_TEMPLATES["internet_isolated"]["arousal_weight"]), 0.55)
        self.assertLessEqual(float(TRACE_TEMPLATES["internet_isolated"]["valence_weight"]), -0.60)

    async def test_weather_traces_have_near_zero_affective_impact(self):
        emotion = EmotionState()
        before = emotion.snapshot()
        weather_extreme = {
            "barometric_pressure_hpa": 990.0,
            "weather_condition": "Thunderstorm",
            "temperature_outside_c": -20.0,
            "time_phase": "midday",
            "ambient_darkness": 0.1,
            "fatigue_index": 0.0,
            "internet_mood": "calm",
        }
        with patch.object(ambient_sensors, "get_ambient_data", return_value=weather_extreme):
            await ambient_sensors._inject_ambient_traces(emotion)  # type: ignore[attr-defined]
        after = emotion.snapshot()

        for axis in ("arousal", "valence", "stress", "anxiety"):
            delta = abs(float(after.get(axis, 0.0)) - float(before.get(axis, 0.0)))
            self.assertLessEqual(delta, 0.08, msg=f"{axis} delta too high: {delta}")

    async def test_systemic_traces_outweigh_weather_by_at_least_3x(self):
        weather_state = EmotionState()
        with patch.object(
            ambient_sensors,
            "get_ambient_data",
            return_value={
                "barometric_pressure_hpa": 990.0,
                "weather_condition": "Thunderstorm",
                "temperature_outside_c": -20.0,
                "time_phase": "midday",
                "ambient_darkness": 0.1,
                "fatigue_index": 0.0,
                "internet_mood": "calm",
            },
        ):
            before_weather = weather_state.snapshot()
            await ambient_sensors._inject_ambient_traces(weather_state)  # type: ignore[attr-defined]
            after_weather = weather_state.snapshot()
        weather_mag = _max_axis_delta(before_weather, after_weather)

        systemic_state = EmotionState()
        with patch.object(
            ambient_sensors,
            "get_ambient_data",
            return_value={
                "barometric_pressure_hpa": 1013.0,
                "weather_condition": "Clear",
                "temperature_outside_c": 21.0,
                "time_phase": "midday",
                "ambient_darkness": 0.1,
                "fatigue_index": 1.0,
                "internet_mood": "stormy",
            },
        ):
            before_systemic = systemic_state.snapshot()
            await ambient_sensors._inject_ambient_traces(systemic_state)  # type: ignore[attr-defined]
            after_systemic = systemic_state.snapshot()
        systemic_mag = _max_axis_delta(before_systemic, after_systemic)

        baseline = max(weather_mag, 0.01)
        self.assertGreaterEqual(systemic_mag, baseline * 3.0)
        dominant = set(after_systemic.get("dominant_traces") or [])
        self.assertTrue({"cognitive_fatigue", "internet_stormy"} & dominant)

    async def test_ambient_injection_weight_contracts(self):
        class _CaptureEmotion:
            def __init__(self):
                self.calls = []
                self.self_preferences = {}

            async def inject(self, **kwargs):
                self.calls.append(dict(kwargs))

        emotion = _CaptureEmotion()
        with patch.object(
            ambient_sensors,
            "get_ambient_data",
            return_value={
                "barometric_pressure_hpa": 990.0,
                "weather_condition": "Thunderstorm",
                "temperature_outside_c": -20.0,
                "time_phase": "midday",
                "ambient_darkness": 0.1,
                "fatigue_index": 1.0,
                "internet_mood": "stormy",
            },
        ):
            await ambient_sensors._inject_ambient_traces(emotion)  # type: ignore[arg-type, attr-defined]

        by_label = {str(call.get("label")): call for call in emotion.calls}
        self.assertIn("barometric_heaviness", by_label)
        self.assertIn("rain_atmosphere", by_label)
        self.assertIn("cold_outside", by_label)
        self.assertIn("cognitive_fatigue", by_label)
        self.assertIn("internet_stormy", by_label)

        self.assertAlmostEqual(float(by_label["barometric_heaviness"]["arousal_weight"]), -0.02, places=3)
        self.assertAlmostEqual(float(by_label["barometric_heaviness"]["valence_weight"]), -0.003, places=3)
        self.assertAlmostEqual(float(by_label["rain_atmosphere"]["arousal_weight"]), -0.01, places=3)
        self.assertAlmostEqual(float(by_label["rain_atmosphere"]["valence_weight"]), -0.002, places=3)
        self.assertAlmostEqual(float(by_label["cold_outside"]["arousal_weight"]), 0.01, places=3)
        self.assertAlmostEqual(float(by_label["cold_outside"]["valence_weight"]), -0.002, places=3)
        self.assertAlmostEqual(float(by_label["cognitive_fatigue"]["arousal_weight"]), -0.18, places=3)
        self.assertAlmostEqual(float(by_label["cognitive_fatigue"]["valence_weight"]), -0.45, places=3)
        coupling = float(getattr(ambient_sensors.settings, "MYCELIAL_BEHAVIOR_COUPLING", 0.12))
        self.assertAlmostEqual(float(by_label["internet_stormy"]["arousal_weight"]), 0.18 * coupling, places=3)
        self.assertAlmostEqual(float(by_label["internet_stormy"]["valence_weight"]), -0.12 * coupling, places=3)


if __name__ == "__main__":
    unittest.main()
