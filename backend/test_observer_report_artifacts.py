import tempfile
import unittest

import observer_report


class ObserverReportArtifactTests(unittest.TestCase):
    def _sample_report(self) -> dict:
        return {
            "report_type": "ObserverReport",
            "version": 1,
            "generated_at": "2026-03-11T00:00:00Z",
            "ghost_id": "omega-7",
            "window_hours": 1,
            "self_model_snapshot": {},
            "notable_self_initiated_changes": [],
            "purpose_vs_usage_conflicts": [],
            "open_risks": [],
            "metrics": {},
        }

    def test_hourly_and_daily_artifacts_are_separately_listed(self):
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as tmp:
            hourly = observer_report.save_report_artifacts(report, root_dir=tmp, kind="hourly")
            daily = observer_report.save_report_artifacts(
                report,
                root_dir=tmp,
                kind="daily",
                day_override="2026-03-10",
            )

            hourly_rows = observer_report.list_report_artifacts(root_dir=tmp, kind="hourly")
            daily_rows = observer_report.list_report_artifacts(root_dir=tmp, kind="daily")

        self.assertEqual(hourly.get("kind"), "hourly")
        self.assertEqual(daily.get("kind"), "daily")
        self.assertEqual(len(hourly_rows), 1)
        self.assertEqual(len(daily_rows), 1)
        self.assertIn("observer_daily_2026-03-10.json", daily_rows[0]["json_path"])

    def test_load_latest_daily_report(self):
        report = self._sample_report()
        report["window_hours"] = 24
        with tempfile.TemporaryDirectory() as tmp:
            observer_report.save_report_artifacts(
                report,
                root_dir=tmp,
                kind="daily",
                day_override="2026-03-10",
            )
            loaded = observer_report.load_latest_report(root_dir=tmp, kind="daily")

        self.assertEqual(loaded.get("report_type"), "ObserverReport")
        self.assertEqual(loaded.get("window_hours"), 24)


if __name__ == "__main__":
    unittest.main()
