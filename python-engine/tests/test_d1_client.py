import json
import os
import unittest
from unittest.mock import MagicMock, patch

from database.d1_client import D1Client, D1Error


class D1ClientTests(unittest.TestCase):
    def test_requires_all_environment_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(D1Error):
                D1Client.from_environment()

    def test_builds_expected_endpoint(self):
        client = D1Client("account", "database", "secret")
        self.assertEqual(
            client.endpoint,
            "https://api.cloudflare.com/client/v4/accounts/account/d1/database/database/query",
        )

    def test_adds_content_length_to_existing_source_states_table(self):
        client = D1Client("account", "database", "secret")
        with patch.object(client, "query") as query:
            query.side_effect = [
                [],  # CREATE TABLE statements
                [{"name": "source_id"}, {"name": "etag"}, {"name": "checked_at"}],
                [],
            ]
            with patch("database.d1_client.Path.read_text", return_value="CREATE TABLE IF NOT EXISTS source_states (source_id TEXT PRIMARY KEY);"):
                client.apply_schema("schema.sql")
        self.assertEqual(
            query.call_args_list[-1].args[0],
            "ALTER TABLE source_states ADD COLUMN content_length TEXT",
        )

    def test_does_not_repeat_content_length_migration(self):
        client = D1Client("account", "database", "secret")
        with patch.object(client, "query") as query:
            query.side_effect = [
                [],
                [{"name": "source_id"}, {"name": "content_length"}],
            ]
            with patch("database.d1_client.Path.read_text", return_value="CREATE TABLE IF NOT EXISTS source_states (source_id TEXT PRIMARY KEY);"):
                client.apply_schema("schema.sql")
        self.assertEqual(query.call_count, 2)

    def test_storage_stats_uses_documented_database_details_endpoint(self):
        client = D1Client("account", "database", "secret")
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'{"success":true,"result":{"file_size":1234,"name":"metadata","version":"1"}}'
        )
        with patch("database.d1_client.urllib.request.urlopen", return_value=response) as opener:
            stats = client.get_storage_stats()
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.cloudflare.com/client/v4/accounts/account/d1/database/database",
        )
        self.assertEqual(stats["estimated_storage_bytes"], 1234)

    def test_query_serializes_all_bound_parameters_as_strings(self):
        client = D1Client("account", "database", "secret")
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'{"success":true,"result":[{"success":true,"results":[]}]}'
        )
        with patch("database.d1_client.urllib.request.urlopen", return_value=response) as opener:
            client.query("SELECT ?, ?, ?", ["text", 2026, True])
        request = opener.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["params"], ["text", "2026", "1"])

    def test_query_rejects_null_bound_parameters(self):
        client = D1Client("account", "database", "secret")
        with self.assertRaises(D1Error):
            client.query("SELECT ?", [None])

    def test_nullable_source_state_values_use_sql_null_literals(self):
        client = D1Client("account", "database", "secret")
        with patch.object(client, "query") as query:
            client.save_source_state("source-1", None, "modified", None, "checked")
        sql, params = query.call_args.args
        self.assertIn("VALUES (?, NULL, ?, NULL, ?)", sql)
        self.assertEqual(params, ["source-1", "modified", "checked"])

    def test_nullable_monitor_log_values_use_sql_null_literals(self):
        client = D1Client("account", "database", "secret")
        with patch.object(client, "query") as query:
            client.record_monitoring_log("source-1", "reachable", "checked")
        sql, params = query.call_args.args
        self.assertIn("VALUES (?, ?, ?, ?, NULL, NULL, NULL)", sql)
        self.assertEqual(len(params), 4)

    def test_import_batch_status_reflects_duplicate_review_requirements(self):
        cases = [
            ({"exact_duplicates": [{"first_index": 0, "duplicate_index": 1}], "fuzzy_candidates": []},
             "exact_duplicates_review_required"),
            ({"exact_duplicates": [], "fuzzy_candidates": [{"first_index": 0, "candidate_index": 1}]},
             "fuzzy_review_required"),
            ({"exact_duplicates": [], "fuzzy_candidates": []}, "validation_passed"),
        ]
        for duplicates, expected_status in cases:
            client = D1Client("account", "database", "secret")
            report = {
                "authority": "PRC",
                "examination": "LET",
                "year": 2026,
                "source_file": "results.csv",
                "validation": {
                    "is_valid": True,
                    "total_records": 2,
                    "valid_records": 2,
                    "invalid_records": [],
                },
                "duplicates": duplicates,
            }
            with self.subTest(expected_status=expected_status):
                with patch.object(client, "query") as query:
                    client.record_import_batch(report)
                sql, bound_params = query.call_args.args
                self.assertIn("?, NULL, ?)", sql)
                self.assertNotIn(None, bound_params)
                self.assertEqual(query.call_args.args[1][9], expected_status)


if __name__ == "__main__":
    unittest.main()
