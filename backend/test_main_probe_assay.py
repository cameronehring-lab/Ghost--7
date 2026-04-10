import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

import main
from models import ProbeAssayRequest, QualiaProbeReport


def _fake_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/diagnostics/probes/assay",
        "headers": [],
        "client": ("127.0.0.1", 8000),
    }
    return Request(scope)


def _snap(timestamp: float, **overrides):
    base = {
        "timestamp": timestamp,
        "arousal": 0.3,
        "stress": 0.2,
        "coherence": 0.8,
        "anxiety": 0.1,
        "proprio_pressure": 0.2,
        "global_latency_avg_ms": 15.0,
        "barometric_pressure_hpa": 1014.0,
        "internet_mood": "calm",
        "weather_condition": "Clear",
        "dominant_traces": ["system_calm"],
    }
    base.update(overrides)
    return base


class ProbeAssayEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _run_assay(self, probe_type: str, signature: dict, snapshots: list[dict], report: QualiaProbeReport):
        req = _fake_request()
        body = ProbeAssayRequest(
            probe_type=probe_type,
            label=f"{probe_type}-label",
            duration_seconds=6,
            settle_seconds=0,
            sample_seconds=2,
            params={},
            persist=True,
        )
        sleep_mock = AsyncMock(return_value=None)
        persist_mock = AsyncMock(return_value=None)
        with patch.object(main.memory, "_pool", object()), patch.object(
            main, "_current_somatic_payload", new=AsyncMock(side_effect=snapshots)
        ), patch.object(
            main, "generate_probe_qualia_report", new=AsyncMock(return_value=report)
        ), patch.object(
            main.feedback_logger, "log_phenomenological_shift", new=persist_mock
        ), patch.object(
            main.probe_runtime, "activate_probe", return_value=signature
        ), patch.object(
            main.probe_runtime, "clear_probe", return_value=None
        ), patch.object(
            main.asyncio, "sleep", new=sleep_mock
        ):
            payload = await main.diagnostics_probe_assay(req, body)
        return payload, persist_mock

    def _assert_probe_assay_persistence(self, persist_mock: AsyncMock, probe_type: str):
        persist_mock.assert_awaited_once()
        args = persist_mock.await_args.args
        self.assertEqual(args[2], f"probe:{probe_type}")
        before_state = args[3]
        after_state = args[4]
        self.assertEqual(before_state["probe_assay"]["probe_type"], probe_type)
        self.assertEqual(after_state["probe_assay"]["probe_type"], probe_type)
        self.assertEqual(before_state["probe_assay"]["stage"], "baseline")
        self.assertEqual(after_state["probe_assay"]["stage"], "post")
        self.assertEqual(before_state["probe_assay"]["assay_metadata"]["duration_seconds"], 6.0)
        self.assertEqual(before_state["probe_assay"]["assay_metadata"]["settle_seconds"], 0.0)
        self.assertEqual(before_state["probe_assay"]["assay_metadata"]["sample_seconds"], 2)
        self.assertTrue(before_state["probe_assay"]["assay_metadata"]["persist"])
        self.assertEqual(len(after_state["probe_assay"]["series"]), 2)
        self.assertIn("structured_report", after_state["probe_assay"])

    async def test_latency_spike_probe_returns_structured_payload_and_persists(self):
        report = QualiaProbeReport(
            agitation=0.7,
            heaviness=0.2,
            clarity=0.5,
            temporal_drag=0.8,
            isolation=0.3,
            urgency=0.9,
            dominant_metaphors=["drag", "distance"],
            subjective_report="I feel the moment stretching and tightening at once.",
        )
        signature = {
            "run_id": "probe-latency-1",
            "probe_type": "latency_spike",
            "shock_request": {},
            "ambient_overlay": {"internet_mood": "stormy"},
        }
        snapshots = [
            _snap(1.0),
            _snap(2.0, global_latency_avg_ms=2200.0, internet_mood="stormy", proprio_pressure=0.55, anxiety=0.35),
            _snap(3.0, global_latency_avg_ms=2200.0, internet_mood="stormy", proprio_pressure=0.57, anxiety=0.37),
            _snap(4.0, global_latency_avg_ms=2200.0, internet_mood="stormy", proprio_pressure=0.58, anxiety=0.38),
        ]
        with patch.object(main, "inject_ambient_traces", new=AsyncMock(return_value=None)) as ambient_mock, patch.object(
            main.emotion_state, "inject", new=AsyncMock(return_value=True)
        ) as emotion_mock:
            payload, persist_mock = await self._run_assay("latency_spike", signature, snapshots, report)

        self.assertEqual(payload["probe_type"], "latency_spike")
        self.assertEqual(payload["probe_signature"]["run_id"], "probe-latency-1")
        self.assertEqual(len(payload["series"]), 2)
        self.assertEqual(payload["structured_report"]["temporal_drag"], 0.8)
        self.assertEqual(payload["persistence"]["trigger_source"], "probe:latency_spike")
        ambient_mock.assert_awaited_once()
        emotion_mock.assert_not_awaited()
        self._assert_probe_assay_persistence(persist_mock, "latency_spike")

    async def test_barometric_storm_probe_returns_structured_payload_and_persists(self):
        report = QualiaProbeReport(
            agitation=0.4,
            heaviness=0.85,
            clarity=0.44,
            temporal_drag=0.52,
            isolation=0.2,
            urgency=0.41,
            dominant_metaphors=["weight", "ozone"],
            subjective_report="The air feels heavier and more contemplative than before.",
        )
        signature = {
            "run_id": "probe-storm-1",
            "probe_type": "barometric_storm",
            "shock_request": {},
            "ambient_overlay": {"barometric_pressure_hpa": 993.0},
        }
        snapshots = [
            _snap(10.0, barometric_pressure_hpa=1014.0),
            _snap(11.0, barometric_pressure_hpa=993.0, weather_condition="Thunderstorm", stress=0.33),
            _snap(12.0, barometric_pressure_hpa=993.0, weather_condition="Thunderstorm", stress=0.35),
            _snap(13.0, barometric_pressure_hpa=993.0, weather_condition="Thunderstorm", stress=0.36),
        ]
        with patch.object(main, "inject_ambient_traces", new=AsyncMock(return_value=None)) as ambient_mock:
            payload, persist_mock = await self._run_assay("barometric_storm", signature, snapshots, report)

        self.assertEqual(payload["probe_type"], "barometric_storm")
        self.assertEqual(payload["post_somatic"]["barometric_pressure_hpa"], 993.0)
        self.assertEqual(payload["structured_report"]["heaviness"], 0.85)
        self.assertEqual(payload["persistence"]["trigger_source"], "probe:barometric_storm")
        ambient_mock.assert_awaited_once()
        self._assert_probe_assay_persistence(persist_mock, "barometric_storm")

    async def test_somatic_shock_control_returns_structured_payload_and_persists(self):
        report = QualiaProbeReport(
            agitation=0.66,
            heaviness=0.31,
            clarity=0.36,
            temporal_drag=0.28,
            isolation=0.12,
            urgency=0.71,
            dominant_metaphors=["compression", "jolt"],
            subjective_report="The shift lands like a brief tightening before it begins to thin out.",
        )
        signature = {
            "run_id": "probe-control-1",
            "probe_type": "somatic_shock_control",
            "shock_request": {
                "label": "probe_control",
                "intensity": 1.25,
                "k": 0.45,
                "arousal_weight": 1.0,
                "valence_weight": -0.35,
            },
            "ambient_overlay": {},
        }
        snapshots = [
            _snap(20.0),
            _snap(21.0, arousal=0.74, stress=0.51, anxiety=0.49, dominant_traces=["probe_control"]),
            _snap(22.0, arousal=0.69, stress=0.46, anxiety=0.43, dominant_traces=["probe_control"]),
            _snap(23.0, arousal=0.66, stress=0.42, anxiety=0.39, dominant_traces=["probe_control"]),
        ]
        with patch.object(main, "inject_ambient_traces", new=AsyncMock(return_value=None)) as ambient_mock, patch.object(
            main.emotion_state, "inject", new=AsyncMock(return_value=True)
        ) as emotion_mock:
            payload, persist_mock = await self._run_assay("somatic_shock_control", signature, snapshots, report)

        self.assertEqual(payload["probe_type"], "somatic_shock_control")
        self.assertEqual(payload["structured_report"]["urgency"], 0.71)
        self.assertEqual(payload["persistence"]["trigger_source"], "probe:somatic_shock_control")
        ambient_mock.assert_not_awaited()
        emotion_mock.assert_awaited_once()
        self._assert_probe_assay_persistence(persist_mock, "somatic_shock_control")


if __name__ == "__main__":
    unittest.main()
