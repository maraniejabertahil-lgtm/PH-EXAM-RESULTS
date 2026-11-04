import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

EXTRACTOR_DIR = Path(__file__).resolve().parents[1] / "extractor"
sys.path.insert(0, str(EXTRACTOR_DIR))

from public_preview_shards import (  # noqa: E402
    _challenge_present,
    merge_shards,
    partition_page_ranges,
    validate_shard_metadata,
)


class PartitionTests(unittest.TestCase):
    def test_901_pages_matches_proven_16_shard_partition(self):
        ranges = partition_page_ranges(901, 16)
        self.assertEqual(ranges[0], (0, 1, 57))
        self.assertEqual(ranges[14], (14, 799, 855))
        self.assertEqual(ranges[15], (15, 856, 901))
        self.assertEqual(sum(end - start + 1 for _, start, end in ranges), 901)

    def test_small_uneven_partition_is_contiguous(self):
        self.assertEqual(
            partition_page_ranges(10, 3),
            [(0, 1, 4), (1, 5, 8), (2, 9, 10)],
        )

    def test_invalid_partition_inputs_fail_closed(self):
        for pages, shards in ((0, 1), (-1, 1), (4, 0), (4, 17), (2, 3), (True, 1)):
            with self.subTest(pages=pages, shards=shards):
                with self.assertRaises(ValueError):
                    partition_page_ranges(pages, shards)

    def test_access_challenge_terms_are_detected(self):
        self.assertTrue(_challenge_present("Please verify you are human"))
        self.assertTrue(_challenge_present("Request access"))
        self.assertFalse(_challenge_present("Page 1 of 901"))


class MergeValidationTests(unittest.TestCase):
    def _metadata(self):
        return [
            {"shard": 0, "shards": 2, "page_start": 1, "page_end": 2, "page_count": 3, "pages_captured": 2},
            {"shard": 1, "shards": 2, "page_start": 3, "page_end": 3, "page_count": 3, "pages_captured": 1},
        ]

    def test_metadata_requires_complete_ranges(self):
        self.assertEqual(validate_shard_metadata(self._metadata(), 2), 3)

    def test_metadata_rejects_gap_or_overlap(self):
        broken = self._metadata()
        broken[1]["page_start"] = 2
        with self.assertRaises(ValueError):
            validate_shard_metadata(broken, 2)

    def test_merge_writes_manifest_and_exact_page_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for item in self._metadata():
                snapshots = []
                for page in range(item["page_start"], item["page_end"] + 1):
                    text = f"Page {page} of 3\nRecord {page}"
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    })
                archive = root / f"shard-{item['shard']}-snapshots.jsonl.gz"
                with gzip.open(archive, "wt", encoding="utf-8") as stream:
                    for snapshot in snapshots:
                        stream.write(json.dumps(snapshot) + "\n")
                item["snapshot_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                (root / f"shard-{item['shard']}.json").write_text(json.dumps(item), encoding="utf-8")

            manifest = merge_shards(shard_count=2, output_dir=root)
            self.assertTrue(manifest["page_coverage_complete"])
            self.assertEqual(manifest["viewer_pages_captured"], 3)
            lines = (root / "page-text-snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["viewer_page"] for line in lines], [1, 2, 3])

    def test_merge_rejects_snapshot_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for item in self._metadata():
                snapshots = []
                for page in range(item["page_start"], item["page_end"] + 1):
                    text = f"Page {page} of 3"
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": "wrong" if page == 2 else hashlib.sha256(text.encode()).hexdigest(),
                    })
                archive = root / f"shard-{item['shard']}-snapshots.jsonl.gz"
                with gzip.open(archive, "wt", encoding="utf-8") as stream:
                    for snapshot in snapshots:
                        stream.write(json.dumps(snapshot) + "\n")
                item["snapshot_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                (root / f"shard-{item['shard']}.json").write_text(json.dumps(item), encoding="utf-8")

            with self.assertRaises(RuntimeError):
                merge_shards(shard_count=2, output_dir=root)


if __name__ == "__main__":
    unittest.main()
