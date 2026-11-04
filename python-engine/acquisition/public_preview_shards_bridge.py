"""Bridge verified fast page-shard captures into the Python Engine ingestion contract.

This module consumes only the ordered visible-text snapshots produced by
extractor.public_preview_shards. It does not fetch source pages, download PDFs,
repair names, renumber records, or mark human visual review complete.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


class ShardBridgeError(RuntimeError):
    """Raised when sharded capture evidence cannot safely enter extraction."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ShardBridgeError(f"{label} path is required")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ShardBridgeError(f"{label} path escapes its capture directory") from exc
    if not path.is_file():
        raise ShardBridgeError(f"{label} file is missing: {value}")
    return path


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShardBridgeError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ShardBridgeError(f"{label} must be a JSON object")
    return value


def _valid_name(value: str) -> bool:
    if len(value) < 5:
        return False
    punctuation = set(" ,.'’‘-‐‑‒–—_()/") | {'"'}
    return all(
        unicodedata.category(char)[0] in {"L", "M", "N"}
        or char.isspace() or char in punctuation
        for char in value
    )


def _extract_records(page_texts: list[str], announced_count: int) -> tuple[list[dict[str, str]], dict]:
    pattern = re.compile(r"^\s*(\d{1,8})[.)]?\s+(.+?)\s*$")
    rows: dict[int, str] = {}
    occurrences: dict[int, int] = {}
    conflicts: list[dict] = []
    out_of_range: list[dict] = []
    blank_lines = 0

    for text in page_texts:
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            sequence = int(match.group(1))
            name = " ".join(match.group(2).split()).strip(" .")
            if not name:
                blank_lines += 1
                continue
            if not _valid_name(name):
                continue
            if not 1 <= sequence <= announced_count:
                out_of_range.append({"seq": sequence, "name": name})
                continue
            occurrences[sequence] = occurrences.get(sequence, 0) + 1
            if sequence in rows and rows[sequence] != name:
                conflicts.append({"seq": sequence, "first": rows[sequence], "second": name})
            else:
                rows[sequence] = name

    missing = sorted(set(range(1, announced_count + 1)) - set(rows))
    duplicate_sequences = sorted(seq for seq, count in occurrences.items() if count > 1)
    from collections import Counter
    name_counts = Counter(rows.values())
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
    records = [{"seq": str(seq), "name": rows[seq]} for seq in sorted(rows)]
    issues = {
        "missing_sequence_count": len(missing),
        "missing_sequence_sample": missing[:100],
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:100],
        "duplicate_sequence_count": len(duplicate_sequences),
        "duplicate_sequence_sample": duplicate_sequences[:100],
        "out_of_range_record_count": len(out_of_range),
        "out_of_range_record_sample": out_of_range[:100],
        "duplicate_name_count": len(duplicate_names),
        "duplicate_name_sample": duplicate_names[:100],
        "blank_name_count": blank_lines,
        "unresolved_target_record_count": 0,
        "unresolved_target_records": [],
    }
    complete = (
        len(records) == announced_count and not missing and not conflicts
        and not duplicate_sequences and not out_of_range and not duplicate_names
        and blank_lines == 0
    )
    return records, {**issues, "candidate_complete": complete,
                     "extracted_unique_sequences": len(records)}


