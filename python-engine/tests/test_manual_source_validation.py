import json
import unittest
from pathlib import Path

from manual_source_validation import build_manual_source_validation_report


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = json.loads((REPO_ROOT / "python-engine" / "config" / "sources.json").read_text(encoding="utf-8"))


class ManualSourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.source = next(
            item for item in REGISTRY["sources"]
            if item["id"] == "CSC-CSE-PPT-2026-08-09-REGION-V"
        )
        self.approved_id = self.source["drive_file_ids"][0]

    def test_accepts_exact_owner_approved_id_for_disabled_manual_source(self):
        report = build_manual_source_validation_report(
            REGISTRY,
            self.source["id"],
            self.approved_id,
            True,
            created_at="2026-11-03T00:00:00+00:00",
        )
        self.assertEqual(report["status"], "manual_source_confirmed_validation_only")
        self.assertEqual(report["source_id"], self.source["id"])
        self.assertEqual(report["drive_file_id"], self.approved_id)
        self.assertFalse(report["source_enabled"])
        self.assertTrue(report["manual_drop_required"])
        self.assertFalse(report["pdf_acquired"])
        self.assertFalse(report["extraction_performed"])
        self.assertFalse(report["published"])
        self.assertEqual(report["created_at"], "2026-11-03T00:00:00+00:00")

    def test_accepts_exact_official_prc_cpale_drive_id_for_manual_validation_only(self):
        source = next(
            item for item in REGISTRY["sources"]
            if item["id"] == "PRC-CPALE-2026-10-OFFICIAL-LIST"
        )
        report = build_manual_source_validation_report(
            REGISTRY,
            source["id"],
            "11-M7AU3RhcKtmyK37omcQQ1fErhdW5Rk",
            True,
            created_at="2026-11-05T00:00:00+00:00",
        )
        self.assertEqual(report["status"], "manual_source_confirmed_validation_only")
        self.assertEqual(report["authority"], "PRC")
        self.assertEqual(report["exam"], "CPALE-2026")
        self.assertFalse(report["source_enabled"])
        self.assertTrue(report["manual_drop_required"])
        self.assertFalse(report["pdf_acquired"])
        self.assertFalse(report["extraction_performed"])
        self.assertFalse(report["published"])

    def test_rejects_drive_id_not_in_exact_allowlist(self):
        with self.assertRaisesRegex(ValueError, "allowlist"):
            build_manual_source_validation_report(
                REGISTRY, self.source["id"], "1UnapprovedDriveFileID_2026", True
            )

    def test_rejects_enabled_source(self):
        enabled_source = {**self.source, "enabled": True}
        registry = {
            **REGISTRY,
            "sources": [
                enabled_source if item["id"] == self.source["id"] else item
                for item in REGISTRY["sources"]
            ],
        }
        with self.assertRaisesRegex(ValueError, "disabled source"):
            build_manual_source_validation_report(
                registry, self.source["id"], self.approved_id, True
            )

    def test_rejects_source_without_manual_drop_requirement(self):
        source = {**self.source, "manual_drop_required": False}
        registry = {
            **REGISTRY,
            "sources": [
                source if item["id"] == self.source["id"] else item
                for item in REGISTRY["sources"]
            ],
        }
        with self.assertRaisesRegex(ValueError, "manual handling"):
            build_manual_source_validation_report(
                registry, self.source["id"], self.approved_id, True
            )

    def test_rejects_missing_validation_only_confirmation(self):
        with self.assertRaisesRegex(ValueError, "confirmation"):
            build_manual_source_validation_report(
                REGISTRY, self.source["id"], self.approved_id, False
            )

    def test_rejects_malformed_drive_id(self):
        with self.assertRaisesRegex(ValueError, "format"):
            build_manual_source_validation_report(
                REGISTRY, self.source["id"], "not a drive id", True
            )

    def test_rejects_non_official_or_unauthorized_source(self):
        source = {**self.source, "authorized": False}
        registry = {
            **REGISTRY,
            "sources": [
                source if item["id"] == self.source["id"] else item
                for item in REGISTRY["sources"]
            ],
        }
        with self.assertRaisesRegex(ValueError, "authorized official"):
            build_manual_source_validation_report(
                registry, self.source["id"], self.approved_id, True
            )


if __name__ == "__main__":
    unittest.main()
