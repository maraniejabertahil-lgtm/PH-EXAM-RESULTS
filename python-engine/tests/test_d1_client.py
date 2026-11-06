import json
import os
import unittest
from unittest.mock import patch

from database import d1_client
from database.d1_client import D1Client, D1Error


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class D1ClientTests(unittest.TestCase):
    def test_activity_is_disabled_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(d1_client.record_activity({
                "event_id": "evt-1", "execution_id": "exec-1",
                "component": "Python Engine", "operation": "test", "status": "success",
            }))

    def test_partial_environment_configuration_is_rejected_without_leaking_values(self):
        with patch.dict(os.environ, {"CF_ACCOUNT_ID": "account", "CF_D1_API_TOKEN": "private-token"}, clear=True):
            with self.assertRaises(D1Error) as caught:
                D1Client.from_env()
        self.assertNotIn("private-token", str(caught.exception))

    def test_metadata_allowlist_excludes_private_search_fields(self):
        safe = d1_client._metadata({
            "workflow": "tests", "run_id": "123",
            "search_query": "private name", "examinee_name": "PRIVATE PERSON",
        })
        self.assertEqual(safe, {"workflow": "tests", "run_id": "123"})
        self.assertNotIn("search_query", json.dumps(safe))
        self.assertNotIn("examinee_name", json.dumps(safe))

    def test_activity_uses_string_rest_parameters_and_sql_nulls(self):
        captured = {}
        def fake_query(account, database, token, sql, params, **kwargs):
            captured.update(account=account, database=database, token=token, sql=sql, params=list(params))
            return []
        with patch.dict(os.environ, {
            "CF_D1_API_TOKEN": "test-token",
            "CF_ACCOUNT_ID": "account",
            "CF_D1_DATABASE_ID": "database",
        }, clear=True), patch.object(d1_client, "_query", fake_query):
            self.assertTrue(d1_client.record_activity({
                "event_id": "evt-2", "execution_id": "exec-2",
                "component": "Python Engine", "operation": "test",
                "status": "failed", "duration_ms": None,
                "error_code": None, "error_message": None,
            }))
        self.assertTrue(all(isinstance(value, str) for value in captured["params"]))
        self.assertIn("NULLIF", captured["sql"])
        self.assertEqual(captured["params"][0], "evt-2")
        self.assertEqual(captured["params"][3], "failed")

    def test_activity_maps_display_statuses_to_legacy_d1_constraints(self):
        captured = {}
        def fake_query(account, database, token, sql, params, **kwargs):
            captured["params"] = list(params)
            return []
        with patch.dict(os.environ, {
            "CF_D1_API_TOKEN": "test-token", "CF_ACCOUNT_ID": "account", "CF_D1_DATABASE_ID": "database",
        }, clear=True), patch.object(d1_client, "_query", fake_query):
            self.assertTrue(d1_client.record_activity({
                "event_id": "evt-blocked", "execution_id": "exec-blocked",
                "component": "Python Engine", "operation": "prc_release_acquisition",
                "status": "blocked", "severity": "warning",
                "error_code": "PRC_REVIEW_REQUIRED",
            }))
        self.assertEqual(captured["params"][2], "greenlight_failed")
        self.assertEqual(captured["params"][3], "failed")
        self.assertEqual(captured["params"][18], "BLOCKED:PRC_REVIEW_REQUIRED")
        self.assertEqual(captured["params"][15], "warning")

    def test_rest_query_uses_string_parameters_and_cloudflare_endpoint(self):
        captured = {}
        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["auth"] = request.get_header("Authorization")
            return FakeResponse({"success": True, "result": [{"results": [{"ok": 1}]}]})
        client = D1Client("account", "database", "secret-token", opener=fake_opener)
        self.assertEqual(client.query("SELECT ? AS ok", [7]), [{"ok": 1}])
        self.assertIn("/accounts/account/d1/database/database/query", captured["url"])
        self.assertEqual(captured["body"], {"sql": "SELECT ? AS ok", "params": ["7"]})
        self.assertEqual(captured["auth"], "Bearer secret-token")

    def test_api_error_does_not_leak_credentials(self):
        client = D1Client(
            "account", "database", "secret-token",
            opener=lambda *args, **kwargs: FakeResponse({
                "success": False, "errors": [{"message": "secret-token invalid"}],
            }),
        )
        with self.assertRaises(D1Error) as caught:
            client.query("SELECT 1")
        self.assertNotIn("secret-token", str(caught.exception))

    def test_import_batch_status_is_allowlisted(self):
        client = D1Client("account", "database", "token", opener=lambda *args, **kwargs: FakeResponse({
            "success": True, "result": [{"results": []}],
        }))
        with self.assertRaises(ValueError):
            client.upsert_import_batch(
                batch_id="b", authority="PRC", exam="LEPT", exam_year=2026,
                status="published; DROP TABLE",
            )

    def test_migration_adds_missing_columns_to_existing_private_metadata_tables(self):
        legacy = {
            "monitoring_logs": {"id", "event_type", "status", "summary", "authority", "exam", "exam_year",
                                "source_id", "correlation_id", "created_at"},
            "import_batches": {"batch_id", "authority", "exam", "exam_year", "source_id", "status",
                               "greenlight_score", "announced_count", "extracted_count", "summary", "created_at", "updated_at"},
            "release_predictions": {"id", "authority", "exam", "exam_year", "predicted_release_date",
                                    "method", "confidence", "evidence_count", "created_at"},
        }
        statements = []
        def fake_execute(sql, params=()):
            statements.append(sql)
            if sql.startswith("PRAGMA table_info("):
                table = sql.split("(")[1].split(")")[0]
                return [{"results": [{"name": name} for name in legacy[table]]}]
            return []
        with patch.object(d1_client, "execute", fake_execute):
            d1_client.apply_schema()
        joined = "\n".join(statements)
        self.assertIn("ALTER TABLE monitoring_logs ADD COLUMN execution_id", joined)
        self.assertIn("ALTER TABLE import_batches ADD COLUMN record_count", joined)
        self.assertIn("ALTER TABLE release_predictions ADD COLUMN prediction_id", joined)
        self.assertTrue(any(statement.startswith("CREATE INDEX") for statement in statements))


if __name__ == "__main__":
    unittest.main()
