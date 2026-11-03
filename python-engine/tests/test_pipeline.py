import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import PipelineError, process_batch


class ProcessingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "python-engine" / "config").mkdir(parents=True)
        (self.root / "python-engine" / "config" / "sources.json").write_text(json.dumps({
            "sources": [{
                "id": "PRC-LET-TEST", "authority": "PRC", "exam": "LET",
                "source_type": "official", "authorized": True, "enabled": True,
                "url": "https://www.prc.gov.ph/articles/exam-results",
                "allow_linked_drive_documents": True,
            }]
        }), encoding="utf-8")
        (self.root / "official.pdf").write_bytes(b"%PDF-1.4\\nfixture\\n")
        self.base = {
            "authority": "PRC", "exam": "LET", "year": 2026,
            "announced_count": 2, "provenance": "official_direct", "source_id": "PRC-LET-TEST", "publicly_released": True,
            "official_source_url": "https://www.prc.gov.ph/articles/exam-results",
            "official_document_url": "https://www.prc.gov.ph/files/example.pdf",
            "source_pdf": "official.pdf", "record_mapping_reviewed": True,
            "records": [
                {"name": "DOE, JANE A", "sequence_number": "001"},
                {"name": "SMITH, JOHN B", "sequence_number": "002"},
            ],
        }
        self.batch = self.root / "batch.json"

    def run_batch(self, data):
        self.batch.write_text(json.dumps(data), encoding="utf-8")
        with patch("main.extract_pdf", return_value={
            "source_file_sha256": "a" * 64,
            "extraction_status": "raw_extraction_complete",
        }):
            return process_batch("batch.json", root=self.root)

    def test_clean_official_batch_builds_manifest(self):
        result = self.run_batch(self.base)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertTrue((result["dataset_dir"] / "manifest.json").is_file())

    def test_pipeline_acquires_official_pdf_when_no_local_pdf_is_supplied(self):
        batch = dict(self.base)
        batch.pop("source_pdf")
        batch["official_article_url"] = "https://www.prc.gov.ph/article/example-results"
        self.batch.write_text(json.dumps(batch), encoding="utf-8")
        acquired = {
            "path": str(self.root / "official.pdf"),
            "sha256": "a" * 64,
            "attempt_log_path": str(self.root / "attempts.json"),
        }
        with patch("main.acquire_official_pdf", return_value=acquired) as acquire, patch(
            "main.extract_pdf", return_value={"source_file_sha256": "a" * 64}
        ):
            result = process_batch("batch.json", root=self.root)
        acquire.assert_called_once()
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["official_attempt_log"], acquired["attempt_log_path"])

    def test_owner_reviewed_official_content_handoff_needs_no_pdf(self):
        batch = dict(self.base)
        batch.pop("source_pdf")
        batch.pop("official_document_url")
        batch["official_content_mode"] = "manual_handoff"
        batch["official_content_url"] = "https://drive.google.com/file/d/approved-file-id/view?usp=sharing"
        batch["official_article_url"] = "https://www.prc.gov.ph/article/example-results"
        batch["official_content_reviewed"] = True
        batch["record_mapping_reviewed"] = True
        self.batch.write_text(json.dumps(batch), encoding="utf-8")
        evidence = self.root / "python-engine/artifacts/official-content-evidence.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with patch("main.verify_official_content_link") as verify, patch("main.acquire_official_pdf") as acquire, patch("main.extract_pdf") as extract:
            verify.return_value = {"provenance": "official_direct"}
            result = process_batch("batch.json", root=self.root)
        verify.assert_called_once()
        acquire.assert_not_called()
        extract.assert_not_called()
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertIsNone(result["report"]["source_pdf_sha256"])
        self.assertTrue(evidence.parent.exists())

    def test_manual_official_content_handoff_requires_owner_review(self):
        batch = dict(self.base)
        batch.pop("source_pdf")
        batch.pop("official_document_url")
        batch["official_content_mode"] = "manual_handoff"
        batch["official_content_url"] = "https://drive.google.com/file/d/approved-file-id/view"
        batch["official_article_url"] = "https://www.prc.gov.ph/article/example-results"
        batch["official_content_reviewed"] = False
        self.batch.write_text(json.dumps(batch), encoding="utf-8")
        with self.assertRaises(PipelineError):
            process_batch("batch.json", root=self.root)

    def test_reviewed_pdf_table_mapping_flows_into_greenlight(self):
        batch = dict(self.base)
        batch.pop("records")
        batch.pop("record_mapping_reviewed")
        batch["table_mapping_reviewed"] = True
        batch["table_mapping"] = {
            "table_indexes": [0], "header_rows": 1,
            "name_column": 0, "sequence_column": 1,
        }
        self.batch.write_text(json.dumps(batch), encoding="utf-8")
        extraction = {
            "source_file_sha256": "a" * 64,
            "pages": [{
                "page_number": 1,
                "tables": [[
                    ["NAME", "SEQ"],
                    ["DOE, JANE A", "001"],
                    ["SMITH, JOHN B", "002"],
                ]],
            }],
        }
        with patch("main.extract_pdf", return_value=extraction):
            result = process_batch("batch.json", root=self.root)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["record_count"], 2)

    def test_missing_sequence_fails_before_dataset_creation(self):
        broken = dict(self.base)
        broken["records"] = [
            {"name": "DOE, JANE A", "sequence_number": "001"},
            {"name": "SMITH, JOHN B", "sequence_number": "003"},
        ]
        with self.assertRaises(PipelineError):
            self.run_batch(broken)
        self.assertFalse((self.root / "python-engine/artifacts/dataset/manifest.json").exists())

    def test_unreviewed_mapping_is_rejected(self):
        with self.assertRaises(PipelineError):
            self.run_batch(dict(self.base, record_mapping_reviewed=False))

    def test_repository_path_traversal_is_rejected(self):
        with self.assertRaises(PipelineError):
            self.run_batch(dict(self.base, source_pdf="../outside.pdf"))


