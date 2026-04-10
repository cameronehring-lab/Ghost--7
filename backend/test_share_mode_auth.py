import base64
import unittest
from types import SimpleNamespace

import main


class _DummyRequest:
    def __init__(
        self,
        headers: dict[str, str],
        *,
        url_hostname: str = "",
        client_host: str = "",
    ):
        self.headers = headers
        self.url = SimpleNamespace(hostname=url_hostname, path="/")
        self.client = SimpleNamespace(host=client_host)


class ShareModeAuthTests(unittest.TestCase):
    def test_extract_basic_auth_valid(self):
        token = base64.b64encode(b"omega:secret").decode("ascii")
        req = _DummyRequest({"authorization": f"Basic {token}"})
        user, password = main._extract_basic_auth(req)  # type: ignore[attr-defined]
        self.assertEqual(user, "omega")
        self.assertEqual(password, "secret")

    def test_extract_basic_auth_invalid(self):
        req = _DummyRequest({"authorization": "Basic not_base64"})
        user, password = main._extract_basic_auth(req)  # type: ignore[attr-defined]
        self.assertEqual(user, "")
        self.assertEqual(password, "")

    def test_share_exempt_default_health(self):
        self.assertTrue(main._is_share_exempt("/health"))  # type: ignore[attr-defined]
        self.assertFalse(main._is_share_exempt("/somatic"))  # type: ignore[attr-defined]

    def test_loopback_request_detects_localhost(self):
        req = _DummyRequest({"host": "localhost:8000"}, url_hostname="localhost", client_host="127.0.0.1")
        self.assertTrue(main._is_loopback_request(req))  # type: ignore[attr-defined]

    def test_loopback_request_rejects_remote_hostname(self):
        req = _DummyRequest({"host": "omega-protocol-ghost.com"}, url_hostname="omega-protocol-ghost.com", client_host="172.67.182.229")
        self.assertFalse(main._is_loopback_request(req))  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
