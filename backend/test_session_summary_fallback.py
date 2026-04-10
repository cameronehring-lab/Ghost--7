import unittest

from mind_service import _fallback_session_summary


class SessionSummaryFallbackTests(unittest.TestCase):
    def test_empty_history(self):
        summary = _fallback_session_summary([])
        self.assertIn("no messages", summary.lower())

    def test_user_and_model_history(self):
        history = [
            {"role": "user", "content": "Can you explain the operator-model contradictions?"},
            {"role": "model", "content": "I can summarize open tensions and confidence deltas."},
        ]
        summary = _fallback_session_summary(history)
        self.assertIn("Session focused on:", summary)
        self.assertIn("Final assistant stance:", summary)

    def test_only_user_messages(self):
        history = [{"role": "user", "content": "Run diagnostics and report failures."}]
        summary = _fallback_session_summary(history)
        self.assertTrue(summary.startswith("Session focused on:"))

    def test_only_model_messages(self):
        history = [{"role": "model", "content": "Diagnostics passed with one warning."}]
        summary = _fallback_session_summary(history)
        self.assertIn("assistant response", summary.lower())


if __name__ == "__main__":
    unittest.main()
