"""Auditable ingestion of records captured from an official public-preview UI.

This module verifies provenance and immutable capture hashes. It never fetches
Drive content, downloads a PDF, repairs names, or renumbers sequence values.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class PublicPreviewCaptureError(RuntimeError):
    """Raised when public-preview evidence is incomplete or inconsistent."""


def _safe_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PublicPreviewCaptureError(f"{label} is required.")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PublicPreviewCaptureError(f"{label} must remain inside the repository.") from exc
    if not path.is_file():
        raise PublicPreviewCaptureError(f"{label} does not exist: {value}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicPreviewCaptureError(f"{label} must be a JSON object.")
    return value


def load_public_preview_capture(
    *,
    batch: dict[str, Any],
    root: str | Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Load exact JSONL pairs after verifying source and capture evidence hashes."""
    repository_root = Path(root).resolve()
    manifest_path = _safe_file(repository_root, batch.get("capture_manifest"), "capture_manifest")
    manifest = _read_json(manifest_path, "capture manifest")
    if manifest.get("schema_version") != 1 or manifest.get("provenance") != "official_direct":
        raise PublicPreviewCaptureError("Unsupported capture manifest schema or provenance.")
    if manifest.get("pdf_downloaded") is not False or manifest.get("access_controls_bypassed") is not False:
        raise PublicPreviewCaptureError("Capture must confirm no PDF download and no access-control bypass.")
    if manifest.get("public_preview_only") is not True:
        raise PublicPreviewCaptureError("Capture must explicitly identify the ordinary public-preview UI path.")
    if manifest.get("official_article_url") != batch.get("official_article_url"):
        raise PublicPreviewCaptureError("Official article URL does not match the capture manifest.")
    if manifest.get("official_content_url") != batch.get("official_content_url"):
        raise PublicPreviewCaptureError("Official linked-content URL does not match the capture manifest.")
    if manifest.get("public_preview_url") != batch.get("public_preview_url"):
        raise PublicPreviewCaptureError("Public-preview URL does not match the capture manifest.")

    content = urlsplit(str(batch.get("official_content_url", "")))
    preview = urlsplit(str(batch.get("public_preview_url", "")))
    if (
        content.scheme != "https" or content.hostname != "drive.google.com"
        or preview.scheme != "https" or preview.hostname != "drive.google.com"
        or not content.path.rstrip("/").endswith("/view")
        or preview.path != content.path.rsplit("/", 1)[0] + "/preview"
    ):
        raise PublicPreviewCaptureError("Preview URL must be the ordinary public preview for the official linked Drive file.")

    page_count = manifest.get("viewer_pages_expected")
    if (
        isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1
        or manifest.get("viewer_pages_navigated") != page_count
        or manifest.get("snapshots_retained") != 1
    ):
        raise PublicPreviewCaptureError("Public-preview page navigation evidence is incomplete.")

    files = manifest.get("files")
    required = ("layout_text", "records_jsonl", "extraction_report", "visual_report")
    if not isinstance(files, dict) or any(key not in files for key in required):
        raise PublicPreviewCaptureError("Capture manifest is missing required evidence-file hashes.")
    resolved: dict[str, Path] = {}
    for key in required:
        entry = files[key]
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PublicPreviewCaptureError(f"Invalid evidence-file entry: {key}")
        path = _safe_file(repository_root, entry["path"], f"{key} evidence")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64 or _sha256(path) != expected:
            raise PublicPreviewCaptureError(f"SHA-256 mismatch for {key} evidence.")
        resolved[key] = path

    extraction = _read_json(resolved["extraction_report"], "extraction report")
    if extraction.get("candidate_complete") is not True:
        raise PublicPreviewCaptureError("The official extraction report does not mark the candidate complete.")
    if extraction.get("provenance") != "official_direct":
        raise PublicPreviewCaptureError("Extraction report provenance is not official_direct.")
    announced = batch.get("announced_count")
    if extraction.get("announced_count") != announced or extraction.get("extracted_unique_sequences") != announced:
        raise PublicPreviewCaptureError("Extraction counts do not match the batch's announced count.")
    if any(extraction.get(key) != 0 for key in (
        "missing_sequence_count", "conflict_count", "duplicate_sequence_count",
        "out_of_range_record_count", "duplicate_name_count", "blank_name_count",
        "unresolved_target_record_count",
    )):
        raise PublicPreviewCaptureError("Extraction report contains unresolved integrity issues.")

    visual = _read_json(resolved["visual_report"], "visual verification report")
    if visual.get("source") != batch.get("public_preview_url") or visual.get("pdf_downloaded") is not False:
        raise PublicPreviewCaptureError("Visual evidence does not match the public-preview source.")
    if visual.get("access_controls_bypassed") is not False or visual.get("ocr_is_advisory_only") is not True:
        raise PublicPreviewCaptureError("Visual evidence does not satisfy the access and OCR safeguards.")
    results = visual.get("results")
    if not isinstance(results, list) or not results:
        raise PublicPreviewCaptureError("Visual evidence must contain at least one captured source page.")
    visual_records = extraction.get("visual_verification_evidence")
    if not isinstance(visual_records, dict):
        raise PublicPreviewCaptureError("Extraction report is missing visual-record evidence.")
    for item in results:
        if not isinstance(item, dict) or item.get("viewer_text_confirmed") is not True:
            raise PublicPreviewCaptureError("A visual source page lacks viewer-text confirmation.")
        screenshot = _safe_file(repository_root, item.get("screenshot"), "visual screenshot")
        if _sha256(screenshot) != item.get("screenshot_sha256"):
            raise PublicPreviewCaptureError("Visual screenshot hash does not match the visual report.")
        sequence = str(item.get("sequence", ""))
        record = visual_records.get(sequence)
        if not isinstance(record, dict) or record.get("name") != item.get("expected_visible_text", "").split(" ", 1)[-1]:
            raise PublicPreviewCaptureError("Visual screenshot evidence does not match the extraction report's expected record.")
        if record.get("screenshot_sha256") != item.get("screenshot_sha256"):
            raise PublicPreviewCaptureError("Extraction and visual reports reference different screenshot hashes.")

    records_path = resolved["records_jsonl"]
    records: list[dict[str, str]] = []
    try:
        for line_number, line in enumerate(records_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != {"seq", "name"}:
                raise PublicPreviewCaptureError(f"Invalid JSONL record schema on line {line_number}.")
            sequence = row["seq"]
            name = row["name"]
            if not isinstance(sequence, str) or not sequence.isdigit():
                raise PublicPreviewCaptureError(f"Invalid sequence value on line {line_number}.")
            if not isinstance(name, str) or not name.strip():
                raise PublicPreviewCaptureError(f"Blank or invalid name on line {line_number}.")
            records.append({"sequence_number": sequence, "name": name})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Cannot parse captured records JSONL: {exc}") from exc
    if len(records) != announced:
        raise PublicPreviewCaptureError("Captured JSONL record count does not match the announced count.")
    return records, {
        "capture_manifest": str(manifest_path.relative_to(repository_root)),
        "capture_manifest_sha256": _sha256(manifest_path),
        "records_file_sha256": _sha256(records_path),
        "public_preview_url": batch["public_preview_url"],
        "viewer_pages": page_count,
        "visual_review_status": visual.get("human_visual_verification", "PENDING"),
    }
