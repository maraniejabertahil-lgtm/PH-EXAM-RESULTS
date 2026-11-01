import json
import tempfile
import unittest
from pathlib import Path

from scraper.monitor import monitor_registry, monitor_source


class SourceMonitorTests(unittest.TestCase):
    def test_empty_registry_is_safe_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.json"
            path.write_text(json.dumps({"schema_version": 1, "sources": []}), encoding="utf-8")
            result = monitor_registry(path)
        self.assertEqual(result["source_count"], 0)
        self.assertEqual(result["results"], [])

    def test_unverified_third_party_is_rejected_without_network(self):
        result = monitor_source({
            "id": "candidate",
            "source_type": "verified_third_party",
            "verified_by_owner": False,
            "enabled": True,
            "url": "https://example.com/results",
        })
        self.assertEqual(result["status"], "rejected")

    def test_unapproved_official_source_is_rejected(self):
        result = monitor_source({
            "id": "official-candidate",
            "source_type": "official",
            "authorized": False,
            "enabled": True,
            "url": "https://example.com/results",
        })
        self.assertEqual(result["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
