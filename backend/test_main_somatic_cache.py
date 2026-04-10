import unittest
from unittest.mock import AsyncMock, patch

import main


class _FakeSnapshot:
    def __init__(self, payload):
        self._payload = dict(payload)

    def model_dump(self):
        return dict(self._payload)


class MainSomaticCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        main.sys_state.somatic_payload_cache = None
        main.sys_state.somatic_payload_cached_at = 0.0
        main.sys_state.init_time_cache = None
        main.sys_state.init_time_cached_at = 0.0

    async def test_current_somatic_payload_uses_short_ttl_cache(self):
        fake_snapshot = _FakeSnapshot({
            "arousal": 0.2,
            "valence": 0.1,
            "stress": 0.0,
            "coherence": 0.9,
            "anxiety": 0.1,
        })

        with (
            patch.object(main, "build_somatic_snapshot", return_value=fake_snapshot) as build_mock,
            patch.object(main.memory, "get_init_time", new=AsyncMock(return_value=123.0)) as init_mock,
        ):
            first = await main._current_somatic_payload(include_init_time=True)
            second = await main._current_somatic_payload(include_init_time=True)

        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(init_mock.await_count, 1)
        self.assertEqual(first["init_time"], 123.0)
        self.assertEqual(second["init_time"], 123.0)
        self.assertEqual(first["stress"], second["stress"])


if __name__ == "__main__":
    unittest.main()