if __name__ == "__main__":
    unittest.main()


class OfficialContentHandoffUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name) / "content-evidence.json"
        self.source = {
            "id": "PRC-TEST", "authority": "PRC", "exam": "LET",
            "source_type": "official", "authorized": True, "enabled": True,
            "url": "https://www.prc.gov.ph/articles/exam-results",
            "robots_policy_verified": True,
            "robots_policy_url": "https://www.prc.gov.ph/robots.txt",
            "allow_linked_drive_documents": True,
        }
        self.article = "https://www.prc.gov.ph/article/sample-results"
        self.content = "https://drive.google.com/file/d/public-file/view?usp=sharing"

    def test_verifies_official_article_link_without_fetching_drive(self):
        from acquisition.official_content import verify_official_content_link
        html = f'<html><a href="{self.content}">List of Successful Examinees</a></html>'.encode()
        with patch("acquisition.official_content._robots_allowed", return_value=True), patch(
            "acquisition.official_content._request",
            return_value=(200, {"Content-Type": "text/html; charset=utf-8"}, self.article, html),
        ) as request:
            evidence = verify_official_content_link(
                source=self.source, article_url=self.article,
                content_url=self.content, evidence_path=self.evidence,
            )
        self.assertTrue(evidence["official_article_link_verified"])
        self.assertFalse(evidence["content_body_downloaded_by_automation"])
        self.assertFalse(evidence["pdf_downloaded"])
        self.assertTrue(self.evidence.is_file())
        request.assert_called_once()

    def test_rejects_content_url_not_linked_by_official_article(self):
        from acquisition.official_content import OfficialContentError, verify_official_content_link
        html = b'<html><a href="https://drive.google.com/file/d/other/view">Other</a></html>'
        with patch("acquisition.official_content._robots_allowed", return_value=True), patch(
            "acquisition.official_content._request",
            return_value=(200, {"Content-Type": "text/html"}, self.article, html),
        ):
            with self.assertRaises(OfficialContentError):
                verify_official_content_link(
                    source=self.source, article_url=self.article,
                    content_url=self.content, evidence_path=self.evidence,
                )

    def test_rejects_drive_link_when_registry_opt_in_is_disabled(self):
        from acquisition.official_content import OfficialContentError, verify_official_content_link
        source = dict(self.source, allow_linked_drive_documents=False)
        with self.assertRaises(OfficialContentError):
            verify_official_content_link(
                source=source, article_url=self.article,
                content_url=self.content, evidence_path=self.evidence,
            )
