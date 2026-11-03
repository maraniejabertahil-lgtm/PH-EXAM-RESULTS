import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.public_preview import PublicPreviewCaptureError, load_public_preview_capture
from main import process_batch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicPreviewCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "python-engine/config").mkdir(parents=True)
        (self.root / "python-engine/config/sources.json").write_text(json.dumps({
            "sources": [{
                "id": "PRC-TEST", "authority": "PRC", "exam": "LET",
                "exam_scope": "all", "source_type": "official", "authorized": True,
                "enabled": True, "url": "https://www.prc.gov.ph/articles/exam-results",
                "allow_linked_drive_documents": True,
            }]
        }), encoding="utf-8")
        (self.root / "capture").mkdir()
        (self.root / "capture/layout.txt").write_text("public preview text", encoding="utf-8")
        (self.root / "capture/records.jsonl").write_text(
            '{"seq":"1","name":"DOE, JANE A"}\n{"seq":"2","name":"SMITH, JOHN B"}\n',
            encoding="utf-8",
        )
        screenshot = self.root / "capture/page.png"
        screenshot.write_bytes(b"test screenshot bytes")
        self.screenshot_hash = digest(screenshot)
        self.extraction = {
            "candidate_complete": True, "provenance": "official_direct",
            "announced_count": 2, "extracted_unique_sequences": 2,
            "missing_sequence_count": 0, "conflict_count": 0,
            "duplicate_sequence_count": 0, "out_of_range_record_count": 0,
            "duplicate_name_count": 0, "blank_name_count": 0,
            "unresolved_target_record_count": 0,
            "visual_verification_evidence": {
                "1": {"name": "DOE, JANE A", "screenshot_sha256": self.screenshot_hash},
            },
        }
        self.visual = {
            "source": "https://drive.google.com/file/d/FILE123/preview",
            "pdf_downloaded": False, "access_controls_bypassed": False,
            "ocr_is_advisory_only": True, "human_visual_verification": "PENDING",
            "results": [{
                "sequence": 1, "name": "DOE, JANE A", "expected_visible_text": "1 DOE, JANE A",
                "viewer_text_confirmed": True, "screenshot": "capture/page.png",
                "screenshot_sha256": self.screenshot_hash,
            }],
        }
        for name, value in (("extraction.json", self.extraction), ("visual.json", self.visual)):
            (self.root / "capture" / name).write_text(json.dumps(value), encoding="utf-8")
        self.manifest = {
            "schema_version": 1, "provenance": "official_direct",
            "public_preview_only": True,
            "official_article_url": "https://www.prc.gov.ph/article/result",
            "official_content_url": "https://drive.google.com/file/d/FILE123/view?usp=sharing",
            "public_preview_url": "https://drive.google.com/file/d/FILE123/preview",
            "viewer_pages_expected": 1, "viewer_pages_navigated": 1,
            "snapshots_retained": 1, "pdf_downloaded": False,
            "access_controls_bypassed": False,
            "files": {
                "layout_text": {"path": "capture/layout.txt", "sha256": digest(self.root / "capture/layout.txt")},
                "records_jsonl": {"path": "capture/records.jsonl", "sha256": digest(self.root / "capture/records.jsonl")},
                "extraction_report": {"path": "capture/extraction.json", "sha256": digest(self.root / "capture/extraction.json")},
                "visual_report": {"path": "capture/visual.json", "sha256": digest(self.root / "capture/visual.json")},
            },
        }
        (self.root / "capture/manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.batch = {
            "authority": "PRC", "exam": "LET-ELEMENTARY", "year": 2026,
            "announced_count": 2, "provenance": "official_direct",
            "source_id": "PRC-TEST", "publicly_released": True,
            "official_source_url": "https://www.prc.gov.ph/articles/exam-results",
            "official_article_url": self.manifest["official_article_url"],
            "official_content_url": self.manifest["official_content_url"],
            "public_preview_url": self.manifest["public_preview_url"],
            "official_content_mode": "public_preview_capture",
            "capture_manifest": "capture/manifest.json",
        }

    def test_public_preview_capture_enters_python_greenlight_without_claiming_manual_review(self):
        records, evidence = load_public_preview_capture(batch=self.batch, root=self.root)
        self.assertEqual(records, [
            {"sequence_number": "1", "name": "DOE, JANE A"},
            {"sequence_number": "2", "name": "SMITH, JOHN B"},
        ])
        self.assertEqual(evidence["visual_review_status"], "PENDING")

    def test_screenshot_hash_mismatch_fails_closed(self):
        (self.root / "capture/page.png").write_bytes(b"tampered")
        with self.assertRaises(PublicPreviewCaptureError):
            load_public_preview_capture(batch=self.batch, root=self.root)

    def test_pipeline_runs_greenlight_and_dataset_generation_without_gitops(self):
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        with patch("main.verify_official_content_link") as verify:
            result = process_batch("batch.json", root=self.root)
        verify.assert_called_once()
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["record_count"], 2)
        self.assertEqual(result["manifest"]["record_count"], 2)
        self.assertTrue((result["dataset_dir"] / "manifest.json").is_file())
        self.assertEqual(result["report"]["public_preview_capture"]["visual_review_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
