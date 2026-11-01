import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_third_party_is_skipped_when_official_source_is_reachable(self):
        registry = {
            "sources": [
                {"id": "official", "authority": "PRC", "exam": "LET", "source_type": "official", "authorized": True, "enabled": True, "url": "https://official.example/results"},
                {"id": "backup", "authority": "PRC", "exam": "LET", "source_type": "verified_third_party", "verified_by_owner": True, "enabled": True, "url": "https://backup.example/results"},
            ]
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with patch("scraper.monitor.monitor_source", return_value={"source_id": "official", "status": "reachable"}):
                result = monitor_registry(path)
        self.assertEqual(result["results"][1]["status"], "skipped_official_available")

    def test_third_party_is_checked_when_official_source_is_unavailable(self):
        registry = {
            "sources": [
                {"id": "official", "authority": "PRC", "exam": "LET", "source_type": "official", "authorized": True, "enabled": True, "url": "https://official.example/results"},
                {"id": "backup", "authority": "PRC", "exam": "LET", "source_type": "verified_third_party", "verified_by_owner": True, "enabled": True, "url": "https://backup.example/results"},
            ]
        }
        def fake_monitor(source):
            return {"source_id": source["id"], "status": "unreachable"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with patch("scraper.monitor.monitor_source", side_effect=fake_monitor):
                result = monitor_registry(path)
        self.assertEqual([item["source_id"] for item in result["results"]], ["official", "backup"])
        self.assertEqual(result["results"][1]["status"], "unreachable")


if __name__ == "__main__":
    unittest.main()
