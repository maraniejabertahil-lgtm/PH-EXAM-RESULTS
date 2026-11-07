from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.static_png_ocr import (
    StaticPngOcrError,
    load_static_png_ocr_capture,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-test-image"


def tsv_line(words, confidence=98):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = []
    for index, word in enumerate(words, start=1):
        rows.append(f"5\t1\t1\t1\t1\t{index}\t0\t0\t10\t10\t{confidence}\t{word}")
    return header + "\n" + "\n".join(rows) + "\n"


class StaticPngOcrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "python-engine" / "config").mkdir(parents=True)
        (self.root / "python-engine" / "artifacts").mkdir(parents=True)
        (self.root / "capture").mkdir()
        self.batch = {
            "authority": "PRC",
            "exam": "SYNTHETIC TEST",
            "year": 2026,
            "announced_count": 2,
            "provenance": "official_direct",
            "publicly_released": True,
            "source_id": "PRC-TEST",
            "official_source_url": "https://www.prc.gov.ph/results",
            "official_content_url": "https://drive.google.com/file/d/test/view",
            "official_article_url": "https://www.prc.gov.ph/results/article",
            "public_preview_url": "https://drive.google.com/file/d/test/preview",
            "official_content_mode": "static_png_ocr",
            "static_png_ocr_mapping_key": "PRC-TEST:2026",
            "static_png_ocr_manifest": "capture/manifest.json",
            "tier_failure_evidence": "capture/tier-failures.json",
            "access_challenge_detected": False,
        }
        review = {
            "approved": True,
            "reviewer": "Owner",
            "reviewer_role": "owner",
            "reviewed_at": "2026-11-07T10:00:00Z",
            "evidence_ref": "owner-review-record-001",
        }
        mapping = {
            "enabled": True,
            "source_id": "PRC-TEST",
            "authority": "PRC",
            "exam": "SYNTHETIC TEST",
            "year": 2026,
            "official_source_url": "https://www.prc.gov.ph/results",
            "record_pattern": r"^(?P<sequence>\d+) (?P<name>[A-Z]+, [A-Z]+ [A-Z])$",
            "language": "eng",
            "page_segmentation_mode": 6,
            "mapping_review": review,
            "access_directives_review": review,
            "reuse_terms_review": review,
        }
        (self.root / "python-engine" / "config" / "static_png_ocr_mappings.json").write_text(
            json.dumps({"schema_version": 1, "mappings": {"PRC-TEST:2026": mapping}}),
            encoding="utf-8",
        )
        failure_evidence = {
            "source_url": self.batch["official_source_url"],
            "access_challenge_detected": False,
            "tier1_direct_text": {"status": "unavailable", "reason": "No extractable text layer."},
            "tier2_rendered_dom": {"status": "unavailable", "reason": "No record text rendered in stable DOM."},
        }
        (self.root / "capture" / "tier-failures.json").write_text(
            json.dumps(failure_evidence), encoding="utf-8"
        )
        screenshots = []
        for page in (1, 2):
            path = self.root / "capture" / f"page-{page}.png"
            path.write_bytes(PNG + bytes([page]))
            screenshots.append({
                "page": page,
                "path": f"capture/page-{page}.png",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        manifest = {
            "schema_version": 1,
            "capture_method": "ordinary_public_preview_ui",
            "source_url": self.batch["public_preview_url"],
            "official_content_url": self.batch["official_content_url"],
            "public_preview_url": self.batch["public_preview_url"],
            "stable_viewport": True,
            "lossless_png": True,
            "access_challenge_detected": False,
            "screenshots": screenshots,
        }
        (self.root / "capture" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_high_confidence_capture_passes_to_greenlight_input(self):
        outputs = [
            tsv_line(["1", "DOE,", "JANE", "A"]),
            tsv_line(["2", "ROE,", "JOHN", "B"]),
        ]
        with patch("acquisition.static_png_ocr._tesseract_tsv", side_effect=outputs):
            records, evidence = load_static_png_ocr_capture(batch=self.batch, root=self.root)
        self.assertEqual(records, [
            {"sequence_number": "1", "name": "DOE, JANE A"},
            {"sequence_number": "2", "name": "ROE, JOHN B"},
        ])
        report = json.loads((self.root / evidence["report_path"]).read_text(encoding="utf-8"))
        self.assertTrue(report["ocr_gate_passed"])
        self.assertFalse(report["publication_allowed"])
        self.assertEqual(report["screenshot_count"], 2)
        self.assertEqual(len(report["ocr_tokens"]), 8)
        self.assertEqual(len(report["screenshots"][0]["ocr_tsv_sha256"]), 64)

    def test_low_confidence_token_is_held_for_human_review(self):
        outputs = [
            tsv_line(["1", "DOE,", "JANE", "A"], confidence=94),
            tsv_line(["2", "ROE,", "JOHN", "B"]),
        ]
        with patch("acquisition.static_png_ocr._tesseract_tsv", side_effect=outputs):
            with self.assertRaisesRegex(StaticPngOcrError, "below 95%"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        report = json.loads((self.root / "python-engine" / "artifacts" / "static-png-ocr-report.json").read_text())
        self.assertFalse(report["ocr_gate_passed"])
        self.assertFalse(report["publication_allowed"])
        self.assertTrue(report["low_confidence_tokens"])

    def test_tier3_rejects_missing_tier1_failure(self):
        evidence_path = self.root / "capture" / "tier-failures.json"
        evidence = json.loads(evidence_path.read_text())
        evidence["tier1_direct_text"]["status"] = "passed"
        evidence_path.write_text(json.dumps(evidence))
        with patch("acquisition.static_png_ocr._tesseract_tsv") as ocr:
            with self.assertRaisesRegex(StaticPngOcrError, "Tier 3 requires"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        ocr.assert_not_called()

    def test_tier3_rejects_access_challenge(self):
        self.batch["access_challenge_detected"] = True
        with patch("acquisition.static_png_ocr._tesseract_tsv") as ocr:
            with self.assertRaisesRegex(StaticPngOcrError, "access challenge"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        ocr.assert_not_called()

    def test_disabled_or_unreviewed_mapping_is_rejected(self):
        config_path = self.root / "python-engine" / "config" / "static_png_ocr_mappings.json"
        config_path.write_text(json.dumps({"schema_version": 1, "mappings": {}}))
        with patch("acquisition.static_png_ocr._tesseract_tsv") as ocr:
            with self.assertRaisesRegex(StaticPngOcrError, "No enabled"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        ocr.assert_not_called()

    def test_incomplete_sequence_coverage_is_rejected(self):
        outputs = [
            tsv_line(["1", "DOE,", "JANE", "A"]),
            tsv_line(["3", "ROE,", "JOHN", "B"]),
        ]
        with patch("acquisition.static_png_ocr._tesseract_tsv", side_effect=outputs):
            with self.assertRaisesRegex(StaticPngOcrError, "exact sequence coverage"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)

    def test_preview_url_must_reference_the_same_allowlisted_drive_file(self):
        self.batch["public_preview_url"] = "https://drive.google.com/file/d/another-file/preview"
        with patch("acquisition.static_png_ocr._tesseract_tsv") as ocr:
            with self.assertRaisesRegex(StaticPngOcrError, "exact allowlisted official Drive file"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        ocr.assert_not_called()

    def test_screenshot_hash_mismatch_is_rejected_before_ocr(self):
        manifest_path = self.root / "capture" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["screenshots"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        with patch("acquisition.static_png_ocr._tesseract_tsv") as ocr:
            with self.assertRaisesRegex(StaticPngOcrError, "SHA-256 mismatch"):
                load_static_png_ocr_capture(batch=self.batch, root=self.root)
        ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
