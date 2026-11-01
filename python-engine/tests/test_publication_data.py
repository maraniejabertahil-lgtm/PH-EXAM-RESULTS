import json
import tempfile
import unittest
from pathlib import Path

from publisher.json_builder import build_public_datasets
from publisher.manifest import build_manifest
from processor.normalizer import normalize_record


class PublicDatasetTests(unittest.TestCase):
    def test_builds_compact_array_shards_and_manifest(self):
        records = [
            normalize_record({"name": "DELA CRUZ, JUAN A"}, "PRC", "LET", 2026),
            normalize_record({"name": "SANTOS, MARIA B"}, "PRC", "LET", 2026),
            normalize_record({"name": "1 UNKNOWN"}, "PRC", "LET", 2026),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "public"
            data_root = root / "data"
            entries = build_public_datasets(records, data_root, "PRC", "LET", 2026)
            self.assertEqual({item["shard"] for item in entries}, {"A-M", "N-Z", "OTHER"})
            manifest = build_manifest(data_root, root / "data" / "manifest.json")
            dataset = manifest["authorities"]["PRC"]["examinations"]["LET"]["years"]["2026"]
            self.assertTrue(dataset["sharded"])
            file_path = root / dataset["files"]["A-M"]["path"].lstrip("/")
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["columns"], ["name", "rating", "region", "seq"])
            self.assertEqual(payload["data"][0][0], "DELA CRUZ, JUAN A")

    def test_rejects_mixed_exam_records(self):
        record = normalize_record({"name": "JUAN DELA CRUZ"}, "PRC", "NLE", 2026)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                build_public_datasets([record], folder, "PRC", "LET", 2026)


if __name__ == "__main__":
    unittest.main()
