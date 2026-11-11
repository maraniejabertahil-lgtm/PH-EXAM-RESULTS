import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from publish_lept_pair import (  # noqa: E402
    EXPECTED_COUNTS,
    TOTAL_EXPECTED,
    build_combined_greenlight_report,
    _temporarily_enable_reviewed_sources,
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
            exam: {
                "reviewer": "Owner",
                "decision": "approved",
                "source_evidence_reviewed": True,
                "records_reviewed": True,
                "candidate_sha256": "a" * 64,
                "capture_manifest_sha256": "b" * 64,
            }
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

    def test_only_exact_owner_reviewed_source_entries_are_temporarily_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "python-engine" / "config"
            config.mkdir(parents=True)
            entries = []
            batches = {}
            for exam in EXPECTED_COUNTS:
                source_id = f"PRC-{exam}-2026-03-OFFICIAL-LIST"
                article = f"https://prc.gov.ph/article/{exam.lower()}"
                entries.append({
                    "id": source_id,
                    "authority": "PRC",
                    "exam": f"{exam}-2026",
                    "source_type": "official",
                    "authorized": True,
                    "enabled": False,
                    "auto_acquire": False,
                    "robots_policy_verified": False,
                    "robots_policy_url": "https://prc.gov.ph/robots.txt",
                    "url": article,
                    "public_preview": {"enabled": True},
                })
                batches[exam] = {
                    "exam_specific_source_id": source_id,
                    "official_article_url": article,
                }
            entries.append({
                "id": "UNRELATED-SOURCE",
                "authority": "PRC",
                "exam": "CPALE-2026",
                "source_type": "official",
                "authorized": True,
                "enabled": False,
            })
            registry_path = config / "sources.json"
            original = json.dumps({"sources": entries}, indent=2).encode("utf-8")
            registry_path.write_bytes(original)
            path, saved = _temporarily_enable_reviewed_sources(batches=batches, root=root)
            updated = json.loads(path.read_text(encoding="utf-8"))["sources"]
            by_id = {item["id"]: item for item in updated}
            for exam in EXPECTED_COUNTS:
                source = by_id[f"PRC-{exam}-2026-03-OFFICIAL-LIST"]
                self.assertTrue(source["enabled"])
                self.assertTrue(source["auto_acquire"])
                self.assertTrue(source["robots_policy_verified"])
            self.assertFalse(by_id["UNRELATED-SOURCE"]["enabled"])
            self.assertEqual(saved, original)
            path.write_bytes(saved)
            self.assertEqual(path.read_bytes(), original)

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
        reviews["LEPT-SECONDARY"] = {
            "decision": "approved",
            "reviewer": "",
            "source_evidence_reviewed": True,
            "records_reviewed": True,
            "candidate_sha256": "a" * 64,
            "capture_manifest_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(PipelineError, "incomplete or not approved"):
            build_combined_greenlight_report(self.records, reviews)


if __name__ == "__main__":
    unittest.main()
