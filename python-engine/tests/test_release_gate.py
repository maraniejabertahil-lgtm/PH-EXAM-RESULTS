import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import broadcaster


class ReleaseGateTests(unittest.TestCase):
    def test_deployment_must_be_successful_on_main(self):
        item = {"name": "Deploy Cloudflare Pages", "status": "completed",
                "conclusion": "success", "head_branch": "main"}
        broadcaster.validate_deployment(item)
        for key, value in (("conclusion", "failure"), ("head_branch", "feature"),
                           ("status", "queued")):
            candidate = dict(item)
            candidate[key] = value
            with self.assertRaises(broadcaster.BroadcastError):
                broadcaster.validate_deployment(candidate)

    def test_announcement_requires_secure_url(self):
        result = broadcaster.announcement("PRC", "LEPT Elementary", "2026", "https://results.example")
        self.assertIn("sequence numbers", result)
        with self.assertRaises(broadcaster.BroadcastError):
            broadcaster.announcement("PRC", "LEPT", "2026", "http://results.example")


if __name__ == "__main__":
    unittest.main()
