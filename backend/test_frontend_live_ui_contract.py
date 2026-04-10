from pathlib import Path
import unittest


class TestFrontendLiveUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate_paths = [
            Path(__file__).resolve().parents[1] / "frontend" / "app.js",
            Path("/Users/cehring/OMEGA4/frontend/app.js"),
        ]
        app_path = next((p for p in candidate_paths if p.exists()), None)
        if app_path is None:
            raise unittest.SkipTest("frontend/app.js is not mounted in this environment")
        cls.source = app_path.read_text(encoding="utf-8")

    def test_live_stream_load_labels_are_not_internet_mood_terms(self):
        self.assertIn("liveLoadLabel = 'CLEAR'", self.source)
        self.assertIn("liveLoadLabel = 'ELEVATED'", self.source)
        self.assertIn("liveLoadLabel = 'SATURATED'", self.source)

    def test_live_diagnostics_trace_and_counters_present(self):
        self.assertIn("LIVE_DIAGNOSTICS_TRACE_LIMIT", self.source)
        self.assertIn("__omegaLiveDiagnosticsTrace", self.source)
        self.assertIn("sent_audio_chunks", self.source)
        self.assertIn("sent_video_frames", self.source)
        self.assertIn("send_failures", self.source)
        self.assertIn("turn_phase_change", self.source)


if __name__ == "__main__":
    unittest.main()
