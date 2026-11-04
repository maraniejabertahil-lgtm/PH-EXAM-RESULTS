import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from acquisition.public_preview_shards_bridge import (  # noqa: E402
    ShardBridgeError,
    build_python_engine_capture_manifest,
)
from main import process_sharded_preview_batch  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicPreviewShardBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / "capture"
        self.output = self.root / "evidence"
        self.capture.mkdir()
        self.batch = {
            "provenance": "official_direct",
            "announced_count": 2,
            "official_article_url": "https://www.prc.gov.ph/article/results",
            "official_content_url": "https://drive.google.com/file/d/FILE/view?usp=sharing",
            "public_preview_url": "https://drive.google.com/file/d/FILE/preview",
        }
        pages = [
            "Page 1 of 2\n1 DOE, JANE A",
            "Page 2 of 2\n2 SMITH, JOHN B",
        ]
        index = []
        snapshots = []
        for number, text in enumerate(pages, 1):
            index.append({
                "viewer_page": number,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "characters": len(text),
            })
            snapshots.append({"viewer_page": number, "text": text})
        (self.capture / "page-capture-index.json").write_text(json.dumps(index), encoding="utf-8")
        (self.capture / "page-text-snapshots.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in snapshots), encoding="utf-8"
        )
        screenshot = self.capture / "shard-0-page-1.png"
        screenshot.write_bytes(b"fixture first-page screenshot")
        (self.capture / "shard-0-page-2.png").write_bytes(b"fixture last-page screenshot")
        self.capture_manifest = {
            "schema_version": 1,
            "capture_method": "ordinary_public_preview_ui",
            "shards": 1,
            "viewer_pages_expected": 2,
            "viewer_pages_captured": 2,
            "page_coverage_complete": True,
            "pdf_downloaded": False,
            "access_controls_bypassed": False,
            "files": {
                "page_capture_index": {
                    "path": "page-capture-index.json",
                    "sha256": sha(self.capture / "page-capture-index.json"),
                },
                "page_text_snapshots": {
                    "path": "page-text-snapshots.jsonl",
                    "sha256": sha(self.capture / "page-text-snapshots.jsonl"),
                },
            },
            "shard_metadata": [],
        }
        (self.capture / "capture-manifest.json").write_text(
            json.dumps(self.capture_manifest), encoding="utf-8"
        )

    def test_builds_hash_bound_engine_manifest_and_exact_records(self):
        result = build_python_engine_capture_manifest(
            capture_dir=self.capture, output_dir=self.output, batch=self.batch, repository_root=self.root
        )
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["human_visual_review"], "PENDING")
        self.assertFalse(result["published"])
        rows = [
            json.loads(line)
            for line in (self.output / "records.jsonl").read_text().splitlines()
        ]
        self.assertEqual(rows, [
            {"seq": "1", "name": "DOE, JANE A"},
            {"seq": "2", "name": "SMITH, JOHN B"},
        ])
        manifest = json.loads(result["manifest_path"].read_text())
        visual = json.loads((self.output / "visual-report.json").read_text())
        self.assertEqual(len(visual["results"]), 2)
        self.assertEqual(manifest["snapshots_retained"], 2)
        self.assertEqual(manifest["viewer_pages_navigated"], 2)
        for entry in manifest["files"].values():
            self.assertEqual(sha(self.root / entry["path"]), entry["sha256"])

    def test_rejects_tampered_snapshot_hash(self):
        with (self.capture / "page-text-snapshots.jsonl").open("a") as stream:
            stream.write("{}\n")
        with self.assertRaises(ShardBridgeError):
            build_python_engine_capture_manifest(
                capture_dir=self.capture, output_dir=self.output, batch=self.batch, repository_root=self.root
            )

    def test_rejects_missing_sequence_without_emitting_engine_manifest(self):
        snapshots = [
            {"viewer_page": 1, "text": "Page 1 of 2\n1 DOE, JANE A"},
            {"viewer_page": 2, "text": "Page 2 of 2\n"},
        ]
        index = [
            {"viewer_page": row["viewer_page"],
             "sha256": hashlib.sha256(row["text"].encode()).hexdigest()}
            for row in snapshots
        ]
        (self.capture / "page-capture-index.json").write_text(json.dumps(index))
        (self.capture / "page-text-snapshots.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in snapshots)
        )
        self.capture_manifest["files"]["page_capture_index"]["sha256"] = sha(
            self.capture / "page-capture-index.json"
        )
        self.capture_manifest["files"]["page_text_snapshots"]["sha256"] = sha(
            self.capture / "page-text-snapshots.jsonl"
        )
        (self.capture / "capture-manifest.json").write_text(json.dumps(self.capture_manifest))
        with self.assertRaises(ShardBridgeError):
            build_python_engine_capture_manifest(
                capture_dir=self.capture, output_dir=self.output, batch=self.batch, repository_root=self.root
            )
        self.assertFalse((self.output / "python-engine-capture-manifest.json").exists())


    def test_full_bridge_runs_local_greenlight_and_dataset_without_publishing(self):
        config = self.root / "python-engine" / "config"
        config.mkdir(parents=True)
        (config / "sources.json").write_text(json.dumps({
            "sources": [{
                "id": "PRC-TEST", "authority": "PRC", "exam_scope": "all",
                "source_type": "official", "authorized": True, "enabled": True,
                "url": "https://www.prc.gov.ph/articles/exam-results",
                "allow_linked_drive_documents": True,
            }]
        }), encoding="utf-8")
        batch = dict(self.batch, authority="PRC", exam="LEPT-SECONDARY",
                     year=2026, publicly_released=True, source_id="PRC-TEST",
                     official_source_url="https://www.prc.gov.ph/articles/exam-results")
        batch_path = self.root / "batch.json"
        batch_path.write_text(json.dumps(batch), encoding="utf-8")
        from unittest.mock import patch
        with patch("main.verify_official_content_link") as verify:
            result = process_sharded_preview_batch(
                "batch.json", capture_dir="capture",
                evidence_dir="python-engine/artifacts/sharded-preview",
                root=self.root,
            )
        verify.assert_called_once()
        self.assertEqual(result["report"]["greenlight_score"], 100)
        self.assertEqual(result["report"]["record_count"], 2)
        self.assertEqual(result["sharded_preview_bridge"]["human_visual_review"], "PENDING")
        self.assertFalse(result["sharded_preview_bridge"]["published"])
        self.assertTrue((result["dataset_dir"] / "manifest.json").is_file())

    def test_rejects_capture_with_access_bypass_flag(self):
        self.capture_manifest["access_controls_bypassed"] = True
        (self.capture / "capture-manifest.json").write_text(json.dumps(self.capture_manifest))
        with self.assertRaises(ShardBridgeError):
            build_python_engine_capture_manifest(
                capture_dir=self.capture, output_dir=self.output, batch=self.batch, repository_root=self.root
            )


if __name__ == "__main__":
    unittest.main()
