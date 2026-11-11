"""Create a locally reviewable bundle from a validated public-preview capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from acquisition.public_preview import (
    PublicPreviewCaptureError,
    load_public_preview_capture,
    parse_public_preview_records,
)

MAX_BUNDLE_BYTES = 50 * 1024 * 1024


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Unable to read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicPreviewCaptureError(f"{label} must be a JSON object.")
    return value


def _root_file(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PublicPreviewCaptureError(f"{label} path is missing.")
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PublicPreviewCaptureError(f"{label} must remain inside the repository.") from exc
    if not path.is_file():
        raise PublicPreviewCaptureError(f"{label} does not exist: {value}")
    return path


def create_review_bundle(
    batch_path: str | Path,
    output_path: str | Path,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    repository_root = Path(root or Path.cwd()).resolve()
    batch_file = _root_file(repository_root, str(batch_path), "Release batch")
    batch = _read_json(batch_file, "release batch")
    if batch.get("official_content_mode") != "public_preview_capture":
        raise PublicPreviewCaptureError("Review bundles require a public-preview capture batch.")

    records, capture_evidence = load_public_preview_capture(batch=batch, root=repository_root)
    source_manifest_path = _root_file(repository_root, batch.get("capture_manifest"), "Capture manifest")
    source_manifest = _read_json(source_manifest_path, "capture manifest")
    files = source_manifest.get("files")
    if not isinstance(files, dict):
        raise PublicPreviewCaptureError("Capture manifest has no evidence file index.")
    record_by_sequence = {record["sequence_number"]: record["name"] for record in records}
    evidence: list[dict[str, Any]] = []
    if source_manifest.get("schema_version") == 1:
        visual_entry = files.get("visual_report")
        if not isinstance(visual_entry, dict):
            raise PublicPreviewCaptureError("Capture manifest has no visual report reference.")
        visual_path = _root_file(repository_root, visual_entry.get("path"), "Visual review report")
        visual_report = _read_json(visual_path, "visual review report")
        results = visual_report.get("results")
        if not isinstance(results, list):
            raise PublicPreviewCaptureError("Visual review report has no evidence results.")
        for result in results:
            if not isinstance(result, dict):
                raise PublicPreviewCaptureError("Visual review report contains an invalid evidence item.")
            sequence = str(result.get("sequence"))
            if (
                sequence not in record_by_sequence
                or result.get("viewer_text_confirmed") is not True
                or not isinstance(result.get("expected_visible_text"), str)
                or not result["expected_visible_text"].strip()
                or any(item["sequence_number"] == sequence for item in evidence)
            ):
                raise PublicPreviewCaptureError("Visual evidence references a sequence outside the candidate.")
            screenshot_path = _root_file(
                repository_root,
                result.get("screenshot"),
                f"Viewer screenshot for sequence {sequence}",
            )
            screenshot_bytes = screenshot_path.read_bytes()
            screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()
            if screenshot_hash != result.get("screenshot_sha256"):
                raise PublicPreviewCaptureError(f"Screenshot hash mismatch for sequence {sequence}.")
            evidence.append({
                "sequence_number": sequence,
                "expected_visible_text": result.get("expected_visible_text"),
                "viewer_text_confirmed": result.get("viewer_text_confirmed"),
                "sha256": screenshot_hash,
                "screenshot_path": screenshot_path.relative_to(repository_root).as_posix(),
            })
        if {item.get("sequence_number") for item in evidence} != set(record_by_sequence):
            raise PublicPreviewCaptureError("Visual evidence does not cover every validated candidate record.")
    elif source_manifest.get("schema_version") == 2:
        evidence = _create_sharded_evidence(
            repository_root=repository_root,
            batch=batch,
            files=files,
            record_by_sequence=record_by_sequence,
        )
    else:
        raise PublicPreviewCaptureError("Unsupported capture manifest schema for review bundle creation.")

    canonical_records = [
        {"name": record["name"], "sequence_number": record["sequence_number"]}
        for record in records
    ]
    bundle = {
        "schema_version": 1,
        "authority": batch["authority"],
        "exam": batch["exam"],
        "year": batch["year"],
        "announced_count": batch["announced_count"],
        "record_count": len(records),
        "candidate_sha256": hashlib.sha256(
            json.dumps(canonical_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "capture_manifest_sha256": capture_evidence["capture_manifest_sha256"],
        "official_article_url": batch["official_article_url"],
        "official_content_url": batch["official_content_url"],
        "public_preview_url": batch["public_preview_url"],
        "records": canonical_records,
        "evidence": evidence,
    }
    destination = (repository_root / str(output_path)).resolve()
    try:
        destination.relative_to(repository_root)
    except ValueError as exc:
        raise PublicPreviewCaptureError("Review bundle output must remain inside the repository.") from exc
    encoded = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_BUNDLE_BYTES:
        raise PublicPreviewCaptureError("Generated review bundle exceeds the 50 MiB browser limit.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return bundle


def _create_sharded_evidence(
    *,
    repository_root: Path,
    batch: dict[str, Any],
    files: dict[str, Any],
    record_by_sequence: dict[str, str],
) -> list[dict[str, Any]]:
    viewer_manifest_entry = files.get("viewer_capture_manifest")
    if not isinstance(viewer_manifest_entry, dict):
        raise PublicPreviewCaptureError("Capture manifest has no viewer capture manifest reference.")
    capture_manifest_path = _root_file(
        repository_root,
        viewer_manifest_entry.get("path"),
        "Viewer capture manifest",
    )
    viewer_manifest = _read_json(capture_manifest_path, "viewer capture manifest")
    viewer_files = viewer_manifest.get("files")
    screenshot_entries = viewer_files.get("screenshots") if isinstance(viewer_files, dict) else None
    if not isinstance(screenshot_entries, list):
        raise PublicPreviewCaptureError("Viewer capture manifest has no screenshot list.")

    snapshots_entry = files.get("page_text_snapshots")
    if not isinstance(snapshots_entry, dict):
        raise PublicPreviewCaptureError("Capture manifest has no page text snapshot reference.")
    snapshot_path = _root_file(repository_root, snapshots_entry.get("path"), "Page text snapshots")
    try:
        snapshots = [
            json.loads(line)
            for line in snapshot_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicPreviewCaptureError(f"Unable to parse page text snapshots: {exc}") from exc

    mapping_key = batch.get("public_preview_mapping_key")
    mapping_path = _root_file(
        repository_root,
        "python-engine/config/adapter_mappings.json",
        "Reviewed adapter mappings",
    )
    mappings = _read_json(mapping_path, "reviewed adapter mappings")
    mapping = mappings.get(mapping_key) if isinstance(mapping_key, str) else None
    if not isinstance(mapping, dict):
        raise PublicPreviewCaptureError("Source-specific public-preview mapping is not configured.")
    if len(snapshots) != len(screenshot_entries):
        raise PublicPreviewCaptureError("Screenshot and rendered-text page counts do not match.")

    seen: set[str] = set()
    evidence: list[dict[str, Any]] = []
    for page_number, (snapshot, screenshot_entry) in enumerate(
        zip(snapshots, screenshot_entries),
        start=1,
    ):
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("viewer_page") != page_number
            or not isinstance(screenshot_entry, dict)
            or screenshot_entry.get("viewer_page") != page_number
            or not isinstance(snapshot.get("text"), str)
        ):
            raise PublicPreviewCaptureError(f"Capture evidence is out of order on page {page_number}.")
        page_records = parse_public_preview_records(
            snapshot["text"],
            mapping,
            require_records=False,
        )
        new_records: list[tuple[str, str]] = []
        for sequence, name in page_records:
            sequence_text = str(sequence)
            if sequence_text in seen:
                continue
            if record_by_sequence.get(sequence_text) != name:
                raise PublicPreviewCaptureError(
                    f"Page {page_number} contains a record that differs from the validated candidate."
                )
            seen.add(sequence_text)
            new_records.append((sequence_text, name))
        if not new_records:
            continue
        screenshot_path = _root_file(
            repository_root,
            screenshot_entry.get("path"),
            f"Viewer screenshot for page {page_number}",
        )
        screenshot_bytes = screenshot_path.read_bytes()
        screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()
        if screenshot_hash != screenshot_entry.get("sha256"):
            raise PublicPreviewCaptureError(f"Screenshot hash mismatch on page {page_number}.")
        evidence.append({
            "viewer_page": page_number,
            "sequence_numbers": [sequence for sequence, _name in new_records],
            "expected_visible_text": "\n".join(
                f"{sequence} {name}" for sequence, name in new_records
            ),
            "viewer_text_confirmed": True,
            "sha256": screenshot_hash,
            "screenshot_path": screenshot_path.relative_to(repository_root).as_posix(),
        })

    if seen != set(record_by_sequence):
        raise PublicPreviewCaptureError("Screenshot evidence does not cover every validated candidate record.")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local owner-review bundle.")
    parser.add_argument("--batch", required=True, help="Repository-relative validated release-batch JSON.")
    parser.add_argument("--out", required=True, help="Repository-relative output JSON path.")
    args = parser.parse_args()
    try:
        bundle = create_review_bundle(args.batch, args.out)
    except (PublicPreviewCaptureError, OSError, ValueError, TypeError) as exc:
        print(f"REVIEW BUNDLE NOT CREATED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "output": args.out,
        "records": bundle["record_count"],
        "evidence_pages": len(bundle["evidence"]),
        "candidate_sha256": bundle["candidate_sha256"],
        "capture_manifest_sha256": bundle["capture_manifest_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
