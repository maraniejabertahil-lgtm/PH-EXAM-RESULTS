#!/usr/bin/env python3
"""Build a hash-bound PRC Secondary capture manifest and run local Greenlight.

This bridge intentionally calls process_batch(), never publish_batch(). It can
validate and generate a local dataset, but it cannot create a PR or publish.
Human visual review remains PENDING and is preserved as such.
"""
from __future__ import annotations

import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))

from main import process_batch  # noqa: E402

DRIVE_ID = "1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7"
ANNOUNCED_COUNT = 45001
SOURCE_ID = "PRC-EXAM-RESULTS-HOMEPAGE"
OFFICIAL_SOURCE_URL = "https://www.prc.gov.ph/articles/exam-results"
EVIDENCE_DIR = ROOT / "official-prc-secondary-evidence"
VISUAL_DIR = ROOT / "official-prc-secondary-visual-check"


class Hrefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    article_path = EVIDENCE_DIR / "official-article.html"
    events_path = EVIDENCE_DIR / "attempt-evidence.json"
    layout_path = EVIDENCE_DIR / "official-layout-text.txt"
    records_path = EVIDENCE_DIR / "extracted-records.jsonl"
    extraction_path = EVIDENCE_DIR / "extraction-report.json"
    page_count_path = EVIDENCE_DIR / "official-preview-page-count.json"
    visual_path = VISUAL_DIR / "visual-check-report.json"

    required = (
        article_path, events_path, layout_path, records_path,
        extraction_path, page_count_path, visual_path,
    )
    missing = [relative(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Required capture evidence is missing: " + ", ".join(missing))

    extraction = read_json(extraction_path)
    visual = read_json(visual_path)
    page_count = read_json(page_count_path)
    events = json.loads(events_path.read_text(encoding="utf-8"))
    if extraction.get("candidate_complete") is not True:
        raise RuntimeError("Capture extraction is not marked candidate_complete.")
    if extraction.get("provenance") != "official_direct":
        raise RuntimeError("Capture provenance is not official_direct.")
    if extraction.get("announced_count") != ANNOUNCED_COUNT:
        raise RuntimeError("Capture announced count is not 45,001.")
    if extraction.get("visual_human_review_status") != "PENDING":
        raise RuntimeError("This workflow requires human visual review to remain PENDING.")
    if visual.get("human_visual_verification") != "PENDING":
        raise RuntimeError("Visual report does not preserve PENDING human review.")
    if visual.get("pdf_downloaded") is not False or visual.get("access_controls_bypassed") is not False:
        raise RuntimeError("Visual evidence does not satisfy the no-download/no-bypass policy.")
    if visual.get("ocr_is_advisory_only") is not True:
        raise RuntimeError("OCR must remain advisory only.")

    article_events = [
        item for item in events
        if isinstance(item, dict) and item.get("stage") == "official_article"
    ]
    if not article_events:
        raise RuntimeError("Capture attempt evidence does not identify the official PRC article.")
    article_url = article_events[-1].get("url")
    if not isinstance(article_url, str) or urlsplit(article_url).hostname != "www.prc.gov.ph":
        raise RuntimeError("Official article URL is not on the approved www.prc.gov.ph origin.")

    parser = Hrefs()
    parser.feed(article_path.read_text(encoding="utf-8", errors="replace"))
    linked = [
        urljoin(article_url, href)
        for href in parser.hrefs
        if DRIVE_ID in href
    ]
    content_url = next(
        (
            value for value in linked
            if urlsplit(value).scheme == "https"
            and urlsplit(value).hostname == "drive.google.com"
            and urlsplit(value).path.rstrip("/").endswith("/view")
        ),
        None,
    )
    if not content_url:
        raise RuntimeError("Could not find the exact official Drive /view link in the PRC article.")
    public_preview_url = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
    content_parts = urlsplit(content_url)
    preview_parts = urlsplit(public_preview_url)
    if content_parts.path.rstrip("/") + "/preview" != preview_parts.path:
        raise RuntimeError("Official Drive link does not match the captured public-preview path.")

    if (
        page_count.get("viewer_pages_expected") != page_count.get("viewer_pages_navigated")
        or page_count.get("viewer_pages_expected") != page_count.get("snapshots_retained")
    ):
        raise RuntimeError("Public-preview page-count evidence is incomplete.")

    files = {
        "layout_text": layout_path,
        "records_jsonl": records_path,
        "extraction_report": extraction_path,
        "visual_report": visual_path,
    }
    manifest = {
        "schema_version": 1,
        "provenance": "official_direct",
        "public_preview_only": True,
        "official_article_url": article_url,
        "official_content_url": content_url,
        "public_preview_url": public_preview_url,
        "viewer_pages_expected": page_count["viewer_pages_expected"],
        "viewer_pages_navigated": page_count["viewer_pages_navigated"],
        "snapshots_retained": page_count["snapshots_retained"],
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "files": {
            key: {"path": relative(path), "sha256": sha256(path)}
            for key, path in files.items()
        },
    }
    manifest_path = EVIDENCE_DIR / "python-engine-capture-manifest.json"
    write_json(manifest_path, manifest)

    batch = {
        "authority": "PRC",
        "exam": "LEPT-SECONDARY",
        "year": 2026,
        "announced_count": ANNOUNCED_COUNT,
        "provenance": "official_direct",
        "publicly_released": True,
        "source_id": SOURCE_ID,
        "official_source_url": OFFICIAL_SOURCE_URL,
        "official_article_url": article_url,
        "official_content_url": content_url,
        "public_preview_url": public_preview_url,
        "official_content_mode": "public_preview_capture",
        "capture_manifest": relative(manifest_path),
    }
    batch_path = EVIDENCE_DIR / "python-engine-batch.json"
    write_json(batch_path, batch)

    # Deliberately local-only: process_batch validates and builds dataset files.
    # Do not replace this with publish_batch() in this trial workflow.
    result = process_batch(relative(batch_path), root=ROOT)
    report = result["report"]
    if report.get("greenlight_score") != 100 or report.get("publication_allowed") is not True:
        raise RuntimeError("Python Engine Greenlight did not return 100/100.")
    if report.get("public_preview_capture", {}).get("visual_review_status") != "PENDING":
        raise RuntimeError("Python Engine did not preserve the pending human-review state.")

    print(json.dumps({
        "status": "GREENLIGHT_LOCAL_DATASET_GENERATED",
        "greenlight_score": report["greenlight_score"],
        "record_count": report["record_count"],
        "records_sha256": report["records_sha256"],
        "dataset_manifest": str(result["dataset_dir"] / "manifest.json"),
        "human_visual_review": "PENDING",
        "published": False,
        "pull_request_created": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"SECONDARY PYTHON ENGINE TRIAL STOPPED: {error}", file=sys.stderr)
        raise
