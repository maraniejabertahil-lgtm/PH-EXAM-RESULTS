import unittest

from publisher.gitops_manager import (
    GitOpsError,
    validate_artifacts,
    validate_greenlight,
)


def good_report():
    return {
        "status": "GREENLIGHT",
        "greenlight_score": 100,
        "publication_allowed": True,
        "provenance": "official_direct",
        "record_count": 2,
        "announced_count": 2,
        "records_sha256": "a" * 64,
        "checks": {
            "count_match": True,
            "zero_blanks": True,
            "zero_duplicates": True,
            "zero_anomalies": True,
            "complete_sequence_coverage": True,
        },
    }


class GitOpsGateTests(unittest.TestCase):
    def test_accepts_complete_official_greenlight(self):
        validate_greenlight(good_report())

    def test_rejects_score_below_100(self):
        report = good_report()
        report["greenlight_score"] = 99
        with self.assertRaises(GitOpsError):
            validate_greenlight(report)

    def test_rejects_false_check_even_when_score_claims_100(self):
        report = good_report()
        report["checks"]["complete_sequence_coverage"] = False
        with self.assertRaises(GitOpsError):
            validate_greenlight(report)

    def test_rejects_count_mismatch(self):
        report = good_report()
        report["announced_count"] = 3
        with self.assertRaises(GitOpsError):
            validate_greenlight(report)

    def test_fallback_requires_two_distinct_sources(self):
        report = good_report()
        report["provenance"] = "third_party_fallback"
        report["source_a_id"] = "source-a"
        report["source_b_id"] = "source-a"
        with self.assertRaises(GitOpsError):
            validate_greenlight(report)

    def test_fallback_accepts_distinct_sources(self):
        report = good_report()
        report["provenance"] = "third_party_fallback"
        report["source_a_id"] = "source-a"
        report["source_b_id"] = "source-b"
        validate_greenlight(report)

    def test_only_public_data_artifacts_are_allowed(self):
        self.assertEqual(
            validate_artifacts({"public/data/prc/example.json": b'{"data":[]}'}),
            {"public/data/prc/example.json": b'{"data":[]}'},
        )

    def test_rejects_path_traversal(self):
        with self.assertRaises(GitOpsError):
            validate_artifacts({"public/data/../../.github/workflows/x.yml": b"x"})

    def test_rejects_files_outside_dataset_directory(self):
        with self.assertRaises(GitOpsError):
            validate_artifacts({"README.md": b"not a dataset"})

    def test_rejects_empty_artifact(self):
        with self.assertRaises(GitOpsError):
            validate_artifacts({"public/data/empty.json": b""})


if __name__ == "__main__":
    unittest.main()
