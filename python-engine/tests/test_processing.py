import unittest
from unittest.mock import patch

from processor.duplicates import find_duplicates
from processor.normalizer import normalize_name, normalize_record
from processor.validator import validate_batch, validate_record


class NormalizerTests(unittest.TestCase):
    def test_normalize_name_ignores_case_and_repeated_spaces(self):
        self.assertEqual(normalize_name("  JUAN   DELA CRUZ "), "juan dela cruz")

    def test_missing_name_is_not_converted_to_literal_none(self):
        record = normalize_record({"name": None}, "PRC", "LET", 2026)
        self.assertEqual(record["name"], "")
        self.assertEqual(record["search_key"], "")

    def test_normalize_record_preserves_original_display_name(self):
        record = normalize_record(
            {"name": "DELA CRUZ, JUAN A", "rating": "85.5", "region": "NCR", "seq": "4"},
            "PRC",
            "LET",
            2026,
        )
        self.assertEqual(record["name"], "DELA CRUZ, JUAN A")
        self.assertEqual(record["search_key"], "dela cruz, juan a")
        self.assertEqual(record["rating"], 85.5)
        self.assertEqual(record["seq"], 4)


class ValidationTests(unittest.TestCase):
    def test_valid_record(self):
        record = normalize_record({"name": "JUAN DELA CRUZ"}, "PRC", "LET", 2026)
        self.assertEqual(validate_record(record), [])
        self.assertTrue(validate_batch([record])["is_valid"])

    def test_invalid_authority_and_missing_name(self):
        record = normalize_record({"name": ""}, "OTHER", "LET", 2026)
        errors = validate_record(record)
        self.assertIn("authority must be PRC or CSC", errors)
        self.assertIn("name is required", errors)

    def test_empty_batch_is_not_valid(self):
        self.assertFalse(validate_batch([])["is_valid"])


class DuplicateTests(unittest.TestCase):
    def test_exact_duplicates_are_flagged_not_removed(self):
        rows = [
            normalize_record({"name": "JUAN DELA CRUZ"}, "PRC", "LET", 2026),
            normalize_record({"name": "Juan Dela Cruz"}, "PRC", "LET", 2026),
        ]
        result = find_duplicates(rows)
        self.assertEqual(len(result["exact_duplicates"]), 1)
        self.assertEqual(len(rows), 2)

    def test_fuzzy_comparisons_respect_per_record_candidate_cap(self):
        rows = [
            normalize_record({"name": f"COMMON NAME {index:05d}"}, "PRC", "LET", 2026)
            for index in range(100)
        ]
        with patch("processor.duplicates.SequenceMatcher") as matcher:
            matcher.return_value.ratio.return_value = 0.99
            result = find_duplicates(rows, max_candidates_per_record=3)
        self.assertLessEqual(matcher.call_count, len(rows) * 3)
        self.assertTrue(result["fuzzy_candidates"])

    def test_different_exams_are_not_compared(self):
        rows = [
            normalize_record({"name": "JUAN DELA CRUZ"}, "PRC", "LET", 2026),
            normalize_record({"name": "JUAN DELA CRUZ"}, "PRC", "NLE", 2026),
        ]
        self.assertEqual(find_duplicates(rows)["exact_duplicates"], [])


if __name__ == "__main__":
    unittest.main()
