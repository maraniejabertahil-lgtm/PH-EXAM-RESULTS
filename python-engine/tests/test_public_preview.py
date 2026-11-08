import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.public_preview import PublicPreviewCaptureError, load_public_preview_capture
from main import PipelineError, process_batch, publish_batch


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
                "2": {"name": "SMITH, JOHN B", "screenshot_sha256": self.screenshot_hash},
            },
        }
        self.visual = {
            "source": "https://drive.google.com/file/d/FILE123/preview",
            "pdf_downloaded": False, "access_controls_bypassed": False,
            "ocr_is_advisory_only": True, "human_visual_verification": "PENDING",
            "results": [{
                "sequence": 1, "expected_visible_text": "1 DOE, JANE A",
                "viewer_text_confirmed": True, "screenshot": "capture/page.png",
                "screenshot_sha256": self.screenshot_hash,
            }, {
                "sequence": 2, "expected_visible_text": "2 SMITH, JOHN B",
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

    def _configure_public_page_batch(self, content_mode="public_preview_capture"):
        article_url = "https://www.prc.gov.ph/article/result"
        content_url = "https://www.prc.gov.ph/results/let-2026-passers"
        allowed_hosts = ["www.prc.gov.ph"]
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"].append({
            "id": "PRC-TEST-PUBLIC-PAGE",
            "authority": "PRC",
            "exam": "LET-ELEMENTARY-2026",
            "year": 2026,
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "auto_acquire": True,
            "url": article_url,
            "public_content_urls": [content_url],
            "robots_policy_verified": True,
            "robots_policy_url": "https://www.prc.gov.ph/robots.txt",
            "public_preview": {
                "enabled": True,
                "method": "ordinary_public_page_ui",
                "allowed_hosts": allowed_hosts,
                "max_pages": 1,
            },
        })
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        self.batch.update({
            "official_article_url": article_url,
            "official_content_url": content_url,
            "public_preview_url": content_url,
            "public_preview_allowed_hosts": allowed_hosts,
            "public_preview_method": "ordinary_public_page_ui",
            "exam_specific_source_id": "PRC-TEST-PUBLIC-PAGE",
            "official_content_mode": content_mode,
        })
        if content_mode == "public_preview_capture":
            self.batch["capture_manifest"] = "capture/public-page-manifest.json"
            (self.root / "capture/public-page-manifest.json").write_text(
                json.dumps({"schema_version": 2}), encoding="utf-8"
            )
        else:
            self.batch["tier_failure_evidence"] = "capture/tier-failures.json"
            self.batch["static_png_ocr_mapping_key"] = "PRC-TEST:2026"
            (self.root / "capture/tier-failures.json").write_text(
                json.dumps({"synthetic": True}), encoding="utf-8"
            )
        return content_url, allowed_hosts

    def test_public_page_capture_uses_owner_approved_public_content_verifier(self):
        content_url, allowed_hosts = self._configure_public_page_batch()
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        records = [
            {"sequence_number": "1", "name": "DOE, JANE A"},
            {"sequence_number": "2", "name": "SMITH, JOHN B"},
        ]
        with (
            patch("main.verify_official_public_content_link") as verify,
            patch("main.load_public_preview_capture", return_value=(records, {"viewer_pages": 1})),
        ):
            result = process_batch("batch.json", root=self.root)
        verify.assert_called_once()
        self.assertEqual(verify.call_args.kwargs["content_url"], content_url)
        self.assertEqual(verify.call_args.kwargs["allowed_hosts"], allowed_hosts)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["manifest"]["record_count"], 2)

    def test_public_page_capture_rejects_batch_host_allowlist_mismatch(self):
        self._configure_public_page_batch()
        self.batch["public_preview_allowed_hosts"] = ["unapproved.example"]
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        with (
            patch("main.verify_official_public_content_link") as verify,
            patch("main.load_public_preview_capture") as load_capture,
        ):
            with self.assertRaisesRegex(PipelineError, "host allowlist"):
                process_batch("batch.json", root=self.root)
        verify.assert_not_called()
        load_capture.assert_not_called()

    def test_public_page_static_ocr_uses_official_public_content_verifier(self):
        content_url, allowed_hosts = self._configure_public_page_batch("static_png_ocr")
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        records = [
            {"sequence_number": "1", "name": "DOE, JANE A"},
            {"sequence_number": "2", "name": "SMITH, JOHN B"},
        ]
        with (
            patch("main.verify_official_public_content_link") as verify,
            patch("main.load_static_png_ocr_capture", return_value=(records, {"ocr_report": "synthetic"})),
        ):
            result = process_batch("batch.json", root=self.root)
        verify.assert_called_once()
        self.assertEqual(verify.call_args.kwargs["content_url"], content_url)
        self.assertEqual(verify.call_args.kwargs["allowed_hosts"], allowed_hosts)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["static_png_ocr"], {"ocr_report": "synthetic"})

    def test_review_bundle_contains_candidate_records_and_hash_verified_screenshots(self):
        from create_review_bundle import create_review_bundle

        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        bundle = create_review_bundle("batch.json", "capture/review-bundle.json", root=self.root)
        self.assertEqual(bundle["record_count"], 2)
        self.assertEqual(
            [sequence for item in bundle["evidence"] for sequence in item.get("sequence_numbers", [item.get("sequence_number")])],
            ["1", "2"],
        )
        self.assertTrue((self.root / "capture/review-bundle.json").is_file())

    def test_public_preview_publication_is_blocked_without_owner_receipt(self):
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(self.batch), encoding="utf-8")
        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "Owner visual-review receipt is required"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_source_approved_automation_publishes_any_greenlighted_exam_year(self):
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["auto_publish_after_greenlight"] = True
        registry["sources"][0]["owner_visual_review_required_exams"] = []
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        candidate = dict(self.batch, exam="LEPT-SECONDARY", year=2027)
        (self.root / "batch.json").write_text(json.dumps(candidate), encoding="utf-8")

        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            gitops.return_value.open_dataset_pr.return_value = {"pull_request_number": 12}
            gitops.return_value.dispatch_ci_and_merge.return_value = {"merged": True}
            result = publish_batch("batch.json", root=self.root)

        self.assertTrue(result["publication"]["merged"])
        gitops.return_value.open_dataset_pr.assert_called_once()
        published_manifest = json.loads(
            (self.root / "python-engine/artifacts/dataset/manifest.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("owner_review", published_manifest)
        self.assertEqual(published_manifest["exam"], "LEPT-SECONDARY")
        self.assertEqual(published_manifest["year"], 2027)

    def test_invalid_source_wide_auto_publish_policy_fails_closed(self):
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["auto_publish_after_greenlight"] = "true"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        (self.root / "batch.json").write_text(json.dumps(self.batch), encoding="utf-8")

        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "Publication policy stopped safely"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_auto_publish_holds_announced_count_mismatch_without_opening_gitops_pr(self):
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["auto_publish_after_greenlight"] = True
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        candidate = dict(self.batch, announced_count=3)
        (self.root / "batch.json").write_text(json.dumps(candidate), encoding="utf-8")

        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "Extraction counts do not match"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_required_owner_review_overrides_automatic_publication_allowlist(self):
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["auto_publish_after_greenlight"] = True
        registry["sources"][0]["auto_publish_exams"] = ["LET-ELEMENTARY-2026"]
        registry["sources"][0]["owner_visual_review_required_exams"] = ["LET-ELEMENTARY"]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        (self.root / "batch.json").write_text(json.dumps(self.batch), encoding="utf-8")

        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "Owner visual-review receipt is required"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_auto_publish_allowlist_is_year_specific(self):
        registry_path = self.root / "python-engine/config/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["auto_publish_exams"] = ["LET-ELEMENTARY-2026"]
        registry["sources"][0]["owner_visual_review_required_exams"] = []
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        (self.root / "batch.json").write_text(
            json.dumps(dict(self.batch, year=2027)), encoding="utf-8"
        )

        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "Owner visual-review receipt is required"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_matching_approved_owner_receipt_allows_public_preview_publication(self):
        canonical_records = [
            {"name": "DOE, JANE A", "sequence_number": "1"},
            {"name": "SMITH, JOHN B", "sequence_number": "2"},
        ]
        candidate_sha256 = hashlib.sha256(
            json.dumps(canonical_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        receipt = {
            "schema_version": 1,
            "authority": "PRC",
            "exam": "LET-ELEMENTARY",
            "year": 2026,
            "announced_count": 2,
            "record_count": 2,
            "candidate_sha256": candidate_sha256,
            "capture_manifest_sha256": digest(self.root / "capture/manifest.json"),
            "reviewer": "Owner",
            "source_evidence_reviewed": True,
            "records_reviewed": True,
            "decision": "approved",
            "notes": "",
            "reviewed_at": "2026-11-06T12:00:00Z",
        }
        (self.root / "capture/review.json").write_text(json.dumps(receipt), encoding="utf-8")
        batch = dict(self.batch, owner_review_receipt="capture/review.json")
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(batch), encoding="utf-8")
        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            gitops.return_value.open_dataset_pr.return_value = {"pull_request_number": 12}
            gitops.return_value.dispatch_ci_and_merge.return_value = {"merged": True}
            result = publish_batch("batch.json", root=self.root)
        self.assertTrue(result["publication"]["merged"])
        gitops.return_value.open_dataset_pr.assert_called_once()
        published_manifest = json.loads(
            (self.root / "python-engine/artifacts/dataset/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(published_manifest["owner_review"]["decision"], "approved")

    def test_owner_receipt_for_a_different_candidate_stops_publication(self):
        receipt = {
            "schema_version": 1,
            "authority": "PRC",
            "exam": "LET-ELEMENTARY",
            "year": 2026,
            "announced_count": 2,
            "record_count": 2,
            "candidate_sha256": "0" * 64,
            "capture_manifest_sha256": digest(self.root / "capture/manifest.json"),
            "reviewer": "Owner",
            "source_evidence_reviewed": True,
            "records_reviewed": True,
            "decision": "approved",
            "reviewed_at": "2026-11-06T12:00:00Z",
        }
        (self.root / "capture/review.json").write_text(json.dumps(receipt), encoding="utf-8")
        batch_path = self.root / "batch.json"
        batch_path.write_text(
            json.dumps(dict(self.batch, owner_review_receipt="capture/review.json")),
            encoding="utf-8",
        )
        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "does not match the exact validated candidate"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()

    def test_owner_receipt_requires_both_review_confirmations(self):
        canonical_records = [
            {"name": "DOE, JANE A", "sequence_number": "1"},
            {"name": "SMITH, JOHN B", "sequence_number": "2"},
        ]
        receipt = {
            "schema_version": 1,
            "authority": "PRC",
            "exam": "LET-ELEMENTARY",
            "year": 2026,
            "announced_count": 2,
            "record_count": 2,
            "candidate_sha256": hashlib.sha256(
                json.dumps(canonical_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "capture_manifest_sha256": digest(self.root / "capture/manifest.json"),
            "reviewer": "Owner",
            "decision": "approved",
            "reviewed_at": "2026-11-06T12:00:00Z",
        }
        (self.root / "capture/review.json").write_text(json.dumps(receipt), encoding="utf-8")
        (self.root / "batch.json").write_text(
            json.dumps(dict(self.batch, owner_review_receipt="capture/review.json")),
            encoding="utf-8",
        )
        with patch("main.verify_official_content_link"), patch("main.GitHubGitOps") as gitops:
            with self.assertRaisesRegex(PipelineError, "does not match the exact validated candidate"):
                publish_batch("batch.json", root=self.root)
        gitops.assert_not_called()


if __name__ == "__main__":
    unittest.main()
