import unittest

from contact_threads import EphemeralContactThreadStore


class ContactThreadStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_keeps_last_twelve_and_updates_summary(self):
        store = EphemeralContactThreadStore(redis_url="", ttl_seconds=3600)
        await store.start()
        try:
            for idx in range(14):
                await store.append_turn(
                    thread_key="+12145551212",
                    person_key="cameron",
                    contact_handle="+12145551212",
                    direction="inbound" if idx % 2 == 0 else "outbound",
                    text=f"message-{idx}",
                )

            thread = await store.get_thread("+12145551212")
            turns = list(thread.get("turns") or [])
            self.assertEqual(len(turns), 12)
            self.assertTrue(str(thread.get("compact_summary") or "").strip())
            self.assertIn("message-0", str(thread.get("compact_summary")))

            history = await store.build_history("+12145551212", max_turns=12)
            self.assertGreaterEqual(len(history), 12)
            self.assertEqual(history[0]["role"], "model")
        finally:
            await store.close()


if __name__ == "__main__":
    unittest.main()
