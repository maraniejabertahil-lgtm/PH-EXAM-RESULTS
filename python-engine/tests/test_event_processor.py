import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper.event_processor import DetectedSourceError, process_detected_pdf


class DetectedSourceProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = self.root / "sources.json"
        self.source = {
            "id": "CSC-CSE-PPT-2026",
            "authority": "CSC",
            "exam": "CSE-PPT",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://csc.gov.ph/examination-advisories/",
            "file_format": "pdf",
            "auto_acquire": True,
        }
        self.registry.write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))
        self.payload = {
            "source_id": self.source["id"],
            "authority": "CSC",
            "exam": "CSE-PPT",
            "detected_url": "https://csc.gov.ph/files/result.pdf",
            "content_type": "application/pdf",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_rejects_cross_origin_pdf(self):
        self.payload["detected_url"] = "https://drive.google.com/file/result.pdf"
        with self.assertRaisesRegex(DetectedSourceError, "Google Drive URL"):
            process_detected_pdf(self.payload, self.registry, self.root / "report.json")

    def test_rejects_metadata_mismatch(self):
        self.payload["exam"] = "OTHER"
        with self.assertRaisesRegex(DetectedSourceError, "does not match"):
            process_detected_pdf(self.payload, self.registry, self.root / "report.json")

    def test_does_not_download_without_owner_auto_acquire_flag(self):
        self.source["auto_acquire"] = False
        self.registry.write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))
        with patch("scraper.event_processor.download_approved_file") as download:
            report = process_detected_pdf(self.payload, self.registry, self.root / "report.json")
        download.assert_not_called()
        self.assertEqual(report["status"], "awaiting_owner_acquisition_approval")
        self.assertFalse((self.root / "report.pdf").exists())

    def test_accepts_only_an_exact_approved_google_drive_file_id(self):
        self.source["drive_file_ids"] = ["1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l"]
        self.registry.write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))
        self.payload["detected_url"] = (
            "https://drive.google.com/uc?export=download&id=1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l"
        )
        def fake_download(source, destination):
            Path(destination).write_bytes(b"%PDF-1.7 test")
            return {"sha256": "b" * 64, "size_bytes": 12}
        with patch("scraper.event_processor.download_approved_file", side_effect=fake_download):
            with patch("scraper.event_processor.extract_pdf_lines", return_value=["CSC result"]):
                report = process_detected_pdf(self.payload, self.registry, self.root / "drive-review.json")
        self.assertEqual(report["status"], "text_extracted_manual_review_required")
        self.assertEqual(report["lines"], ["CSC result"])

    def test_rejects_unapproved_google_drive_file_id(self):
        self.source["drive_file_ids"] = ["approved-file-id-123456"]
        self.registry.write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))
        self.payload["detected_url"] = (
            "https://drive.google.com/uc?export=download&id=another-file-id-123456"
        )
        with self.assertRaisesRegex(DetectedSourceError, "exact owner-approved file ID"):
            process_detected_pdf(self.payload, self.registry, self.root / "rejected.json")

    def test_extracts_only_after_approved_download(self):
        def fake_download(source, destination):
            Path(destination).write_bytes(b"%PDF-1.7 test")
            return {"sha256": "a" * 64, "size_bytes": 12}
        with patch("scraper.event_processor.download_approved_file", side_effect=fake_download):
            with patch("scraper.event_processor.extract_pdf_lines", return_value=["Example line"]):
                report = process_detected_pdf(self.payload, self.registry, self.root / "report.json")
        self.assertEqual(report["status"], "text_extracted_manual_review_required")
        self.assertEqual(report["lines"], ["Example line"])
        self.assertTrue(report["manual_review_required"])
        self.assertIn("not passer-record extraction", report["notice"])


if __name__ == "__main__":
    unittest.main()
