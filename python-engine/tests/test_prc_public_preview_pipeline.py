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
from prc_orchestrator import NeedsReviewError, capture_public_preview, run
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


if __name__ == "__main__":
    unittest.main()
