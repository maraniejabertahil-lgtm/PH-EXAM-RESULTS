import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from create_review_bundle import _create_sharded_evidence  # noqa: E402
from acquisition.public_preview import PublicPreviewCaptureError  # noqa: E402


class ShardedReviewBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "capture" / "screens").mkdir(parents=True)
        config = self.root / "python-engine" / "config"
        config.mkdir(parents=True)
        (config / "adapter_mappings.json").write_text(
            json.dumps({
                "LEPT:elementary:2026:public_preview": {
                    "record_pattern": r"^\s*(?P<sequence>\d+)[.)]?\s+(?P<name>.+?)\s*$",
                    "require_comma_in_name": True,
                }
            }),
            encoding="utf-8",
        )
        screenshot = self.root / "capture" / "screens" / "page-0001.png"
        screenshot.write_bytes(b"test screenshot bytes")
        self.screenshot_sha = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        (self.root / "capture" / "page-text-snapshots.jsonl").write_text(
            json.dumps({
                "viewer_page": 1,
                "text": "Page 1 of 1\n1 AALA, TEST NAME",
            }) + "\n",
            encoding="utf-8",
        )
        (self.root / "capture" / "viewer-capture-manifest.json").write_text(
            json.dumps({
                "files": {
                    "screenshots": [{
                        "viewer_page": 1,
                        "path": "capture/screens/page-0001.png",
                        "sha256": self.screenshot_sha,
                    }]
                }
            }),
            encoding="utf-8",
        )
        self.batch = {"public_preview_mapping_key": "LEPT:elementary:2026:public_preview"}
        self.files = {
            "viewer_capture_manifest": {
                "path": "capture/viewer-capture-manifest.json",
            },
            "page_text_snapshots": {
                "path": "capture/page-text-snapshots.jsonl",
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_bundle_references_screenshot_file_without_embedding_base64(self):
        evidence = _create_sharded_evidence(
            repository_root=self.root,
            batch=self.batch,
            files=self.files,
            record_by_sequence={"1": "AALA, TEST NAME"},
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0]["screenshot_path"],
            "capture/screens/page-0001.png",
        )
        self.assertEqual(evidence[0]["sha256"], self.screenshot_sha)
        self.assertNotIn("image_data", evidence[0])
        self.assertTrue(evidence[0]["viewer_text_confirmed"])

    def test_bundle_rejects_screenshot_hash_mismatch(self):
        manifest_path = self.root / "capture" / "viewer-capture-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["screenshots"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(PublicPreviewCaptureError, "Screenshot hash mismatch"):
            _create_sharded_evidence(
                repository_root=self.root,
                batch=self.batch,
                files=self.files,
                record_by_sequence={"1": "AALA, TEST NAME"},
            )


if __name__ == "__main__":
    unittest.main()
