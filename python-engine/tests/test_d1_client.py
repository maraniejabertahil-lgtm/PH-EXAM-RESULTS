from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from database.d1_client import D1Client, D1Error


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


class D1ClientTests(unittest.TestCase):
    def test_query_uses_rest_api_and_binds_parameters(self):
        opener = Mock(return_value=FakeResponse({"success": True, "result": [{"results": [{"ok": 1}]}]}))
        client = D1Client("account", "database", "secret-token", opener=opener)
        self.assertEqual(client.query("SELECT ? AS ok", [1]), [{"ok": 1}])
        request = opener.call_args.args[0]
        self.assertIn("/d1/database/database/query", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(json.loads(request.data), {"sql": "SELECT ? AS ok", "params": [1]})

    def test_api_error_does_not_leak_credentials(self):
        opener = Mock(return_value=FakeResponse({"success": False, "errors": [{"message": "secret-token invalid"}]}))
        client = D1Client("account", "database", "secret-token", opener=opener)
        with self.assertRaises(D1Error) as caught:
            client.query("SELECT 1")
        self.assertNotIn("secret-token", str(caught.exception))

    def test_partial_environment_configuration_is_rejected(self):
        with patch.dict("os.environ", {"CF_ACCOUNT_ID": "account"}, clear=True):
            with self.assertRaises(D1Error):
                D1Client.from_env()

    def test_import_batch_status_is_allowlisted(self):
        opener = Mock(return_value=FakeResponse({"success": True, "result": [{"results": []}]}))
        client = D1Client("account", "database", "token", opener=opener)
        with self.assertRaises(ValueError):
            client.upsert_import_batch(batch_id="b", authority="PRC", exam="LEPT", exam_year=2026, status="published; DROP TABLE")


if __name__ == "__main__":
    unittest.main()
