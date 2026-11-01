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


if __name__ == "__main__":
    unittest.main()
