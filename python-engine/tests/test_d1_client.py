import os
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