def build_python_engine_capture_manifest(
    *, capture_dir: str | Path, output_dir: str | Path,
    batch: dict[str, Any], repository_root: str | Path | None = None,
) -> dict:
    """Verify the sharded manifest, extract exact pairs, and write hash-bound evidence."""
    root = Path(repository_root or Path.cwd()).resolve()
    source = Path(capture_dir).resolve()
    destination = Path(output_dir).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ShardBridgeError("output directory must remain inside the repository root") from exc
    destination.mkdir(parents=True, exist_ok=True)
    if batch.get("provenance") != "official_direct":
        raise ShardBridgeError("only official_direct capture may use this bridge")
    announced = batch.get("announced_count")
    if isinstance(announced, bool) or not isinstance(announced, int) or announced < 1:
        raise ShardBridgeError("announced_count must be a positive integer")

    capture_path = _safe_file(source, "capture-manifest.json", "shard capture manifest")
    capture = _read_json(capture_path, "shard capture manifest")
    if (
        capture.get("schema_version") != 1
        or capture.get("capture_method") != "ordinary_public_preview_ui"
        or capture.get("page_coverage_complete") is not True
        or capture.get("pdf_downloaded") is not False
        or capture.get("access_controls_bypassed") is not False
    ):
        raise ShardBridgeError("capture manifest does not satisfy the public-preview safety contract")
    page_count = capture.get("viewer_pages_expected")
    if (
        isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1
        or capture.get("viewer_pages_captured") != page_count
    ):
        raise ShardBridgeError("capture manifest page coverage is incomplete")

    files = capture.get("files")
    if not isinstance(files, dict):
        raise ShardBridgeError("capture manifest files object is missing")
    index_entry = files.get("page_capture_index")
    snapshots_entry = files.get("page_text_snapshots")
    for label, entry in (("page capture index", index_entry), ("page text snapshots", snapshots_entry)):
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            raise ShardBridgeError(f"{label} hash entry is invalid")
    index_path = _safe_file(source, index_entry.get("path"), "page capture index")
    snapshots_path = _safe_file(source, snapshots_entry.get("path"), "page text snapshots")
    if _sha256(index_path) != index_entry["sha256"]:
        raise ShardBridgeError("page capture index SHA-256 mismatch")
    if _sha256(snapshots_path) != snapshots_entry["sha256"]:
        raise ShardBridgeError("page text snapshots SHA-256 mismatch")

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        snapshots = [
            json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShardBridgeError(f"cannot parse merged page snapshots: {exc}") from exc
    expected_pages = list(range(1, page_count + 1))
    if not isinstance(index, list) or [item.get("viewer_page") for item in index] != expected_pages:
        raise ShardBridgeError("page index has a gap, overlap, or ordering error")
    if not isinstance(snapshots, list) or len(snapshots) != page_count:
        raise ShardBridgeError("page snapshot count does not match the viewer page count")
    page_texts = []
    for page, item, indexed in zip(expected_pages, snapshots, index):
        if not isinstance(item, dict) or item.get("viewer_page") != page or not isinstance(item.get("text"), str):
            raise ShardBridgeError(f"invalid page snapshot at viewer page {page}")
        text = item["text"]
        if not text.strip():
            raise ShardBridgeError(f"blank page snapshot at viewer page {page}")
        expected_hash = indexed.get("sha256")
        if expected_hash != hashlib.sha256(text.encode("utf-8")).hexdigest():
            raise ShardBridgeError(f"visible-text hash mismatch at viewer page {page}")
        page_texts.append(text)

    records, extraction = _extract_records(page_texts, announced)
    if not extraction["candidate_complete"]:
        raise ShardBridgeError(
            "extraction did not meet complete sequence/name integrity: "
            + json.dumps({key: extraction[key] for key in (
                "extracted_unique_sequences", "missing_sequence_count", "conflict_count",
                "duplicate_sequence_count", "out_of_range_record_count",
                "duplicate_name_count", "blank_name_count",
            )}, sort_keys=True)
        )

    record_path = destination / "records.jsonl"
    layout_path = destination / "layout-text.txt"
    extraction_path = destination / "extraction-report.json"
    visual_path = destination / "visual-report.json"
    record_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    layout_path.write_text("\n".join(page_texts), encoding="utf-8")

    # The first record screenshot is evidence only; it never marks human review complete.
    screenshot_candidates = sorted(source.glob("shard-*-page-1.png"))
    first_page_records, _ = _extract_records([page_texts[0]], announced)
    if not screenshot_candidates or not first_page_records or first_page_records[0]["seq"] != "1":
        raise ShardBridgeError("first-page screenshot and sequence-1 record evidence are required")
    screenshot_source = screenshot_candidates[0]
    screenshot_path = destination / "first-page.png"
    screenshot_path.write_bytes(screenshot_source.read_bytes())
    screenshot_hash = _sha256(screenshot_path)
    first_name = first_page_records[0]["name"]
    extraction.update({
        "provenance": "official_direct",
        "announced_count": announced,
        "visual_verification_evidence": {
            "1": {"name": first_name, "screenshot_sha256": screenshot_hash}
        },
        "visual_human_review_status": "PENDING",
        "published": False,
    })
    visual = {
        "source": batch.get("public_preview_url"),
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "ocr_is_advisory_only": True,
        "human_visual_verification": "PENDING",
        "results": [{
            "sequence": 1, "name": first_name,
            "expected_visible_text": f"1 {first_name}",
            "viewer_text_confirmed": True,
            "screenshot": screenshot_path.relative_to(root).as_posix(),
            "screenshot_sha256": screenshot_hash,
        }],
    }
    extraction_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    visual_path.write_text(json.dumps(visual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1, "provenance": "official_direct",
        "public_preview_only": True,
        "official_article_url": batch.get("official_article_url"),
        "official_content_url": batch.get("official_content_url"),
        "public_preview_url": batch.get("public_preview_url"),
        "viewer_pages_expected": page_count,
        "viewer_pages_navigated": page_count,
        "snapshots_retained": page_count,
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "files": {
            key: {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
            for key, path in {
                "layout_text": layout_path, "records_jsonl": record_path,
                "extraction_report": extraction_path, "visual_report": visual_path,
            }.items()
        },
    }
    manifest_path = destination / "python-engine-capture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest_path": manifest_path, "manifest": manifest, "record_count": len(records),
            "human_visual_review": "PENDING", "published": False}
