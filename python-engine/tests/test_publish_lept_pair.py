import sys
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from publish_lept_pair import (  # noqa: E402
    EXPECTED_COUNTS,
    TOTAL_EXPECTED,
    build_combined_greenlight_report,
)
from main import PipelineError  # noqa: E402


def sample_records(count):
    return [
        {"sequence_number": str(index), "name": f"TEST, PERSON {index}"}
        for index in range(1, count + 1)
    ]


class CombinedLeptPublicationTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            exam: sample_records(count)
            for exam, count in EXPECTED_COUNTS.items()
        }
        self.reviews = {
            exam: {"reviewer": "Owner", "decision": "approved"}
            for exam in EXPECTED_COUNTS
        }

    def test_combined_report_requires_both_owner_approved_levels(self):
        report = build_combined_greenlight_report(self.records, self.reviews)
        self.assertEqual(report["status"], "GREENLIGHT")
        self.assertEqual(report["greenlight_score"], 100)
        self.assertTrue(report["publication_allowed"])
        self.assertEqual(report["record_count"], TOTAL_EXPECTED)
        self.assertEqual(report["announced_count"], TOTAL_EXPECTED)
        self.assertEqual(report["provenance"], "official_direct")
        self.assertEqual(len(report["records_sha256"]), 64)
        self.assertTrue(all(report["checks"].values()))

    def test_combined_report_rejects_missing_level(self):
        records = dict(self.records)
        records.pop("LEPT-SECONDARY")
        with self.assertRaisesRegex(PipelineError, "Both LEPT levels"):
            build_combined_greenlight_report(records, self.reviews)

    def test_combined_report_rejects_incomplete_record_count(self):
        records = dict(self.records)
        records["LEPT-ELEMENTARY"] = records["LEPT-ELEMENTARY"][:-1]
        with self.assertRaisesRegex(PipelineError, "record count"):
            build_combined_greenlight_report(records, self.reviews)

    def test_combined_report_rejects_missing_owner_reviewer(self):
        reviews = dict(self.reviews)
        reviews["LEPT-SECONDARY"] = {"decision": "approved", "reviewer": ""}
        with self.assertRaisesRegex(PipelineError, "no reviewer"):
            build_combined_greenlight_report(self.records, reviews)


if __name__ == "__main__":
    unittest.main()
