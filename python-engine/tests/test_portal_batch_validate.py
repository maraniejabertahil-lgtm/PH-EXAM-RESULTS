import json
import tempfile
import unittest
from pathlib import Path

from portal_batch_validate import PortalBatchError, validate_portal_batch


class PortalBatchValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = {
            "id": "CSC-CSE-PORTAL",
            "authority": "CSC",
            "exam": "CSE-PPT-2026-03",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://exam.csc.gov.ph/list_passers?type_id=1",
            "content_access_mode": "owner_reviewed_portal_handoff",
        }
        config = self.root / "python-engine/config"
        config.mkdir(parents=True)
        (config / "sources.json").write_text(
            json.dumps({"sources": [self.source]}), encoding="utf-8"
        )
        self.batch = {
            "authority": "CSC",
            "exam": "CSE-PPT-2026-03",
            "year": 2026,
            "announced_count": 2,
            "source_id": "CSC-CSE-PORTAL",
            "official_source_url": self.source["url"],
            "official_portal_url": self.source["url"],
            "publicly_released": True,
            "provenance": "official_direct",
            "official_content_mode": "owner_reviewed_portal_handoff",
            "official_content_reviewed": True,
            "record_mapping_reviewed": True,
            "records": [
                {"name": "SAMPLE ALPHA", "sequence_number": "001"},
                {"name": "SAMPLE BETA", "sequence_number": "002"},
            ],
        }

    def test_clean_synthetic_batch_reaches_greenlight(self):
        result = validate_portal_batch(self.batch, repository_root=self.root)
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertTrue((self.root / "python-engine/artifacts/dataset/manifest.json").is_file())

    def test_unreviewed_batch_is_rejected(self):
        batch = dict(self.batch, official_content_reviewed=False)
        with self.assertRaises(PortalBatchError):
            validate_portal_batch(batch, repository_root=self.root)

    def test_wrong_source_url_is_rejected(self):
        batch = dict(self.batch, official_source_url="https://example.org/list_passers")
        with self.assertRaises(PortalBatchError):
            validate_portal_batch(batch, repository_root=self.root)


if __name__ == "__main__":
    unittest.main()
