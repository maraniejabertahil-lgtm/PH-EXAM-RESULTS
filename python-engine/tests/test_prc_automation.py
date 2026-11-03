import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.prc_automation import (
    PRCAutomationError, parse_official_article, acquire_public_drive_pdf,
    extract_sequence_name_pairs,
)


class PRCAutomationTests(unittest.TestCase):
    def test_article_parser_extracts_announced_counts_and_official_drive_lists(self):
        html = b"""
        <p>18,376 elementary teachers out of 32,796 examinees successfully passed.
        45,001 secondary teachers out of 61,561 examinees successfully passed.</p>
        <a href="https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view">List of Successful Examinees for Elementary</a>
        <a href="https://drive.google.com/file/d/1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7/view">List of Successful Examinees for Secondary</a>
        """
        result = parse_official_article("https://www.prc.gov.ph/article/sample", html)
        self.assertEqual(result["announced_counts"], {"elementary": 18376, "secondary": 45001})
        self.assertEqual([d["level"] for d in result["documents"]], ["elementary", "secondary"])

    def test_public_drive_download_accepts_only_pdf_from_official_article_link(self):
        article = "https://www.prc.gov.ph/article/sample"
        doc = "https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view"
        html = b'<a href="' + doc.encode() + b'">List of Successful Examinees for Elementary</a>'
        pdf = b"%PDF-1.7\nvalid fixture"
        with tempfile.TemporaryDirectory() as tmp, patch(
            "acquisition.prc_automation._robots_allow", return_value=True
        ), patch("acquisition.prc_automation._get", side_effect=[
            (200, {"Content-Type": "text/html"}, article, html),
            (200, {"Content-Type": "application/pdf"}, "https://drive.google.com/uc?export=download&id=1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE", pdf),
        ]):
            out = Path(tmp) / "roll.pdf"
            result = acquire_public_drive_pdf(
                official_article_url=article, linked_document_url=doc,
                output_path=out, attempt_log_path=Path(tmp) / "attempt.json",
            )
            self.assertEqual(out.read_bytes(), pdf)
            self.assertEqual(result["size_bytes"], len(pdf))

    def test_drive_html_interstitial_is_rejected_not_bypassed(self):
        article = "https://www.prc.gov.ph/article/sample"
        doc = "https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view"
        html = b'<a href="' + doc.encode() + b'">List of Successful Examinees for Elementary</a>'
        with tempfile.TemporaryDirectory() as tmp, patch(
            "acquisition.prc_automation._robots_allow", return_value=True
        ), patch("acquisition.prc_automation._get", side_effect=[
            (200, {"Content-Type": "text/html"}, article, html),
            (200, {"Content-Type": "text/html"}, "https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view", b"<html>Sign in</html>"),
        ]):
            with self.assertRaises(PRCAutomationError):
                acquire_public_drive_pdf(
                    official_article_url=article, linked_document_url=doc,
                    output_path=Path(tmp) / "roll.pdf", attempt_log_path=Path(tmp) / "attempt.json",
                )

    def test_sequence_extractor_requires_complete_unambiguous_mapping(self):
        extraction = {"pages": [{"tables": [[
            ["1", "DOE, JANE A"], ["2", "SMITH, JOHN B"], ["3", "GARCIA, ANA C"]
        ]]}]}
        rows = extract_sequence_name_pairs(extraction, 3)
        self.assertEqual([r["sequence_number"] for r in rows], ["1", "2", "3"])
        self.assertEqual(rows[1]["name"], "SMITH, JOHN B")

    def test_sequence_extractor_rejects_missing_sequence(self):
        extraction = {"pages": [{"tables": [[
            ["1", "DOE, JANE A"], ["3", "GARCIA, ANA C"]
        ]]}]}
        with self.assertRaises(PRCAutomationError):
            extract_sequence_name_pairs(extraction, 3)


if __name__ == "__main__":
    unittest.main()
