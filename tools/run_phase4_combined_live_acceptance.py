#!/usr/bin/env python3
"""Run Phase 4 capture-to-Greenlight acceptance without GitOps or publication."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))

from main import process_sharded_preview_batch  # noqa: E402


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment value: {name}")
    return value


def main() -> int:
    batch = {
        "authority": "PRC",
        "exam": "LEPT-SECONDARY",
        "year": 2026,
        "announced_count": int(required("ANNOUNCED_COUNT")),
        "provenance": "official_direct",
        "publicly_released": True,
        "source_id": "PRC-EXAM-RESULTS-HOMEPAGE",
        "official_source_url": "https://www.prc.gov.ph/articles/exam-results",
        "official_article_url": required("OFFICIAL_ARTICLE_URL"),
        "official_content_url": required("OFFICIAL_CONTENT_URL"),
        "public_preview_url": required("PUBLIC_PREVIEW_URL"),
        "official_content_mode": "public_preview_capture",
    }
    batch_path = ROOT / "python-engine" / "artifacts" / "phase4-live-batch.json"
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = process_sharded_preview_batch(
        batch_path.relative_to(ROOT),
        capture_dir="public-preview-capture",
        evidence_dir="python-engine/artifacts/sharded-preview",
        root=ROOT,
    )
    report = result["report"]
    summary = {
        "status": "PASS" if report.get("greenlight_score") == 100 else "FAIL",
        "capture_pages": result["sharded_preview_bridge"]["record_count"],
        "record_count": report.get("record_count"),
        "announced_count": batch["announced_count"],
        "greenlight_score": report.get("greenlight_score"),
        "publication_allowed": report.get("publication_allowed"),
        "human_visual_review": result["sharded_preview_bridge"]["human_visual_review"],
        "dataset_manifest": str(result["dataset_dir"] / "manifest.json"),
        "published": False,
        "pull_request_created": False,
        "deployed": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "PASS" or summary["record_count"] != batch["announced_count"]:
        raise RuntimeError("Combined Phase 4 live acceptance did not satisfy Greenlight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
