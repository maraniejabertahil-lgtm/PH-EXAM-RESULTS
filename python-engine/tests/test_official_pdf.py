import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.official_pdf import AcquisitionError, acquire_official_pdf


class OfficialPDFAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = {
            "id": "PRC-TEST", "authority": "PRC", "exam": "LET",
            "source_type": "official", "authorized": True, "enabled": True,
            "url": "https://prc.gov.ph/articles/exam-results",
            "robots_policy_verified": True,
            "robots_policy_url": "https://prc.gov.ph/robots.txt",
        }
        self.article = "https://prc.gov.ph/article/example-results"
        self.document = "https://prc.gov.ph/files/results.pdf"
        self.output = self.root / "result.pdf"
        self.log = self.root / "attempts.json"

    def test_downloads_only_linked_same_origin_verified_pdf(self):
        pdf = b"%PDF-1.4\\nexample pdf bytes"
        responses = [
            (200, {"Content-Type": "text/html"}, self.article,
             b'<html><a href="/files/results.pdf">List of successful examinees</a></html>'),
            (200, {"Content-Type": "application/pdf"}, self.document, b""),
            (200, {"Content-Type": "application/pdf"}, self.document, pdf),
        ]
        with patch("acquisition.official_pdf._robots_allowed", return_value=True), patch(
            "acquisition.official_pdf._request", side_effect=responses
        ):
            result = acquire_official_pdf(
                source=self.source, article_url=self.article, document_url=self.document,
                output_path=self.output, attempt_log_path=self.log,
            )
        self.assertEqual(self.output.read_bytes(), pdf)
        self.assertEqual(result["provenance"], "official_direct")
        evidence = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertTrue(evidence["official_pdf_acquired"])
        self.assertEqual([x["method"] for x in evidence["attempts"]], ["HEAD", "GET"])

    def test_external_drive_link_is_logged_and_routes_to_manual_drop(self):
        drive_url = "https://drive.google.com/file/d/abcdefghijklmnop/view"
        with self.assertRaises(AcquisitionError):
            acquire_official_pdf(
                source=self.source, article_url=self.article, document_url=drive_url,
                output_path=self.output, attempt_log_path=self.log,
            )
        evidence = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(evidence["attempts"][0]["outcome"], "manual_drop_required_external_host")
        self.assertFalse(self.output.exists())

    def test_document_must_be_linked_from_the_official_article(self):
        responses = [
            (200, {"Content-Type": "text/html"}, self.article, b"<html><body>No PDF link</body></html>"),
        ]
        with patch("acquisition.official_pdf._robots_allowed", return_value=True), patch(
            "acquisition.official_pdf._request", side_effect=responses
        ):
            with self.assertRaises(AcquisitionError):
                acquire_official_pdf(
                    source=self.source, article_url=self.article, document_url=self.document,
                    output_path=self.output, attempt_log_path=self.log,
                )
        self.assertTrue(self.log.exists())
        self.assertFalse(self.output.exists())

    def test_robots_disallow_stops_before_article_or_pdf_requests(self):
        with patch("acquisition.official_pdf._robots_allowed", return_value=False), patch(
            "acquisition.official_pdf._request"
        ) as request:
            with self.assertRaises(AcquisitionError):
                acquire_official_pdf(
                    source=self.source, article_url=self.article, document_url=self.document,
                    output_path=self.output, attempt_log_path=self.log,
                )
        request.assert_not_called()
        self.assertTrue(self.log.exists())

    def test_human_verification_response_is_not_accepted_as_pdf(self):
        responses = [
            (200, {"Content-Type": "text/html"}, self.article,
             b'<a href="/files/results.pdf">PDF</a>'),
            (405, {"Content-Type": "text/html"}, self.document, b""),
            (403, {"Content-Type": "text/html"}, self.document, b"Checking your browser. Verify you are human."),
        ]
        with patch("acquisition.official_pdf._robots_allowed", return_value=True), patch(
            "acquisition.official_pdf._request", side_effect=responses
        ):
            with self.assertRaises(AcquisitionError):
                acquire_official_pdf(
                    source=self.source, article_url=self.article, document_url=self.document,
                    output_path=self.output, attempt_log_path=self.log,
                )
        evidence = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(evidence["attempts"][-1]["failure_class"], "human_verification_required")
        self.assertFalse(evidence["official_pdf_acquired"])


if __name__ == "__main__":
    unittest.main()
