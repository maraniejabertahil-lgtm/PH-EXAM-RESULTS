import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import process_batch
from prc_adapters import REGISTRY
from prc_orchestrator import NeedsReviewError, _load_tier3_mapping_key, detect_layout_mapping, greenlight, run, validate_event


SOURCE = {
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


def event(exam_code="NLE"):
    return {
        "schema_version": "1",
        "source_id": SOURCE["id"],
        "article_url": "https://www.prc.gov.ph/article/nle-2026-results",
        "exam_code": exam_code,
        "exam_title": "Nursing Licensure Examination Results 2026",
        "exam_year": 2026,
        "list_type": "successful_examinees",
        "announced_count": 1,
        "content_urls": [{
            "url": "https://drive.google.com/file/d/public-results/view",
            "format": "pdf",
        }],
        "detected_at": "2026-11-03T00:00:00Z",
    }


class PRCOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry_path = self.root / "sources.json"
        self.mapping_path = self.root / "adapter_mappings.json"
        self.registry_path.write_text(json.dumps({"sources": [SOURCE]}), encoding="utf-8")
        self.mapping_path.write_text(json.dumps({}), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_detects_unambiguous_csv_layout_without_approving_it(self):
        raw = b'Sequence Number,Full Name\\n1,ALPHA BETA\\n2,GAMMA DELTA\\n'
        candidate = detect_layout_mapping(raw, 'csv')
        self.assertEqual(candidate['seq_col'], 'Sequence Number')
        self.assertEqual(candidate['name_col'], 'Full Name')
        self.assertEqual(candidate['detected_rows'], 2)

    def test_detects_unambiguous_json_layout(self):
        raw = json.dumps({'passers': [
            {'sequence': 1, 'name': 'ALPHA BETA'},
            {'sequence': 2, 'name': 'GAMMA DELTA'},
        ]}).encode('utf-8')
        candidate = detect_layout_mapping(raw, 'json')
        self.assertEqual(candidate['seq_key'], 'sequence')
        self.assertEqual(candidate['name_key'], 'name')

    def test_ambiguous_or_unlabelled_layout_fails_closed(self):
        ambiguous = b'Sequence,Seq No.,Name\\n1,1,ALPHA BETA\\n'
        unlabelled = b'Column A,Column B\\n1,ALPHA BETA\\n'
        self.assertIsNone(detect_layout_mapping(ambiguous, 'csv'))
        self.assertIsNone(detect_layout_mapping(unlabelled, 'csv'))
        self.assertIsNone(detect_layout_mapping(b'%PDF-1.7', 'pdf'))

    def test_tier3_mapping_accepts_both_downloadability_states_only_when_publicly_viewable(self):
        config_dir = self.root / "python-engine" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "static_png_ocr_mappings.json"
        base_mapping = {
            "enabled": True,
            "source_id": SOURCE["id"],
            "authority": "PRC",
            "exam": "NLE",
            "year": 2026,
            "official_source_url": SOURCE["url"],
            "public_viewability": {"publicly_viewable": True, "downloadable": True},
        }
        with patch("prc_orchestrator.HERE", self.root / "python-engine"):
            for downloadable in (True, False):
                mapping = dict(base_mapping)
                mapping["public_viewability"] = {
                    "publicly_viewable": True,
                    "downloadable": downloadable,
                }
                config_path.write_text(
                    json.dumps({"schema_version": 1, "mappings": {"NLE:2026": mapping}}),
                    encoding="utf-8",
                )
                self.assertEqual(
                    _load_tier3_mapping_key(SOURCE, event(), downloadable=downloadable),
                    "NLE:2026",
                )
            mapping = dict(base_mapping)
            mapping["public_viewability"] = {"publicly_viewable": False, "downloadable": False}
            config_path.write_text(
                json.dumps({"schema_version": 1, "mappings": {"NLE:2026": mapping}}),
                encoding="utf-8",
            )
            self.assertIsNone(_load_tier3_mapping_key(SOURCE, event(), downloadable=False))

    def test_publicly_viewable_but_non_downloadable_pdf_reaches_tier3(self):
        payload = event()
        specific = {
            "id": "PRC-NLE-2026-OFFICIAL-LIST",
            "authority": "PRC",
            "exam": "NLE-2026",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "auto_acquire": True,
            "url": payload["article_url"],
            "public_preview": {
                "enabled": True,
                "method": "ordinary_public_preview_ui",
                "max_pages": 1,
            },
            "drive_file_ids": ["public-results"],
        }
        self.registry_path.write_text(
            json.dumps({"sources": [SOURCE, specific]}), encoding="utf-8"
        )
        config_dir = self.root / "python-engine" / "config"
        config_dir.mkdir(parents=True)
        review = {
            "approved": True,
            "reviewer": "Owner",
            "reviewer_role": "owner",
            "reviewed_at": "2026-11-08T10:00:00Z",
            "evidence_ref": "owner-review-record-002",
        }
        mapping = {
            "enabled": True,
            "source_id": specific["id"],
            "authority": "PRC",
            "exam": "NLE",
            "year": 2026,
            "official_source_url": specific["url"],
            "record_pattern": r"^(?P<sequence>\d+) (?P<name>[A-Z]+, [A-Z]+ [A-Z])$",
            "mapping_review": review,
            "public_viewability_review": review,
            "access_compliance_review": review,
            "public_viewability": {
                "publicly_viewable": True,
                "downloadable": False,
                "evidence_ref": "public-viewer-capture-002",
            },
        }
        (config_dir / "static_png_ocr_mappings.json").write_text(
            json.dumps({"schema_version": 1, "mappings": {"NLE:2026": mapping}}),
            encoding="utf-8",
        )

        def capture_public_viewer(*, preview_url, output_dir, settings):
            output_dir.mkdir(parents=True, exist_ok=True)
            png = b"\x89PNG\r\n\x1a\n" + b"public-viewer-test"
            (output_dir / "page-1.png").write_bytes(png)
            (output_dir / "page-text-snapshots.jsonl").write_text(
                json.dumps({"page": 1, "text": "Page 1 of 1"}) + "\n",
                encoding="utf-8",
            )
            (output_dir / "capture-manifest.json").write_text(
                json.dumps({
                    "files": {
                        "screenshots": [{
                            "viewer_page": 1,
                            "path": "page-1.png",
                            "sha256": hashlib.sha256(png).hexdigest(),
                        }]
                    }
                }),
                encoding="utf-8",
            )
            return {
                "viewer_pages_captured": 1,
                "viewer_pages_expected": 1,
                "page_coverage_complete": True,
            }

        with patch("prc_orchestrator.HERE", self.root / "python-engine"):
            result = run(
                payload,
                self.root / "output",
                fetcher=lambda _url: (_ for _ in ()).throw(
                    NeedsReviewError("Official content request returned HTTP 403.")
                ),
                preview_verifier=lambda **_kwargs: {},
                preview_capturer=capture_public_viewer,
                registry_path=self.registry_path,
                repository_root=self.root,
            )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        batch = json.loads((self.root / "output" / "release-batch.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "ready_for_greenlight_pipeline")
        self.assertEqual(batch["official_content_mode"], "static_png_ocr")
        self.assertTrue(batch["publicly_viewable"])
        self.assertFalse(batch["content_downloadable"])
        self.assertEqual(batch["static_png_ocr_mapping_key"], "NLE:2026")

    def test_event_rejects_non_official_and_invalid_count_inputs(self):
        payload = event()
        payload["content_urls"][0]["url"] = "https://drive.google.com.evil.example/file.pdf"
        payload["announced_count"] = True

        errors = validate_event(payload)

        self.assertTrue(any("approved" in item for item in errors))
        self.assertTrue(any("positive integer" in item for item in errors))

    def test_generic_exam_identity_cannot_enter_automatic_acquisition(self):
        payload = event("LICENSURE-EXAM-RESULTS")

        errors = validate_event(payload)

        self.assertIn("generic exam code is not eligible for acquisition", errors)

    def test_disabled_exam_specific_source_blocks_acquisition(self):
        specific = {
            "id": "PRC-CPALE-2026-OFFICIAL-LIST",
            "authority": "PRC",
            "exam": "CPALE-2026",
            "source_type": "official",
            "authorized": True,
            "enabled": False,
            "auto_acquire": False,
            "url": "https://www.prc.gov.ph/article/nle-2026-results",
            "disable_reason": "Public preview requires sign-in.",
        }
        self.registry_path.write_text(
            json.dumps({"sources": [SOURCE, specific]}), encoding="utf-8"
        )
        payload = event("CPALE")
        payload["exam_title"] = "Certified Public Accountants Licensure Examination Results 2026"
        calls = []

        result = run(
            payload,
            self.root / "output",
            fetcher=lambda url: calls.append(url),
            registry_path=self.registry_path,
            cfg_path=self.mapping_path,
        )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertEqual(report["status"], "needs_review")
        self.assertIn("requires sign-in", report["reason"])
        self.assertEqual(calls, [])

    def test_current_cpale_registry_stops_when_public_preview_requires_sign_in(self):
        payload = event("CPALE")
        payload["exam_title"] = "Certified Public Accountants Licensure Examination Results 2026"
        payload["article_url"] = (
            "https://www.prc.gov.ph/article/october-2026-certified-public-accountants-"
            "licensure-examination-results-released-six-6"
        )
        payload["content_urls"][0]["url"] = (
            "https://drive.google.com/file/d/11-M7AU3RhcKtmyK37omcQQ1fErhdW5Rk/view"
        )

        def challenged_preview(**_kwargs):
            raise RuntimeError("public preview requires permission or human verification")

        import sys
        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        if str(extractor_dir) not in sys.path:
            sys.path.insert(0, str(extractor_dir))
        import pdf_parser
        fake_pdf = b"%PDF-1.7\\nsynthetic blank-text PDF"
        extraction = {
            "page_count": 1,
            "pages": [{"page_number": 1, "text": "", "tables": []}],
            "source_file_sha256": hashlib.sha256(fake_pdf).hexdigest(),
        }
        with patch.object(pdf_parser, "extract_pdf", return_value=extraction):
            result = run(
                payload,
                self.root / "output",
                fetcher=lambda _url: fake_pdf,
                preview_verifier=lambda **_kwargs: {},
                preview_capturer=challenged_preview,
            )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertEqual(report["tier1"]["status"], "unavailable")
        self.assertIn("requires permission or human verification", report["reason"])

    def test_sign_in_html_is_not_treated_as_a_pdf(self):
        html = b"<!doctype html><html><title>Sign in</title></html>"

        result = run(
            event(),
            self.root / "output",
            fetcher=lambda _url: html,
            registry_path=self.registry_path,
            cfg_path=self.mapping_path,
        )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("sign-in", report["reason"])
        self.assertFalse((self.root / "output" / "release-batch.json").exists())

    def test_malformed_pdf_is_reported_as_needs_review(self):
        self.mapping_path.write_text(
            json.dumps({"NLE:*:pdf": {"seq_idx": 0, "name_idx": 1}}),
            encoding="utf-8",
        )

        result = run(
            event(),
            self.root / "output",
            fetcher=lambda _url: b"%PDF-1.7\nmalformed",
            registry_path=self.registry_path,
            cfg_path=self.mapping_path,
        )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 3)
        self.assertIn("PDF extraction failed", report["reason"])

    def test_reviewed_mapping_creates_a_greenlight_batch_without_publishing(self):
        self.mapping_path.write_text(
            json.dumps({"NLE:*:pdf": {"seq_idx": 0, "name_idx": 1}}),
            encoding="utf-8",
        )
        fake_pdf = b"%PDF-1.7\nsynthetic test document"
        import sys
        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        if str(extractor_dir) not in sys.path:
            sys.path.insert(0, str(extractor_dir))
        import pdf_parser
        extraction = {
            "page_count": 1,
            "pages": [{"page_number": 1, "text": "SAMPLE NAME", "tables": []}],
            "source_file_sha256": hashlib.sha256(fake_pdf).hexdigest(),
        }
        with patch.object(pdf_parser, "extract_pdf", return_value=extraction), patch.dict(
            REGISTRY, {"pdf": lambda _raw, _mapping: [(1, "SAMPLE NAME")]}
        ):
            result = run(
                event(),
                self.root / "output",
                fetcher=lambda _url: fake_pdf,
                registry_path=self.registry_path,
                cfg_path=self.mapping_path,
            )

        report = json.loads((self.root / "output" / "report.json").read_text(encoding="utf-8"))
        batch = json.loads((self.root / "output" / "release-batch.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "ready_for_greenlight_pipeline")
        self.assertFalse(report["published"])
        self.assertEqual(batch["records"], [{"sequence_number": "1", "name": "SAMPLE NAME"}])
        self.assertTrue(batch["record_mapping_reviewed"])
        self.assertEqual(batch["source_pdf_sha256"], hashlib.sha256(fake_pdf).hexdigest())
        config_dir = self.root / "python-engine" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "sources.json").write_text(
            json.dumps({"sources": [SOURCE]}), encoding="utf-8"
        )
        with patch(
            "main.extract_pdf",
            return_value={"source_file_sha256": hashlib.sha256(fake_pdf).hexdigest()},
        ):
            processed = process_batch("output/release-batch.json", root=self.root)
        self.assertEqual(processed["report"]["greenlight_score"], 100)
        self.assertTrue((processed["dataset_dir"] / "manifest.json").is_file())

    def test_lept_level_is_preserved_in_the_publication_exam_identity(self):
        payload = event("LEPT")
        payload["exam_title"] = "Licensure Examination for Professional Teachers Elementary 2026"
        payload["result_level"] = "elementary"
        self.mapping_path.write_text(
            json.dumps({"LEPT:elementary:pdf": {"seq_idx": 0, "name_idx": 1}}),
            encoding="utf-8",
        )
        fake_pdf = b"%PDF-1.7\nsynthetic test document"
        import sys
        extractor_dir = Path(__file__).resolve().parents[1] / "extractor"
        if str(extractor_dir) not in sys.path:
            sys.path.insert(0, str(extractor_dir))
        import pdf_parser
        extraction = {
            "page_count": 1,
            "pages": [{"page_number": 1, "text": "SAMPLE NAME", "tables": []}],
            "source_file_sha256": hashlib.sha256(fake_pdf).hexdigest(),
        }
        with patch.object(pdf_parser, "extract_pdf", return_value=extraction), patch.dict(
            REGISTRY, {"pdf": lambda _raw, _mapping: [(1, "SAMPLE NAME")]}
        ):
            result = run(
                payload,
                self.root / "output",
                fetcher=lambda _url: fake_pdf,
                registry_path=self.registry_path,
                cfg_path=self.mapping_path,
            )

        batch = json.loads((self.root / "output" / "release-batch.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(batch["exam"], "LEPT-ELEMENTARY")
        self.assertEqual(batch["level"], "elementary")

    def test_greenlight_rejects_duplicate_names_and_sequence_gaps(self):
        score, failures = greenlight([(1, "Same Name"), (3, " same   name ")], announced=2)

        self.assertEqual(score, 0)
        self.assertIn("sequence numbers do not cover exactly 1 through the announced count", failures)
        self.assertIn("duplicate name at record 2", failures)

    def test_greenlight_rejects_malformed_record_shapes_without_crashing(self):
        score, failures = greenlight([(1, "SAMPLE NAME"), {"bad": "row"}], announced=2)

        self.assertEqual(score, 0)
        self.assertIn("invalid record shape at record 2", failures)


if __name__ == "__main__":
    unittest.main()
