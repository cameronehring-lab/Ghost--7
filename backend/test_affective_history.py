import unittest

import affective_history


class _FakeWriteAPI:
    def __init__(self):
        self.calls = []

    def write(self, **kwargs):
        self.calls.append(kwargs)


class _FakeClient:
    def __init__(self):
        self.writer = _FakeWriteAPI()

    def write_api(self):
        return self.writer

    def query_api(self):
        raise RuntimeError("not-used")


class AffectiveHistoryTests(unittest.TestCase):
    def test_append_recent_and_axis_history(self):
        history = affective_history.AffectiveHistoryBuffer(max_points=8)
        history.append({"arousal": 0.2, "valence": 0.1, "stress": 0.3, "coherence": 0.8, "anxiety": 0.2}, surprise=0.14, persist=False)
        history.append({"arousal": 0.3, "valence": 0.0, "stress": 0.4, "coherence": 0.7, "anxiety": 0.3}, surprise=0.22, persist=False)

        recent = history.recent(limit=4)
        axis = history.axis_history(limit=4)

        self.assertEqual(len(recent), 2)
        self.assertEqual(len(axis), 2)
        self.assertIn("surprise", recent[-1])
        self.assertIn("timestamp", axis[-1])

    def test_append_persists_when_influx_client_available(self):
        history = affective_history.AffectiveHistoryBuffer(max_points=4)
        fake_client = _FakeClient()
        history.set_influx_client(fake_client)

        history.append(
            {"arousal": 0.25, "valence": -0.1, "stress": 0.45, "coherence": 0.68, "anxiety": 0.39},
            surprise=0.31,
            persist=True,
        )

        self.assertEqual(len(fake_client.writer.calls), 1)
        payload = fake_client.writer.calls[0]
        self.assertIn("record", payload)
        self.assertIn("affective_state", str(payload["record"]))


if __name__ == "__main__":
    unittest.main()
