import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

from imessage_bridge import IMessageBridge


async def _noop_callback(_record):
    return None


class IMessageBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="imessage_bridge_test_")
        self.db_path = Path(self.tmpdir.name) / "chat.db"
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                CREATE TABLE handle (
                    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT,
                    service TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE message (
                    guid TEXT,
                    text TEXT,
                    handle_id INTEGER,
                    is_from_me INTEGER,
                    date INTEGER
                )
                """
            )
            conn.execute("INSERT INTO handle (id, service) VALUES (?, ?)", ("(214) 555-1212", "iMessage"))
            conn.execute("INSERT INTO handle (id, service) VALUES (?, ?)", ("Friend@Example.com", "iMessage"))
            conn.execute(
                "INSERT INTO message (guid, text, handle_id, is_from_me, date) VALUES (?, ?, ?, ?, ?)",
                ("m-1", "hello from phone", 1, 0, 123),
            )
            conn.execute(
                "INSERT INTO message (guid, text, handle_id, is_from_me, date) VALUES (?, ?, ?, ?, ?)",
                ("m-2", "outbound echo", 1, 1, 124),
            )
            conn.execute(
                "INSERT INTO message (guid, text, handle_id, is_from_me, date) VALUES (?, ?, ?, ?, ?)",
                ("m-3", "", 2, 0, 125),
            )
            conn.commit()
        finally:
            conn.close()

        self.loop = asyncio.new_event_loop()

    def tearDown(self):
        self.loop.close()
        self.tmpdir.cleanup()

    def _bridge(self) -> IMessageBridge:
        return IMessageBridge(
            db_path=str(self.db_path),
            poll_interval_seconds=1.0,
            batch_size=20,
            on_message=_noop_callback,
            loop=self.loop,
        )

    def test_read_max_rowid(self):
        bridge = self._bridge()
        self.assertEqual(bridge._read_max_rowid(), 3)

    def test_poll_filters_inbound_and_normalizes_handle(self):
        bridge = self._bridge()
        records = bridge._poll_new_messages(0)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.guid, "m-1")
        self.assertEqual(rec.text, "hello from phone")
        self.assertEqual(rec.handle, "+12145551212")

    def test_poll_respects_last_rowid(self):
        bridge = self._bridge()
        records = bridge._poll_new_messages(3)
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
