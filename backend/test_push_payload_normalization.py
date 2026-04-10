import json
import unittest

from main import _normalize_push_payload


class PushPayloadNormalizationTests(unittest.TestCase):
    def test_plain_text_becomes_text_payload(self):
        payload = _normalize_push_payload("hello from ghost")
        self.assertEqual(payload["text"], "hello from ghost")
        self.assertIn("timestamp", payload)

    def test_json_string_is_decoded(self):
        payload = _normalize_push_payload('{"text":"hi","kind":"proactive"}')
        self.assertEqual(payload["text"], "hi")
        self.assertEqual(payload["kind"], "proactive")

    def test_bytes_json_string_is_decoded(self):
        payload = _normalize_push_payload(b'{"message":"hi"}')
        self.assertEqual(payload["text"], "hi")

    def test_dict_without_text_falls_back(self):
        payload = _normalize_push_payload({"kind": "x", "value": 2})
        self.assertTrue(payload["text"])
        # Ensure payload is still JSON-serializable.
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
