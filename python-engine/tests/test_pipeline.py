import json
import tempfile
import unittest
from pathlib import Path

from main import PipelineError, process_batch


class ProcessingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "python-engine").mkdir()
        (self.root / "official.pdf").write_bytes(b"%PDF-1.4\\nfixture\\n")
        self.base = {
            "authority": "PRC", "exam": "LET", "year": 2026,
            "announced_count": 2, "provenance": "official_direct",
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
        return process_batch("batch.json", root=self.root)

    def test_clean_official_batch_builds_manifest(self):
        result = self.run_batch(self.base)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertTrue((result["dataset_dir"] / "manifest.json").is_file())

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
