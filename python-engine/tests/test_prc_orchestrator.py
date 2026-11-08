import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import process_batch
from prc_adapters import REGISTRY
from prc_orchestrator import greenlight, run, validate_event


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
