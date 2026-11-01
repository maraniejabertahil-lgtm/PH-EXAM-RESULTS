import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scraper.monitor import load_registry, monitor_registry, monitor_source


class FakeRangeResponse:
    status = 206

    def __init__(self):
        self.headers = {
            "Content-Length": "1",
            "Content-Range": "bytes 0-0/98765",
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://official.example/results"

    def read(self, size=-1):
        return b"x"


class FakeRedirectResponse:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://official.example:8443/results"


class SourceMonitorTests(unittest.TestCase):
    def test_rejects_redirect_to_different_https_port(self):
        source = {
            "id": "official-port-redirect",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://official.example/results",
        }
        with patch("scraper.monitor.urlopen", return_value=FakeRedirectResponse()):
            result = monitor_source(source)
        self.assertEqual(result["status"], "redirect_rejected")

    def test_range_fallback_uses_total_content_range_size(self):
        source = {
            "id": "official-range",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://official.example/results",
        }
        head_error = HTTPError(
            source["url"], 405, "Method Not Allowed", {}, None
        )
        with patch(
            "scraper.monitor.urlopen",
            side_effect=[head_error, FakeRangeResponse()],
        ):
            result = monitor_source(source)
        self.assertEqual(result["status"], "reachable")
        self.assertEqual(result["content_length"], "98765")

    def test_range_fallback_does_not_mistake_one_byte_for_full_size(self):
        source = {
            "id": "official-range-no-total",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://official.example/results",
        }
        response = FakeRangeResponse()
        response.headers.pop("Content-Range")
        head_error = HTTPError(
            source["url"], 405, "Method Not Allowed", {}, None
        )
        with patch(
            "scraper.monitor.urlopen",
            side_effect=[head_error, response],
        ):
            result = monitor_source(source)
        self.assertIsNone(result["content_length"])

    def test_registry_rejects_unsafe_ids_and_embedded_url_credentials(self):
        invalid_sources = [
            {
                "id": "unsafe/source",
                "authority": "PRC",
                "exam": "LET",
                "source_type": "official",
                "authorized": True,
                "enabled": True,
                "url": "https://official.example/results",
            },
            {
                "id": "official-source",
                "authority": "PRC",
                "exam": "LET",
                "source_type": "official",
                "authorized": True,
                "enabled": True,
                "url": "https://user:password@official.example/results",
            },
            {
                "id": "official-non-text-url",
                "authority": "PRC",
                "exam": "LET",
                "source_type": "official",
                "authorized": True,
                "enabled": True,
                "url": 12345,
            },
            {
                "id": "official-invalid-exam",
                "authority": "PRC",
                "exam": "LET/2026",
                "source_type": "official",
                "authorized": True,
                "enabled": True,
                "url": "https://official.example/results",
            },
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.json"
            for source in invalid_sources:
                path.write_text(
                    json.dumps({"schema_version": 1, "sources": [source]}),
                    encoding="utf-8",
                )
                with self.subTest(source_id=source["id"]):
                    with self.assertRaises(ValueError):
                        load_registry(path)

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
