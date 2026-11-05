from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from publisher.site_catalogue import CatalogueError, build_site_catalogue, serialize_site_catalogue

class SiteCatalogueTests(unittest.TestCase):
    def test_catalogue_maps_current_dataset_manifest_to_website_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "PRC" / "LEPT-ELEMENTARY" / "2026"
            folder.mkdir(parents=True)
            manifest = {"schema_version":1,"authority":"PRC","exam":"LEPT-ELEMENTARY","year":2026,
                "shards":[{"file":"2026-abcd1234.json","sha256":"a"*64,"record_count":18376,"size_bytes":862332}]}
            (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = build_site_catalogue(root)
            entry = result["authorities"]["PRC"]["examinations"]["LEPT-ELEMENTARY"]["years"]["2026"]["files"]["S001"]
            self.assertEqual(entry["path"], "/data/PRC/LEPT-ELEMENTARY/2026/2026-abcd1234.json")
            self.assertEqual(entry["record_count"], 18376)
            self.assertEqual(json.loads(serialize_site_catalogue(root))["schema_version"], 2)

    def test_overlay_updates_current_batch_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay = {"authority":"PRC","exam":"LET","year":2026,
                "shards":[{"file":"2026-new.json","sha256":"b"*64,"record_count":2,"size_bytes":80}]}
            result = build_site_catalogue(tmp, overlay=overlay)
            self.assertIn("LET", result["authorities"]["PRC"]["examinations"])

    def test_rejects_unsafe_or_invalid_shard_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "PRC" / "LET" / "2026"
            root.mkdir(parents=True)
            (root / "manifest.json").write_text(json.dumps({"authority":"PRC","exam":"LET","year":2026,
                "shards":[{"file":"../evil.json","sha256":"c"*64,"record_count":1,"size_bytes":80}]}))
            with self.assertRaises(CatalogueError):
                build_site_catalogue(Path(tmp))

if __name__ == "__main__":
    unittest.main()
