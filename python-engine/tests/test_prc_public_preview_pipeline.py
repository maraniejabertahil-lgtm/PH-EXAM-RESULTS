import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from acquisition.official_content import OfficialContentError, verify_official_preview_link
from acquisition.public_preview import (
    PublicPreviewCaptureError,
    parse_public_preview_snapshots,
)
from main import PipelineError, process_batch
from prc_orchestrator import NeedsReviewError, capture_public_preview, load_public_preview_mapping, run
from playwright.sync_api import Error as PlaywrightError


ARTICLE_URL = "https://www.prc.gov.ph/article/cpale-2026-results"
CONTENT_URL = "https://drive.google.com/file/d/CPALE_FILE_2026/view?usp=sharing"
PREVIEW_URL = "https://drive.google.com/file/d/CPALE_FILE_2026/preview"
MAPPING_KEY = "CPALE:2026:public_preview"
MAPPING = {
    "record_pattern": r"^\s*(?P<sequence>\d+)[.)]?\s+(?P<name>.+?)\s*$",
    "require_comma_in_name": True,
}
LISTING_SOURCE = {
    "id": "PRC-EXAM-RESULTS-HOMEPAGE",
    "authority": "PRC",
    "exam": "LICENSURE-EXAM-RESULTS",
    "exam_scope": "all",
    "source_type": "official",
    "authorized": True,
    "enabled": True,
    "url": "https://www.prc.gov.ph/articles/exam-results",
    "discover_official_result_articles": True,
    "auto_acquire": True,
    "allow_linked_drive_documents": True,
}
EXAM_SOURCE = {
    "id": "PRC-CPALE-2026-10-OFFICIAL-LIST",
    "authority": "PRC",
    "exam": "CPALE-2026",
    "source_type": "official",
    "authorized": True,
    "enabled": True,
    "auto_acquire": True,
    "url": ARTICLE_URL,
    "drive_file_ids": ["CPALE_FILE_2026"],
    "allow_linked_drive_documents": True,
    "robots_policy_verified": True,
    "robots_policy_url": "https://www.prc.gov.ph/robots.txt",
    "public_preview": {
        "enabled": True,
        "method": "ordinary_public_preview_ui",
        "shards": 4,
        "allowed_hosts": ["drive.google.com"],
        "max_pages": 4,
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fake_capture(preview_url: str, output_dir: Path, settings: dict) -> dict:
    del preview_url, settings
    output_dir.mkdir(parents=True, exist_ok=True)
    texts = [
        "Page 1 of 2\n1. ABAD, KRIZZIA CAMILLE CALDERON",
        "Page 2 of 2\n1. ABAD, KRIZZIA CAMILLE CALDERON\n2. ABAD, MARIAN ALEXANDRA VALDEZ",
    ]
    page_index = []
    screenshots = []
    for page_number, text in enumerate(texts, start=1):
        screenshot_name = f"page-{page_number:04d}.png"
        screenshot = output_dir / screenshot_name
        screenshot.write_bytes(f"fake screenshot {page_number}".encode())
        screenshot_hash = digest(screenshot)
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        screenshots.append({
            "viewer_page": page_number,
            "path": screenshot_name,
            "sha256": screenshot_hash,
        })
        page_index.append({
            "viewer_page": page_number,
            "sha256": text_hash,
            "screenshot_sha256": screenshot_hash,
        })
    (output_dir / "page-capture-index.json").write_text(
        json.dumps(page_index), encoding="utf-8"
    )
    (output_dir / "page-text-snapshots.jsonl").write_text(
        "".join(
            json.dumps({"viewer_page": number, "text": text}) + "\n"
            for number, text in enumerate(texts, start=1)
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "capture_method": "ordinary_public_preview_ui",
        "viewer_pages_expected": 2,
        "viewer_pages_captured": 2,
        "page_coverage_complete": True,
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "files": {"screenshots": screenshots},
    }
    (output_dir / "capture-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return manifest


class PRCPublicPreviewPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = self.root / "python-engine/config"
        config.mkdir(parents=True)
        (config / "sources.json").write_text(
            json.dumps({"sources": [LISTING_SOURCE, EXAM_SOURCE]}),
            encoding="utf-8",
        )
        (config / "adapter_mappings.json").write_text(
            json.dumps({MAPPING_KEY: MAPPING}),
            encoding="utf-8",
        )
        self.event = {
            "schema_version": "1",
            "source_id": LISTING_SOURCE["id"],
            "article_url": ARTICLE_URL,
            "exam_code": "CPALE",
            "exam_title": "Certified Public Accountants Licensure Examination Results 2026",
            "exam_year": 2026,
            "list_type": "successful_examinees",
            "announced_count": 2,
            "content_urls": [{"url": CONTENT_URL, "format": "pdf"}],
            "detected_at": "2026-11-03T00:00:00Z",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_lept_reviewed_mapping_matches_visible_roster_line(self):
        event = {
            "exam_code": "LEPT",
            "result_level": "elementary",
            "exam_year": 2026,
        }
        key, mapping = load_public_preview_mapping(
            event,
            cfg_path=Path(__file__).resolve().parents[1] / "config" / "adapter_mappings.json",
        )
        self.assertEqual(key, "LEPT:elementary:2026:public_preview")
        self.assertEqual(
            parse_public_preview_snapshots(
                [{"text": "Page 2 of 368\\n51 ABAPO, REJEAN DUMAYON"}],
                mapping,
            ),
            [(51, "ABAPO, REJEAN DUMAYON")],
        )

    def test_browser_capture_uses_sequential_bounded_shards(self):
        import sys

        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        sys.path.insert(0, str(extractor_dir))
        import public_preview_shards

        with patch.object(public_preview_shards, "capture_shard") as capture, patch.object(
            public_preview_shards, "merge_shards", return_value={"page_coverage_complete": True}
        ) as merge:
            result = capture_public_preview(
                preview_url=PREVIEW_URL,
                output_dir=self.root / "capture",
                settings=EXAM_SOURCE["public_preview"],
            )
        self.assertTrue(result["page_coverage_complete"])
        self.assertEqual(
            [call.kwargs["shard"] for call in capture.call_args_list],
            [0, 1, 2, 3],
        )
        self.assertTrue(
            all(call.kwargs["shard_count"] == 4 for call in capture.call_args_list)
        )
        merge.assert_called_once_with(shard_count=4, output_dir=self.root / "capture")

    def test_browser_crash_is_reported_as_a_safe_review_stop(self):
        import sys

        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        sys.path.insert(0, str(extractor_dir))
        import public_preview_shards

        with patch.object(
            public_preview_shards,
            "capture_shard",
            side_effect=PlaywrightError("Target crashed"),
        ):
            with self.assertRaisesRegex(NeedsReviewError, "browser capture stopped safely"):
                capture_public_preview(
                    preview_url=PREVIEW_URL,
                    output_dir=self.root / "capture",
                    settings=EXAM_SOURCE["public_preview"],
                )

    def test_cumulative_snapshots_are_deduplicated_by_matching_sequence(self):
        snapshots = [
            {"text": "Page 1 of 2"},
            {"text": "1. ABAD, KRIZZIA CAMILLE CALDERON"},
            {
                "text": (
                    "1. ABAD, KRIZZIA CAMILLE CALDERON\n"
                    "2. ABAD, MARIAN ALEXANDRA VALDEZ"
                )
            },
        ]
        self.assertEqual(
            parse_public_preview_snapshots(snapshots, MAPPING),
            [
                (1, "ABAD, KRIZZIA CAMILLE CALDERON"),
                (2, "ABAD, MARIAN ALEXANDRA VALDEZ"),
            ],
        )

    def test_cumulative_snapshots_reject_conflicting_or_same_page_duplicates(self):
        with self.assertRaises(PublicPreviewCaptureError):
            parse_public_preview_snapshots(
                [
                    {"text": "1. ABAD, KRIZZIA CAMILLE CALDERON"},
                    {"text": "1. ABAD, KRIZZIA C. CALDERON"},
                ],
                MAPPING,
            )
        with self.assertRaises(PublicPreviewCaptureError):
            parse_public_preview_snapshots(
                [
                    {
                        "text": (
                            "1. ABAD, KRIZZIA CAMILLE CALDERON\n"
                            "1. ABAD, KRIZZIA CAMILLE CALDERON"
                        )
                    }
                ],
                MAPPING,
            )

    def run_capture(
        self, *, content_url=CONTENT_URL, capturer=write_fake_capture,
        pdf_extraction=None, cfg_path=None, fetcher=None,
    ):
        import sys

        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        if str(extractor_dir) not in sys.path:
            sys.path.insert(0, str(extractor_dir))
        import pdf_parser

        self.event["content_urls"][0]["url"] = content_url
        extraction = pdf_extraction or {
            "page_count": 1,
            "pages": [{"page_number": 1, "text": "", "tables": []}],
            "source_file_sha256": "a" * 64,
        }
        with patch.object(pdf_parser, "extract_pdf", return_value=extraction):
            return run(
                self.event,
                self.root / "output",
                fetcher=fetcher or (lambda _url: b"%PDF-1.4\nsynthetic"),
                preview_verifier=lambda **_kwargs: {},
                preview_capturer=capturer,
                registry_path=self.root / "python-engine/config/sources.json",
                cfg_path=cfg_path or self.root / "python-engine/config/adapter_mappings.json",
                repository_root=self.root,
            )

    def test_unapproved_drive_file_id_stops_before_capture(self):
        capturer = Mock()
        result = self.run_capture(
            content_url="https://drive.google.com/file/d/OTHER/view",
            capturer=capturer,
        )
        report = json.loads((self.root / "output/report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("not allowlisted", report["reason"])
        capturer.assert_not_called()
        self.assertFalse((self.root / "output/release-batch.json").exists())

    def test_access_challenge_stops_without_a_batch(self):
        def challenged(**_kwargs):
            raise RuntimeError("public preview requires permission or human verification")

        result = self.run_capture(capturer=challenged)
        report = json.loads((self.root / "output/report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("human verification", report["reason"])
        self.assertFalse((self.root / "output/release-batch.json").exists())

    def test_full_capture_evidence_enters_greenlight_without_network(self):
        self.assertEqual(self.run_capture(), 0)
        with patch("main.verify_official_preview_link") as verify:
            result = process_batch("output/release-batch.json", root=self.root)
        verify.assert_called_once()
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["record_count"], 2)
        self.assertEqual(
            result["report"]["public_preview_capture"]["visual_review_status"],
            "PENDING",
        )

    def test_tampered_screenshot_fails_closed_before_greenlight(self):
        self.assertEqual(self.run_capture(), 0)
        (self.root / "output/public-preview-capture/page-0001.png").write_bytes(b"tampered")
        with patch("main.verify_official_preview_link"):
            with self.assertRaises(PipelineError):
                process_batch("output/release-batch.json", root=self.root)

    def test_tier1_readable_pdf_without_reviewed_mapping_stops_before_preview(self):
        capturer = Mock()
        result = self.run_capture(
            capturer=capturer,
            pdf_extraction={
                "page_count": 1,
                "pages": [{"page_number": 1, "text": "Official result text", "tables": []}],
                "source_file_sha256": "b" * 64,
            },
        )
        report = json.loads((self.root / "output/report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("readable PDF content", report["reason"])
        self.assertEqual(report["tier1"]["status"], "available")
        capturer.assert_not_called()
        self.assertFalse((self.root / "output/release-batch.json").exists())

    def test_tier1_reviewed_pdf_mapping_takes_priority_over_preview(self):
        config_path = self.root / "python-engine/config/adapter_mappings.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["CPALE:*:pdf"] = {"seq_idx": 0, "name_idx": 1}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        capturer = Mock()
        with patch.dict(
            "prc_orchestrator.REGISTRY",
            {"pdf": Mock(return_value=[(1, "DOE, JANE"), (2, "ROE, JOHN")])},
        ):
            result = self.run_capture(
                capturer=capturer,
                pdf_extraction={
                    "page_count": 1,
                    "pages": [{"page_number": 1, "text": "1 DOE, JANE", "tables": []}],
                    "source_file_sha256": "c" * 64,
                },
            )
        batch = json.loads((self.root / "output/release-batch.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(batch["official_content_mode"], "pdf_text_extraction")
        capturer.assert_not_called()

    def test_tier2_readable_text_without_mapping_stops_without_ocr(self):
        config_path = self.root / "python-engine/config/adapter_mappings.json"
        config_path.write_text("{}", encoding="utf-8")
        result = self.run_capture()
        report = json.loads((self.root / "output/report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("rendered readable DOM text", report["reason"])
        self.assertEqual(report["tier2"]["status"], "available")
        self.assertFalse((self.root / "output/release-batch.json").exists())

    def test_tier3_is_not_enabled_without_owner_reviewed_mapping(self):
        def blank_preview(**kwargs):
            manifest = write_fake_capture(**kwargs)
            capture_dir = kwargs["output_dir"]
            snapshots = [
                {"viewer_page": 1, "text": "Page 1 of 2"},
                {"viewer_page": 2, "text": "Page 2 of 2"},
            ]
            (capture_dir / "page-text-snapshots.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in snapshots),
                encoding="utf-8",
            )
            return manifest

        result = self.run_capture(capturer=blank_preview)
        report = json.loads((self.root / "output/report.json").read_text(encoding="utf-8"))
        evidence = json.loads((self.root / "output/tier-failures.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertEqual(evidence["tier1_direct_text"]["status"], "unavailable")
        self.assertEqual(evidence["tier2_rendered_dom"]["status"], "unavailable")
        self.assertIn("Tier 3 remains disabled", report["reason"])
        self.assertFalse((self.root / "output/release-batch.json").exists())

    def test_preview_source_verifier_requires_robot_permission_and_exact_article_link(self):
        evidence_path = self.root / "preview-evidence.json"
        article = f'<html><a href="{CONTENT_URL}">List of successful examinees</a></html>'.encode()
        with patch("acquisition.official_content._robots_allowed", return_value=True) as robots, patch(
            "acquisition.official_content._request",
            return_value=(200, {"Content-Type": "text/html; charset=utf-8"}, ARTICLE_URL, article),
        ) as request:
            evidence = verify_official_preview_link(
                source=EXAM_SOURCE,
                article_url=ARTICLE_URL,
                content_url=CONTENT_URL,
                evidence_path=evidence_path,
            )
        robots.assert_called_once()
        request.assert_called_once()
        self.assertFalse(evidence["public_preview_content_downloaded"])
        self.assertFalse(evidence["pdf_downloaded"])
        self.assertTrue(evidence_path.is_file())

    def test_preview_source_verifier_stops_when_robots_disallows_article(self):
        with patch("acquisition.official_content._robots_allowed", return_value=False), patch(
            "acquisition.official_content._request"
        ) as request:
            with self.assertRaises(OfficialContentError):
                verify_official_preview_link(
                    source=EXAM_SOURCE,
                    article_url=ARTICLE_URL,
                    content_url=CONTENT_URL,
                    evidence_path=self.root / "preview-evidence.json",
                )
        request.assert_not_called()

    def test_preview_source_verifier_rejects_unlinked_drive_file(self):
        article = b'<html><a href="https://drive.google.com/file/d/OTHER/view">Results</a></html>'
        with patch("acquisition.official_content._robots_allowed", return_value=True), patch(
            "acquisition.official_content._request",
            return_value=(200, {"Content-Type": "text/html"}, ARTICLE_URL, article),
        ):
            with self.assertRaises(OfficialContentError):
                verify_official_preview_link(
                    source=EXAM_SOURCE,
                    article_url=ARTICLE_URL,
                    content_url=CONTENT_URL,
                    evidence_path=self.root / "preview-evidence.json",
                )


    def test_vet_public_view_only_roster_uses_tier2_after_direct_html_response(self):
        article_url = "https://www.prc.gov.ph/article/november-2026-veterinarians-computer-based-licensure-examination-results-released-one-1"
        content_url = "https://drive.google.com/file/d/1y6DT1PZG8lLlqlAHAqPVoKB3cKKy74l0/view?usp=sharing"
        file_id = "1y6DT1PZG8lLlqlAHAqPVoKB3cKKy74l0"
        vet_source = {
            "id": "PRC-VET-2026-11-OFFICIAL-LIST",
            "authority": "PRC",
            "exam": "VET-2026",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "auto_acquire": True,
            "url": article_url,
            "drive_file_ids": [file_id],
            "allow_linked_drive_documents": True,
            "robots_policy_verified": True,
            "robots_policy_url": "https://www.prc.gov.ph/robots.txt",
            "public_preview": {
                "enabled": True,
                "method": "ordinary_public_preview_ui",
                "shards": 4,
                "allowed_hosts": ["drive.google.com"],
                "max_pages": 30,
            },
        }
        registry_path = self.root / "python-engine/config/sources.json"
        registry_path.write_text(
            json.dumps({"sources": [LISTING_SOURCE, vet_source]}),
            encoding="utf-8",
        )
        mapping = {
            "record_pattern": r"^\s*(?P<sequence>\d{1,4})\s+(?P<name>[^\W\d_][\w\s,.'’()\-]+?)\s*$",
            "require_comma_in_name": True,
        }
        mapping_path = self.root / "python-engine/config/adapter_mappings.json"
        mapping_path.write_text(
            json.dumps({"VET:2026:public_preview": mapping}),
            encoding="utf-8",
        )
        payload = {
            "schema_version": "1",
            "source_id": LISTING_SOURCE["id"],
            "article_url": article_url,
            "exam_code": "VET",
            "exam_title": "November 2026 Veterinarians Computer-Based Licensure Examination Results Released in One (1) Working Day",
            "exam_year": 2026,
            "list_type": "successful_examinees",
            "announced_count": 2,
            "content_urls": [{"url": content_url, "format": "pdf"}],
            "detected_at": "2026-11-11T00:00:00Z",
        }
        calls = []

        def capture_vet_preview(*, preview_url, output_dir, settings):
            self.assertEqual(preview_url, content_url.replace("/view?usp=sharing", "/preview"))
            self.assertEqual(settings["max_pages"], 30)
            output_dir.mkdir(parents=True, exist_ok=True)
            texts = [
                "Page 1 of 2\n1 ABAD, JEM ELYZA SALAZAR",
                "Page 2 of 2\n2 ABAD, MARIA LOURDES SALAZAR",
            ]
            screenshots = []
            page_index = []
            for page_number, page_text in enumerate(texts, start=1):
                screenshot_name = f"page-{page_number:04d}.png"
                screenshot = output_dir / screenshot_name
                screenshot.write_bytes(f"vet-preview-page-{page_number}".encode())
                screenshot_hash = digest(screenshot)
                screenshots.append({
                    "viewer_page": page_number,
                    "path": screenshot_name,
                    "sha256": screenshot_hash,
                })
                page_index.append({
                    "viewer_page": page_number,
                    "sha256": hashlib.sha256(page_text.encode()).hexdigest(),
                    "screenshot_sha256": screenshot_hash,
                })
            (output_dir / "page-capture-index.json").write_text(
                json.dumps(page_index), encoding="utf-8"
            )
            (output_dir / "page-text-snapshots.jsonl").write_text(
                "".join(
                    json.dumps({"viewer_page": number, "text": page_text}) + "\n"
                    for number, page_text in enumerate(texts, start=1)
                ),
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "capture_method": "ordinary_public_preview_ui",
                "viewer_pages_expected": 2,
                "viewer_pages_captured": 2,
                "page_coverage_complete": True,
                "pdf_downloaded": False,
                "access_controls_bypassed": False,
                "files": {"screenshots": screenshots},
            }
            (output_dir / "capture-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            calls.append("captured")
            return manifest

        def verify_preview(**_kwargs):
            calls.append("verified")
            return {}

        result = run(
            payload,
            self.root / "vet-output",
            fetcher=lambda _url: b"<!doctype html><html><title>Google Drive viewer</title></html>",
            preview_verifier=verify_preview,
            preview_capturer=capture_vet_preview,
            registry_path=registry_path,
            cfg_path=mapping_path,
            repository_root=self.root,
        )
        report = json.loads((self.root / "vet-output/report.json").read_text(encoding="utf-8"))
        batch = json.loads((self.root / "vet-output/release-batch.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(calls, ["verified", "captured"])
        self.assertEqual(report["status"], "ready_for_greenlight_pipeline")
        self.assertEqual(report["tier1"]["status"], "unavailable")
        self.assertFalse(report["tier1"]["downloadable"])
        self.assertEqual(report["tier2"]["status"], "available")
        self.assertEqual(report["records"], 2)
        self.assertEqual(report["greenlight"], 100)
        self.assertEqual(batch["official_content_mode"], "public_preview_capture")
        self.assertFalse(report["published"])
        records = [
            json.loads(line)
            for line in (self.root / "vet-output/public-preview-capture/records.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            records,
            [
                {"seq": "1", "name": "ABAD, JEM ELYZA SALAZAR"},
                {"seq": "2", "name": "ABAD, MARIA LOURDES SALAZAR"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
