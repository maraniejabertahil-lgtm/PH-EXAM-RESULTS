from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from publisher.json_builder import DatasetBuildError, build_dataset
from processor.greenlight import validate_records


class ArrayJsonBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output = Path(self.temp_dir.name) / "data"
        self.records = [
            {"name": "ZULU, ZED", "sequence_number": "003", "rating": 88.5, "region": "NCR"},
            {"name": "ALPHA, ANN", "sequence_number": "001", "rating": None, "region": None},
            {"name": "MIKE, MAY", "sequence_number": "002", "rating": 91, "region": "REGION III"},
        ]
        self.report = validate_records(self.records, announced_count=3)

    def test_builds_expected_array_of_arrays_and_manifest(self) -> None:
        manifest = build_dataset(
            self.records, authority="PRC", exam="LET", year=2026,
            output_dir=self.output, greenlight_report=self.report,
        )
        self.assertEqual(manifest["record_count"], 3)
        self.assertEqual(manifest["shard_count"], 1)
        self.assertEqual(manifest["columns"], ["name", "rating", "region", "seq"])
        shard = self.output / manifest["shards"][0]["file"]
        payload = json.loads(shard.read_text(encoding="utf-8"))
        self.assertEqual(payload["data"][0][0], "ALPHA, ANN")
        self.assertEqual(payload["data"][0][3], "001")
        self.assertEqual((self.output / "manifest.json").exists(), True)

    def test_shards_are_below_configured_size_and_preserve_every_record(self) -> None:
        records = [
            {"name": f"NAME {index:03d} PERSON WITH LONG SURNAME", "sequence_number": f"{index:03d}"}
            for index in range(1, 16)
        ]
        report = validate_records(records, announced_count=15)
        manifest = build_dataset(
            records, authority="CSC", exam="CSE-PPT", year=2026,
            output_dir=self.output, greenlight_report=report, max_shard_bytes=150,
        )
        self.assertGreater(manifest["shard_count"], 1)
        all_rows = []
        for shard_info in manifest["shards"]:
            path = self.output / shard_info["file"]
            self.assertLess(path.stat().st_size, 150)
            self.assertEqual(path.stat().st_size, shard_info["size_bytes"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            all_rows.extend(payload["data"])
        self.assertEqual(len(all_rows), 15)
        self.assertEqual([row[3] for row in all_rows], [f"{i:03d}" for i in range(1, 16)])

    def test_rejects_non_greenlight_report(self) -> None:
        failed = dict(self.report, status="REJECTED", greenlight_score=0, publication_allowed=False)
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                self.records, authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=failed,
            )
        self.assertFalse((self.output / "manifest.json").exists())

    def test_rejects_greenlight_report_with_false_check(self) -> None:
        failed = dict(self.report, checks={"count_match": True, "zero_duplicates": False})
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                self.records, authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=failed,
            )

    def test_rejects_record_count_that_differs_from_greenlight(self) -> None:
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                self.records[:2], authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=self.report,
            )

    def test_rejects_single_record_larger_than_shard_limit(self) -> None:
        long_record = [{"name": "A" * 500, "sequence_number": "001"}]
        report = validate_records(long_record, announced_count=1)
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                long_record, authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=report, max_shard_bytes=100,
            )

    def test_builder_rejects_records_that_do_not_match_the_validated_input_hash(self) -> None:
        changed_records = [dict(row) for row in self.records]
        changed_records[0]["name"] = "ALTERED, NAME"
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                changed_records, authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=self.report,
            )

    def test_fallback_manifest_preserves_both_source_identities(self) -> None:
        fallback_report = validate_records(
            self.records,
            announced_count=3,
            provenance="third_party_fallback",
            comparison_records=self.records,
            source_a_id="mirror-a",
            source_b_id="mirror-b",
        )
        manifest = build_dataset(
            self.records, authority="PRC", exam="LET", year=2026,
            output_dir=self.output, greenlight_report=fallback_report,
            provenance="third_party_fallback",
        )
        self.assertEqual(manifest["source_a_id"], "mirror-a")
        self.assertEqual(manifest["source_b_id"], "mirror-b")
        self.assertTrue(manifest["comparison_records_sha256"])

    def test_builder_preserves_original_name_spacing(self) -> None:
        rows = [{"name": "  ALPHA, ANN  ", "sequence_number": "001"}]
        report = validate_records(rows, announced_count=1)
        manifest = build_dataset(
            rows, authority="PRC", exam="LET", year=2026,
            output_dir=self.output, greenlight_report=report,
        )
        payload = json.loads((self.output / manifest["shards"][0]["file"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["data"][0][0], "  ALPHA, ANN  ")

    def test_content_addressed_shards_do_not_overwrite_previous_manifest_until_complete(self) -> None:
        first = build_dataset(
            self.records, authority="PRC", exam="LET", year=2026,
            output_dir=self.output, greenlight_report=self.report,
        )
        original_manifest = (self.output / "manifest.json").read_bytes()
        invalid_report = dict(self.report, greenlight_score=0)
        with self.assertRaises(DatasetBuildError):
            build_dataset(
                self.records, authority="PRC", exam="LET", year=2026,
                output_dir=self.output, greenlight_report=invalid_report,
            )
        self.assertEqual((self.output / "manifest.json").read_bytes(), original_manifest)
        self.assertEqual(first["shards"][0]["file"], json.loads(original_manifest)["shards"][0]["file"])


if __name__ == "__main__":
    unittest.main()
