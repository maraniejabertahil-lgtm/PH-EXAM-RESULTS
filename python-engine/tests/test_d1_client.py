import json
import os
import unittest
from unittest.mock import patch
from database import d1_client

class D1ClientTests(unittest.TestCase):
    def test_activity_is_disabled_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(d1_client.record_activity({
                "event_id": "evt-1", "execution_id": "exec-1",
                "component": "Python Engine", "operation": "test", "status": "success",
            }))

    def test_metadata_allowlist_excludes_private_search_fields(self):
        safe = d1_client._metadata({
            "workflow": "tests", "run_id": "123",
            "search_query": "private name", "examinee_name": "PRIVATE PERSON",
        })
        self.assertEqual(safe, {"workflow": "tests", "run_id": "123"})
        self.assertNotIn("search_query", json.dumps(safe))
        self.assertNotIn("examinee_name", json.dumps(safe))

    def test_activity_uses_only_string_rest_parameters_and_sql_nulls(self):
        captured = {}
        def fake_execute(sql, params=()):
            captured["sql"] = sql
            captured["params"] = list(params)
            return []
        with patch.dict(os.environ, {
            "CF_D1_API_TOKEN": "test-token",
            "CF_ACCOUNT_ID": "account",
            "CF_D1_DATABASE_ID": "database",
        }, clear=True), patch.object(d1_client, "execute", fake_execute):
            self.assertTrue(d1_client.record_activity({
                "event_id": "evt-2", "execution_id": "exec-2",
                "component": "Python Engine", "operation": "test",
                "status": "failed", "duration_ms": None,
                "error_code": None, "error_message": None,
            }))
        self.assertTrue(all(isinstance(value, str) for value in captured["params"]))
        self.assertIn("NULLIF", captured["sql"])

    def test_execute_rejects_non_string_rest_parameters(self):
        with patch.dict(os.environ, {
            "CF_D1_API_TOKEN": "test-token",
            "CF_ACCOUNT_ID": "account",
            "CF_D1_DATABASE_ID": "database",
        }, clear=True):
            with self.assertRaises(TypeError):
                d1_client.execute("SELECT ?", [7], opener=lambda *args, **kwargs: None)

    def test_execute_uses_cloudflare_d1_rest_endpoint_and_parameterized_query(self):
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"success":true,"result":[{"results":[]}]}' 
        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["auth"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return Response()
        with patch.dict(os.environ, {
            "CF_D1_API_TOKEN": "test-token",
            "CF_ACCOUNT_ID": "account",
            "CF_D1_DATABASE_ID": "database",
        }, clear=True):
            result = d1_client.execute("SELECT * FROM monitoring_logs WHERE event_id = ?", ["evt"], opener=fake_opener)
        self.assertIn("/accounts/account/d1/database/database/query", captured["url"])
        self.assertEqual(captured["body"]["params"], ["evt"])
        self.assertEqual(captured["auth"], "Bearer test-token")
        self.assertEqual(result, [{"results": []}])

if __name__ == "__main__":
    unittest.main()
