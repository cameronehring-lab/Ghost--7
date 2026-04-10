import asyncio
import inspect
import unittest

import ghost_api


class GhostApiSignatureTests(unittest.TestCase):
    def test_ghost_stream_accepts_lightweight_call_form(self):
        stream = ghost_api.ghost_stream(user_message="hello", somatic={})
        try:
            self.assertTrue(inspect.isasyncgen(stream))
        finally:
            asyncio.run(stream.aclose())


if __name__ == "__main__":
    unittest.main()
