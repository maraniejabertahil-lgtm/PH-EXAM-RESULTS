"""Auditable ingestion of records captured from an official public-preview UI.

This module verifies provenance and immutable capture hashes. It never fetches
Drive content, downloads a PDF, repairs names, or renumbers sequence values.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class PublicPreviewCaptureError(RuntimeError):
    """Raised when public-preview evidence is incomplete or inconsistent."""


def parse_public_preview_records(
    text: str,
    mapping: dict[str, Any],
    *,
    require_records: bool = True,
) -> list[tuple[int, str]]:
    """Extract exact sequence/name pairs using an explicitly reviewed mapping."""
    pattern = mapping.get("record_pattern")
    if not isinstance(pattern, str) or not pattern:
        raise PublicPreviewCaptureError("Reviewed public-preview mapping must define record_pattern.")
    try:
        expression = re.compile(pattern)
    except re.error as exc:
        raise PublicPreviewCaptureError(f"Reviewed public-preview record pattern is invalid: {exc}") from exc
    if not {"sequence", "name"}.issubset(expression.groupindex):
        raise PublicPreviewCaptureError("Record pattern must define named sequence and name groups.")

    records: list[tuple[int, str]] = []
    require_comma = mapping.get("require_comma_in_name", False)
    if not isinstance(require_comma, bool):
        raise PublicPreviewCaptureError("require_comma_in_name must be a boolean.")
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = expression.fullmatch(line)
        if match is None:
            continue
        sequence_text = match.group("sequence")
        name = match.group("name")
        if not sequence_text.isdigit() or not name.strip():
            raise PublicPreviewCaptureError(f"Invalid record on rendered line {line_number}.")
        if require_comma and "," not in name:
            continue
        if any(
            not (
                character.isspace()
                or unicodedata.category(character)[0] in {"L", "M", "N", "P", "Z"}
            )
            for character in name
        ):
            raise PublicPreviewCaptureError(f"Unexpected character in rendered name on line {line_number}.")
        records.append((int(sequence_text), name))
    if require_records and not records:
        raise PublicPreviewCaptureError("Reviewed mapping found no passer sequence/name pairs.")
    return records


def parse_public_preview_snapshots(
    snapshots: list[dict[str, Any]],
    mapping: dict[str, Any],
) -> list[tuple[int, str]]:
    """Combine page-local or cumulative viewer snapshots without masking conflicts."""
    records_by_sequence: dict[int, str] = {}
    for snapshot_number, snapshot in enumerate(snapshots, start=1):
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("text"), str):
            raise PublicPreviewCaptureError(
                f"Rendered page snapshot {snapshot_number} is missing text."
            )
        page_records = parse_public_preview_records(
            snapshot["text"],
            mapping,
            require_records=False,
        )
        sequences_on_page: set[int] = set()
        for sequence, name in page_records:
            if sequence in sequences_on_page:
                raise PublicPreviewCaptureError(
                    f"Rendered page snapshot {snapshot_number} repeats sequence {sequence}."
                )
            sequences_on_page.add(sequence)
            existing_name = records_by_sequence.get(sequence)
            if existing_name is not None and existing_name != name:
                raise PublicPreviewCaptureError(
                    f"Rendered page snapshots disagree on sequence {sequence}."
                )
            records_by_sequence[sequence] = name
    if not records_by_sequence:
        raise PublicPreviewCaptureError("Rendered page snapshots contain no passer records.")
    return sorted(records_by_sequence.items())


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
    if manifest.get("schema_version") == 2:
        return _load_sharded_public_preview_capture(
            batch=batch,
            repository_root=repository_root,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    if manifest.get("schema_version") != 1 or manifest.get("provenance") != "official_direct":
        raise PublicPreviewCaptureError("Unsupported capture manifest schema or provenance.")
    if manifest.get("pdf_downloaded") is not False or manifest.get("access_controls_bypassed") is not False:
        raise PublicPreviewCaptureError("Capture must confirm no PDF download and no access-control bypass.")
    if manifest.get("capture_method") not in {"ordinary_public_preview_ui", "ordinary_public_page_ui"}:
        raise PublicPreviewCaptureError("Capture method is not an approved ordinary public UI route.")
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
    allowed_hosts = batch.get("public_preview_allowed_hosts")
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or content.scheme != "https" or preview.scheme != "https"
        or content.hostname not in allowed_hosts or preview.hostname not in allowed_hosts
        or content.username or content.password or content.fragment
        or preview.username or preview.password or preview.fragment
    ):
        raise PublicPreviewCaptureError("Content and preview URLs must use credential-free, approved HTTPS hosts.")
    if batch.get("public_preview_method") == "ordinary_public_page_ui":
        if batch.get("official_content_url") != batch.get("public_preview_url"):
            raise PublicPreviewCaptureError("An ordinary public-page capture must use the exact official content URL.")
        if manifest.get("capture_method") != "ordinary_public_page_ui":
            raise PublicPreviewCaptureError("Public-page batch and capture method do not match.")
    elif (
        batch.get("public_preview_method") != "ordinary_public_preview_ui"
        or content.hostname != "drive.google.com"
        or preview.hostname != "drive.google.com"
        or not content.path.rstrip("/").endswith("/view")
        or preview.path != content.path.rsplit("/", 1)[0] + "/preview"
    ):
        raise PublicPreviewCaptureError("Drive preview URL must be the ordinary preview for the exact official linked file.")

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


def _load_sharded_public_preview_capture(
    *,
    batch: dict[str, Any],
    repository_root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Verify page screenshots, rendered text, mapping, and exact extracted pairs."""
    if (
        manifest.get("provenance") != "official_direct"
        or manifest.get("capture_method") not in {"ordinary_public_preview_ui", "ordinary_public_page_ui"}
        or manifest.get("public_preview_only") is not True
        or manifest.get("pdf_downloaded") is not False
        or manifest.get("access_controls_bypassed") is not False
    ):
        raise PublicPreviewCaptureError("Sharded capture is not verified ordinary public-preview evidence.")
    if manifest.get("source_id") != batch.get("exam_specific_source_id"):
        raise PublicPreviewCaptureError("Capture source ID does not match the approved exam-specific source.")
    for key in ("official_article_url", "official_content_url", "public_preview_url"):
        if manifest.get(key) != batch.get(key):
            raise PublicPreviewCaptureError(f"{key} does not match the capture manifest.")

    content = urlsplit(str(batch.get("official_content_url", "")))
    preview = urlsplit(str(batch.get("public_preview_url", "")))
    allowed_hosts = batch.get("public_preview_allowed_hosts")
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or content.scheme != "https"
        or preview.scheme != "https"
        or content.hostname not in allowed_hosts
        or preview.hostname not in allowed_hosts
        or content.username or content.password or content.fragment
        or preview.username or preview.password or preview.fragment
    ):
        raise PublicPreviewCaptureError("Content and preview URLs must use credential-free, approved HTTPS hosts.")
    if batch.get("public_preview_method") == "ordinary_public_page_ui":
        if batch.get("official_content_url") != batch.get("public_preview_url"):
            raise PublicPreviewCaptureError("An ordinary public-page capture must use the exact official content URL.")
        if manifest.get("capture_method") != "ordinary_public_page_ui":
            raise PublicPreviewCaptureError("Public-page batch and capture method do not match.")
    elif (
        batch.get("public_preview_method") != "ordinary_public_preview_ui"
        or content.hostname != "drive.google.com"
        or preview.hostname != "drive.google.com"
        or not content.path.rstrip("/").endswith("/view")
        or preview.path != content.path.rsplit("/", 1)[0] + "/preview"
    ):
        raise PublicPreviewCaptureError("Drive preview URL must be the ordinary preview for the exact official linked file.")

    page_count = manifest.get("viewer_pages_expected")
    if (
        isinstance(page_count, bool)
        or not isinstance(page_count, int)
        or page_count < 1
        or manifest.get("viewer_pages_navigated") != page_count
        or manifest.get("page_coverage_complete") is not True
    ):
        raise PublicPreviewCaptureError("Public-preview page navigation evidence is incomplete.")

    files = manifest.get("files")
    required = (
        "page_capture_index", "page_text_snapshots", "records_jsonl",
        "extraction_report", "viewer_capture_manifest",
    )
    if not isinstance(files, dict) or any(key not in files for key in required):
        raise PublicPreviewCaptureError("Sharded capture manifest is missing required evidence hashes.")
    resolved: dict[str, Path] = {}
    for key in required:
        entry = files[key]
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PublicPreviewCaptureError(f"Invalid evidence-file entry: {key}")
        path = _safe_file(repository_root, entry["path"], f"{key} evidence")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or _sha256(path) != expected:
            raise PublicPreviewCaptureError(f"SHA-256 mismatch for {key} evidence.")
        resolved[key] = path

    capture = _read_json(resolved["viewer_capture_manifest"], "viewer capture manifest")
    if (
        capture.get("schema_version") != 1
        or capture.get("capture_method") not in {"ordinary_public_preview_ui", "ordinary_public_page_ui"}
        or capture.get("page_coverage_complete") is not True
        or capture.get("viewer_pages_expected") != page_count
        or capture.get("viewer_pages_captured") != page_count
        or capture.get("pdf_downloaded") is not False
        or capture.get("access_controls_bypassed") is not False
    ):
        raise PublicPreviewCaptureError("Viewer capture manifest does not prove complete, compliant page coverage.")
    screenshot_entries = capture.get("files", {}).get("screenshots")
    if not isinstance(screenshot_entries, list) or len(screenshot_entries) != page_count:
        raise PublicPreviewCaptureError("A screenshot must be retained for every captured viewer page.")
    for page_number, entry in enumerate(screenshot_entries, start=1):
        if not isinstance(entry, dict) or entry.get("viewer_page") != page_number:
            raise PublicPreviewCaptureError("Screenshot evidence has a page gap or ordering error.")
        screenshot = _safe_file(repository_root, entry.get("path"), "viewer screenshot")
        if _sha256(screenshot) != entry.get("sha256"):
            raise PublicPreviewCaptureError(f"Screenshot hash mismatch for viewer page {page_number}.")

    try:
        page_index = json.loads(resolved["page_capture_index"].read_text(encoding="utf-8"))
        snapshots = [
            json.loads(line)
            for line in resolved["page_text_snapshots"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Cannot parse captured page text evidence: {exc}") from exc
    if (
        not isinstance(page_index, list)
        or len(page_index) != page_count
        or len(snapshots) != page_count
    ):
        raise PublicPreviewCaptureError("Captured page text evidence does not cover every viewer page.")
    for page_number, (index_item, snapshot) in enumerate(zip(page_index, snapshots), start=1):
        if (
            not isinstance(index_item, dict)
            or not isinstance(snapshot, dict)
            or index_item.get("viewer_page") != page_number
            or snapshot.get("viewer_page") != page_number
            or index_item.get("sha256") != hashlib.sha256(str(snapshot.get("text", "")).encode("utf-8")).hexdigest()
            or index_item.get("screenshot_sha256") != screenshot_entries[page_number - 1].get("sha256")
        ):
            raise PublicPreviewCaptureError(f"Rendered text evidence is inconsistent on viewer page {page_number}.")

    extraction = _read_json(resolved["extraction_report"], "extraction report")
    mapping_key = batch.get("public_preview_mapping_key")
    if not isinstance(mapping_key, str) or not mapping_key:
        raise PublicPreviewCaptureError("Reviewed public-preview mapping key is required.")
    mapping_path = _safe_file(
        repository_root,
        "python-engine/config/adapter_mappings.json",
        "reviewed adapter mappings",
    )
    mapping_config = _read_json(mapping_path, "reviewed adapter mappings")
    mapping = mapping_config.get(mapping_key)
    if not isinstance(mapping, dict):
        raise PublicPreviewCaptureError("Source-specific public-preview mapping is not configured.")
    mapping_bytes = json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if extraction.get("mapping_key") != mapping_key or extraction.get("mapping_sha256") != hashlib.sha256(mapping_bytes).hexdigest():
        raise PublicPreviewCaptureError("Extraction report does not match the currently reviewed mapping.")
    try:
        parsed_records = parse_public_preview_snapshots(snapshots, mapping)
    except (KeyError, TypeError) as exc:
        raise PublicPreviewCaptureError(f"Rendered page snapshot is invalid: {exc}") from exc

    announced = batch.get("announced_count")
    sequences = [sequence for sequence, _name in parsed_records]
    if (
        len(parsed_records) != announced
        or sorted(sequences) != list(range(1, announced + 1))
        or len(set(sequences)) != len(sequences)
    ):
        raise PublicPreviewCaptureError("Rendered content does not match the announced count and exact sequence range.")
    if len({" ".join(name.split()).casefold() for _sequence, name in parsed_records}) != announced:
        raise PublicPreviewCaptureError("Rendered content contains duplicate passer names.")
    if (
        extraction.get("announced_count") != announced
        or extraction.get("extracted_records") != announced
        or extraction.get("sequence_coverage_complete") is not True
        or extraction.get("duplicate_sequence_count") != 0
        or extraction.get("duplicate_name_count") != 0
    ):
        raise PublicPreviewCaptureError("Extraction report does not prove complete, duplicate-free records.")

    try:
        stored_records = [
            json.loads(line)
            for line in resolved["records_jsonl"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Cannot parse extracted JSONL records: {exc}") from exc
    expected_records = [
        {"seq": str(sequence), "name": name}
        for sequence, name in parsed_records
    ]
    if stored_records != expected_records:
        raise PublicPreviewCaptureError("Extracted records do not exactly match the rendered official text.")
    records_hash = hashlib.sha256(resolved["records_jsonl"].read_bytes()).hexdigest()
    if extraction.get("records_jsonl_sha256") != records_hash:
        raise PublicPreviewCaptureError("Extraction report record hash does not match the captured records.")
    return [
        {"sequence_number": record["seq"], "name": record["name"]}
        for record in stored_records
    ], {
        "capture_manifest": str(manifest_path.relative_to(repository_root)),
        "capture_manifest_sha256": _sha256(manifest_path),
        "records_file_sha256": records_hash,
        "public_preview_url": batch["public_preview_url"],
        "viewer_pages": page_count,
        "visual_review_status": "PENDING",
    }
