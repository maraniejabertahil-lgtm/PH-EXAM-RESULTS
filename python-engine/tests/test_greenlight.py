from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from processor.greenlight import validate_dataframe, validate_records, write_validation_report


class GreenlightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean_records = [
            {"sequence_number": "001", "name": "DELA CRUZ, JUAN A"},
            {"sequence_number": "002", "name": "SANTOS, MARIA B"},
            {"sequence_number": "003", "name": "GARCIA, JOSE C"},
        ]

    def test_clean_records_receive_100_greenlight(self) -> None:
        report = validate_records(self.clean_records, announced_count=3)
        self.assertEqual(report["status"], "GREENLIGHT")
        self.assertEqual(report["greenlight_score"], 100)
        self.assertTrue(report["publication_allowed"])
        self.assertTrue(all(report["checks"].values()))

    def test_announced_count_mismatch_fails_closed(self) -> None:
        report = validate_records(self.clean_records, announced_count=4)
        self.assertEqual(report["greenlight_score"], 0)
        self.assertFalse(report["checks"]["count_match"])
        self.assertFalse(report["publication_allowed"])

    def test_blank_names_fail(self) -> None:
        rows = [dict(self.clean_records[0]), dict(self.clean_records[1]), {"sequence_number": "003", "name": "   "}]
        report = validate_records(rows, announced_count=3)
        self.assertFalse(report["checks"]["zero_blanks"])
        self.assertEqual(report["metrics"]["blank_record_count"], 1)

    def test_duplicate_names_and_sequence_numbers_fail(self) -> None:
        rows = [
            {"sequence_number": "001", "name": "DOE, JOHN A"},
            {"sequence_number": "001", "name": "  doe,   john a "},
        ]
        report = validate_records(rows, announced_count=2)
        self.assertFalse(report["checks"]["zero_duplicates"])
        self.assertGreater(report["metrics"]["duplicate_name_record_count"], 0)
        self.assertGreater(report["metrics"]["duplicate_sequence_record_count"], 0)

    def test_missing_sequence_coverage_fails(self) -> None:
        rows = [
            {"sequence_number": "001", "name": "DOE, JOHN A"},
            {"sequence_number": "003", "name": "SMITH, JANE B"},
        ]
        report = validate_records(rows, announced_count=2)
        self.assertFalse(report["checks"]["complete_sequence_coverage"])
        self.assertEqual(report["issues"][-1]["missing_sequences"], [2])
        self.assertEqual(report["issues"][-1]["unexpected_sequences"], [3])

    def test_unexpected_symbols_and_invalid_sequence_fail(self) -> None:
        rows = [
            {"sequence_number": "1A", "name": "DOE ★, JOHN"},
        ]
        report = validate_records(rows, announced_count=1)
        self.assertFalse(report["checks"]["zero_anomalies"])
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("UNEXPECTED_NAME_CHARACTER", codes)
        self.assertIn("INVALID_SEQUENCE_NUMBER", codes)

    def test_unicode_names_and_punctuation_are_preserved(self) -> None:
        rows = [
            {"sequence_number": "1", "name": "ÑUÑEZ, JOSÉ D'ÁVILA"},
            {"sequence_number": "2", "name": "محمد، أحمد"},
        ]
        report = validate_records(rows, announced_count=2)
        self.assertEqual(report["greenlight_score"], 100)

    def test_third_party_fallback_requires_exact_independent_source_pairs(self) -> None:
        report = validate_records(
            self.clean_records,
            announced_count=3,
            provenance="third_party_fallback",
            comparison_records=self.clean_records,
            source_a_id="mirror-a",
            source_b_id="mirror-b",
        )
        self.assertEqual(report["greenlight_score"], 100)
        self.assertTrue(report["checks"]["two_independent_sources"])
        self.assertTrue(report["checks"]["exact_sequence_name_pair_agreement"])

    def test_third_party_fallback_without_second_source_fails(self) -> None:
        report = validate_records(
            self.clean_records, announced_count=3, provenance="third_party_fallback"
        )
        self.assertEqual(report["greenlight_score"], 0)
        self.assertFalse(report["checks"]["two_independent_sources"])
        self.assertFalse(report["checks"]["exact_sequence_name_pair_agreement"])

    def test_third_party_fallback_pair_mismatch_fails(self) -> None:
        second_source = [dict(row) for row in self.clean_records]
        second_source[1]["name"] = "SANTOS, MARIA X"
        report = validate_records(
            self.clean_records,
            announced_count=3,
            provenance="third_party_fallback",
            comparison_records=second_source,
            source_a_id="mirror-a",
            source_b_id="mirror-b",
        )
        self.assertEqual(report["greenlight_score"], 0)
        self.assertFalse(report["checks"]["exact_sequence_name_pair_agreement"])

    def test_third_party_fallback_rejects_same_source_identity(self) -> None:
        report = validate_records(
            self.clean_records,
            announced_count=3,
            provenance="third_party_fallback",
            comparison_records=self.clean_records,
            source_a_id="same-mirror",
            source_b_id="same-mirror",
        )
        self.assertEqual(report["greenlight_score"], 0)
        self.assertFalse(report["checks"]["two_independent_sources"])

    def test_third_party_comparison_source_must_also_pass_greenlight(self) -> None:
        second_source = [dict(row) for row in self.clean_records]
        second_source[2]["sequence_number"] = "004"
        report = validate_records(
            self.clean_records,
            announced_count=3,
            provenance="third_party_fallback",
            comparison_records=second_source,
            source_a_id="mirror-a",
            source_b_id="mirror-b",
        )
        self.assertEqual(report["greenlight_score"], 0)
        self.assertFalse(report["checks"]["exact_sequence_name_pair_agreement"])

    def test_dataframe_validation_preserves_leading_zeroes(self) -> None:
        frame = pd.DataFrame({"raw_seq": pd.Series(["001", "002"], dtype="string"), "raw_name": ["DOE, JOHN", "SMITH, JANE"]})
        report = validate_dataframe(
            frame, announced_count=2, name_column="raw_name", sequence_column="raw_seq"
        )
        self.assertEqual(report["greenlight_score"], 100)

    def test_dataframe_requires_explicit_columns(self) -> None:
        frame = pd.DataFrame({"name": ["DOE, JOHN"]})
        with self.assertRaises(ValueError):
            validate_dataframe(frame, announced_count=1, name_column="name", sequence_column="seq")

    def test_invalid_announced_count_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_records(self.clean_records, announced_count=-1)

    def test_report_is_written_without_passer_names(self) -> None:
        report = validate_records(self.clean_records, announced_count=3)
        with tempfile.TemporaryDirectory() as directory:
            path = write_validation_report(report, Path(directory) / "validation.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["greenlight_score"], 100)
        self.assertNotIn("DELA CRUZ", json.dumps(saved))


if __name__ == "__main__":
    unittest.main()
