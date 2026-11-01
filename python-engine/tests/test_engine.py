import json
import tempfile
import unittest
from pathlib import Path

from prediction.release_predictor import predict_next_release
from processor.duplicates import find_duplicates
from processor.normalizer import normalize_record
from processor.validator import validate_batch
from publisher.json_builder import MAX_SHARD_BYTES, build_public_datasets
from publisher.manifest import build_manifest


class ProcessingTests(unittest.TestCase):
    def test_normalization_preserves_display_name_and_normalizes_search_key(self):
        record = normalize_record(
            {"name": "  Dela\u00a0Cruz, Juan A  ", "rating": "85.5", "seq": "12"},
            "PRC",
            "LET",
            2026,
        )
        self.assertEqual(record["name"], "Dela\u00a0Cruz, Juan A")
        self.assertEqual(record["search_key"], "dela cruz, juan a")
        self.assertEqual(record["rating"], 85.5)
        self.assertEqual(record["seq"], 12)

    def test_validation_rejects_invalid_rating(self):
        record = normalize_record(
            {"name": "Sample Passer", "rating": "not-a-number"},
            "PRC",
            "LET",
            2026,
        )
        report = validate_batch([record])
        self.assertFalse(report["is_valid"])
        self.assertTrue(report["invalid_records"])

    def test_exact_duplicates_are_scoped_to_exam_and_year(self):
        records = [
            normalize_record({"name": "Juan Dela Cruz"}, "PRC", "LET", 2026),
            normalize_record({"name": "Juan Dela Cruz"}, "PRC", "LET", 2026),
            normalize_record({"name": "Juan Dela Cruz"}, "CSC", "Professional", 2026),
        ]
        result = find_duplicates(records)
        self.assertEqual(len(result["exact_duplicates"]), 1)
        self.assertEqual(result["exact_duplicates"][0]["duplicate_index"], 1)


class DatasetTests(unittest.TestCase):
    def make_record(self, name, year=2026):
        return normalize_record(
            {"name": name, "rating": "90", "region": "NCR", "seq": "1"},
            "PRC",
            "LET",
            year,
        )

    def test_builder_creates_manifest_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary) / "data"
            records = [self.make_record("ALVAREZ, ANA"), self.make_record("SANTOS, BEN")]
            entries = build_public_datasets(records, data_root, "PRC", "LET", 2026)
            manifest = build_manifest(data_root, data_root / "manifest.json")
            self.assertEqual(sum(entry["record_count"] for entry in entries), 2)
            year = manifest["authorities"]["PRC"]["examinations"]["LET"]["years"]["2026"]
            for entry in year["files"].values():
                self.assertTrue(entry["path"].startswith("/data/prc/let/"))
                self.assertEqual(len(entry["hash"]), 64)

    def test_non_letter_names_are_in_other_shard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            entries = build_public_datasets(
                [self.make_record("123 SAMPLE")], root, "PRC", "LET", 2026
            )
            self.assertEqual([entry["shard"] for entry in entries], ["OTHER"])

    def test_oversized_alphabetical_range_is_split(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            records = [
                self.make_record(f"{chr(65 + index % 26)}{index:06d} " + ("X" * 450))
                for index in range(30000)
            ]
            entries = build_public_datasets(records, root, "PRC", "LET", 2026)
            self.assertGreater(len(entries), 1)
            self.assertTrue(all(entry["size_bytes"] <= MAX_SHARD_BYTES for entry in entries))


class PredictionTests(unittest.TestCase):
    def test_prediction_requires_enough_history(self):
        result = predict_next_release(["2023-01-01", "2024-01-01", "2025-01-01"])
        self.assertIsNone(result["predicted_date"])

    def test_prediction_is_between_historical_interval_bounds(self):
        result = predict_next_release([
            "2020-01-01", "2021-01-01", "2022-01-01",
            "2023-01-01", "2024-01-01", "2025-01-01",
        ])
        self.assertIsNotNone(result["predicted_date"])
        self.assertLessEqual(result["window_start"], result["predicted_date"])
        self.assertGreaterEqual(result["window_end"], result["predicted_date"])


if __name__ == "__main__":
    unittest.main()
