#!/usr/bin/env python3
"""Bridge official PRC public-preview evidence into the Python Engine.

This runs after the capture and screenshot jobs. It reconciles screenshot hashes,
creates an auditable capture manifest, and invokes process_batch only. It never
opens a GitOps PR, merges, deploys, or downloads the linked PDF.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "official-prc-evidence"
VISUAL = ROOT / "official-prc-visual-check"
ENGINE_ARTIFACTS = ROOT / "python-engine" / "artifacts"
ANNOUNCED = 18376
SOURCE_ID = "PRC-EXAM-RESULTS-HOMEPAGE"
OFFICIAL_SOURCE_URL = "https://www.prc.gov.ph/articles/exam-results"
EXPECTED_ARTICLE = "https://www.prc.gov.ph/index.php/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39"
DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
PREVIEW_URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return value


def main() -> int:
    extraction_path = EVIDENCE / "extraction-report.json"
    visual_path = VISUAL / "visual-check-report.json"
    attempt_path = EVIDENCE / "attempt-evidence.json"
    records_path = EVIDENCE / "extracted-records.jsonl"
    text_path = EVIDENCE / "official-layout-text.txt"
    extraction = read_json(extraction_path)
    visual = read_json(visual_path)
    attempts = json.loads(attempt_path.read_text(encoding="utf-8"))
    if not isinstance(attempts, list):
        raise RuntimeError("Official attempt evidence must be a list.")

    article_events = [event for event in attempts if event.get("stage") == "official_article"]
    preview_events = [event for event in attempts if event.get("stage") == "official_public_preview_pages"]
    if len(article_events) != 1 or len(preview_events) != 1:
        raise RuntimeError("Expected exactly one official article and public-preview evidence event.")
    article = article_events[0]
    preview = preview_events[0]
    if article.get("url") != EXPECTED_ARTICLE or DRIVE_ID not in str(article.get("drive_link", "")):
        raise RuntimeError("Captured article or linked Drive document does not match the approved PRC result.")
    if preview.get("url") != PREVIEW_URL or preview.get("final_url") != PREVIEW_URL:
        raise RuntimeError("Captured preview URL does not match the official linked document.")
    if preview.get("status") != 200 or preview.get("viewer_pages") != 368:
        raise RuntimeError("Public preview did not return the expected 368-page viewer.")
    if preview.get("pages_navigated") != 368 or preview.get("snapshots_retained") != 1:
        raise RuntimeError("Public-preview navigation or cumulative-snapshot evidence is incomplete.")
    if extraction.get("candidate_complete") is not True or extraction.get("announced_count") != ANNOUNCED:
        raise RuntimeError("Unicode extraction candidate is not complete against the announced PRC count.")

    visual_results = visual.get("results")
    if visual.get("source") != PREVIEW_URL or visual.get("access_controls_bypassed") is not False:
        raise RuntimeError("Visual evidence source or access-control safeguards are invalid.")
    if not isinstance(visual_results, list) or len(visual_results) != 2:
        raise RuntimeError("Expected exactly two targeted visual evidence captures.")
    for item in visual_results:
        screenshot = (ROOT / item["screenshot"]).resolve()
        if ROOT not in screenshot.parents or not screenshot.is_file():
            raise RuntimeError("Visual screenshot path is invalid or missing.")
        actual_hash = sha256(screenshot)
        if actual_hash != item.get("screenshot_sha256") or item.get("viewer_text_confirmed") is not True:
            raise RuntimeError("Visual screenshot hash or viewer text confirmation failed.")
        seq = str(item["sequence"])
        expected_name = item["expected_visible_text"].split(" ", 1)[-1]
        entry = extraction.get("visual_verification_evidence", {}).get(seq)
        if not isinstance(entry, dict) or entry.get("name") != expected_name:
            raise RuntimeError(f"Visual source evidence does not match extraction sequence {seq}.")
        # Reconcile the extraction report to the exact screenshot hash in this run.
        entry["screenshot_sha256"] = actual_hash
    extraction["visual_evidence_integrity"] = "SCREENSHOT_HASHES_MATCH"
    extraction["visual_human_review_status"] = visual.get("human_visual_verification", "PENDING")
    extraction_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Re-read the exact capture files after reconciliation; the manifest is a
    # hash-bound record of what the Python Engine is about to validate.
    manifest = {
        "schema_version": 1,
        "provenance": "official_direct",
        "public_preview_only": True,
        "official_article_url": EXPECTED_ARTICLE,
        "official_content_url": article["drive_link"],
        "public_preview_url": PREVIEW_URL,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "viewer_pages_expected": 368,
        "viewer_pages_navigated": 368,
        "snapshots_retained": 1,
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "visual_human_review_status": visual.get("human_visual_verification", "PENDING"),
        "files": {
            "layout_text": {"path": "official-prc-evidence/official-layout-text.txt", "sha256": sha256(text_path)},
            "records_jsonl": {"path": "official-prc-evidence/extracted-records.jsonl", "sha256": sha256(records_path)},
            "extraction_report": {"path": "official-prc-evidence/extraction-report.json", "sha256": sha256(extraction_path)},
            "visual_report": {"path": "official-prc-visual-check/visual-check-report.json", "sha256": sha256(visual_path)},
        },
        "visual_screenshots": [
            {"path": item["screenshot"], "sha256": item["screenshot_sha256"], "sequence": item["sequence"]}
            for item in visual_results
        ],
    }
    ENGINE_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest_path = ENGINE_ARTIFACTS / "prc-lept-elementary-2026-capture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    batch = {
        "authority": "PRC",
        "exam": "LEPT-ELEMENTARY",
        "year": 2026,
        "announced_count": ANNOUNCED,
        "provenance": "official_direct",
        "source_id": SOURCE_ID,
        "publicly_released": True,
        "official_source_url": OFFICIAL_SOURCE_URL,
        "official_article_url": EXPECTED_ARTICLE,
        "official_content_url": article["drive_link"],
        "public_preview_url": PREVIEW_URL,
        "official_content_mode": "public_preview_capture",
        "capture_manifest": str(manifest_path.relative_to(ROOT)),
    }
    batch_path = ENGINE_ARTIFACTS / "prc-lept-elementary-2026-batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sys.path.insert(0, str(ROOT / "python-engine"))
    from main import process_batch
    result = process_batch(batch_path.relative_to(ROOT), root=ROOT)
    report = result["report"]
    print(json.dumps({
        "status": report["status"],
        "greenlight_score": report["greenlight_score"],
        "record_count": report["record_count"],
        "announced_count": report["announced_count"],
        "records_sha256": report["records_sha256"],
        "checks": report["checks"],
        "dataset_manifest": str((result["dataset_dir"] / "manifest.json").relative_to(ROOT)),
        "dataset_shard_count": result["manifest"]["shard_count"],
        "dataset_shard_sizes": [entry["size_bytes"] for entry in result["manifest"]["shards"]],
        "publication_performed": False,
        "gitops_pr_created": False,
        "visual_human_review_status": report["public_preview_capture"]["visual_review_status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
