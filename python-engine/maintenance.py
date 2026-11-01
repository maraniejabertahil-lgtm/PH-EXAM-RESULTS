#!/usr/bin/env python3
"""Validate published static datasets before deployment or during maintenance."""

import hashlib
import json
import re
import sys
from pathlib import Path


EXPECTED_COLUMNS = ["name", "rating", "region", "seq"]
MAX_ASSET_BYTES = 10 * 1024 * 1024
SHARD_FILENAME_PATTERN = re.compile(
    r"^\d{4}-(?:[A-Z]-[A-Z]|OTHER)(?:-(?P<content_hash>[a-f0-9]{64}))?\.json$"
)


def validate_public_directory(public_root: str | Path) -> list[str]:
    root = Path(public_root).resolve()
    errors = []
    manifest_path = root / "data" / "manifest.json"
    status_path = root / "data" / "site-status.json"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read manifest: {exc}"]

    if not isinstance(manifest, dict):
        return ["Manifest must be a JSON object."]
    if manifest.get("schema_version") != 2:
        errors.append("Unsupported manifest schema version.")
    authorities = manifest.get("authorities")
    if not isinstance(authorities, dict):
        return errors + ["Manifest authorities must be an object."]

    for authority, authority_data in authorities.items():
        if authority not in {"PRC", "CSC"}:
            errors.append(f"Unsupported authority in manifest: {authority}")
            continue
        if not isinstance(authority_data, dict) or not isinstance(authority_data.get("examinations"), dict):
            errors.append(f"Invalid examination catalogue for authority: {authority}")
            continue
        for exam, exam_data in authority_data["examinations"].items():
            if not isinstance(exam, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", exam):
                errors.append(f"Invalid examination identifier in manifest: {exam}")
                continue
            if not isinstance(exam_data, dict) or not isinstance(exam_data.get("years"), dict):
                errors.append(f"Invalid year catalogue for {authority}/{exam}")
                continue
            for year, year_data in exam_data["years"].items():
                if not re.fullmatch(r"\d{4}", str(year)):
                    errors.append(f"Invalid result year in manifest: {year}")
                    continue
                if not isinstance(year_data, dict) or not isinstance(year_data.get("files"), dict):
                    errors.append(f"Invalid dataset shard catalogue for {authority}/{exam}/{year}")
                    continue
                for shard, entry in year_data["files"].items():
                    if not re.fullmatch(r"(?:[A-Z]-[A-Z]|OTHER)", str(shard)):
                        errors.append(f"Invalid shard key in manifest: {shard}")
                        continue
                    if not isinstance(entry, dict):
                        errors.append(f"Invalid dataset entry for {authority}/{exam}/{year}/{shard}")
                        continue
                    relative = str(entry.get("path", "")).lstrip("/")
                    target = (root / relative).resolve()
                    if root not in target.parents:
                        errors.append(f"Dataset path escapes public directory: {entry.get('path')}")
                        continue
                    try:
                        raw = target.read_bytes()
                    except OSError as exc:
                        errors.append(f"Missing dataset {entry.get('path')}: {exc}")
                        continue
                    if len(raw) > MAX_ASSET_BYTES:
                        errors.append(f"Dataset exceeds 10 MiB: {entry.get('path')}")
                    actual_hash = hashlib.sha256(raw).hexdigest()
                    if actual_hash != entry.get("hash"):
                        errors.append(f"Hash mismatch: {entry.get('path')}")
                    filename_match = SHARD_FILENAME_PATTERN.fullmatch(target.name)
                    if not filename_match:
                        errors.append(f"Invalid dataset shard filename: {entry.get('path')}")
                    elif (
                        filename_match.group("content_hash")
                        and filename_match.group("content_hash") != actual_hash
                    ):
                        errors.append(f"Filename hash mismatch: {entry.get('path')}")
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        errors.append(f"Invalid JSON: {entry.get('path')}")
                        continue
                    if not isinstance(payload, dict):
                        errors.append(f"Dataset payload must be an object: {entry.get('path')}")
                        continue
                    if payload.get("columns") != EXPECTED_COLUMNS:
                        errors.append(f"Unexpected columns: {entry.get('path')}")
                    rows = payload.get("data")
                    if not isinstance(rows, list):
                        errors.append(f"Dataset data must be an array: {entry.get('path')}")
                        continue
                    if len(rows) != entry.get("record_count"):
                        errors.append(f"Record count mismatch: {entry.get('path')}")
                    for row_number, row in enumerate(rows, start=1):
                        if not isinstance(row, list) or len(row) != len(EXPECTED_COLUMNS):
                            errors.append(f"Invalid row {row_number}: {entry.get('path')}")
                            break
                        if not isinstance(row[0], str) or not row[0].strip():
                            errors.append(f"Missing name at row {row_number}: {entry.get('path')}")
                            break

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(status, dict):
            errors.append("Site status must be a JSON object.")
            status = {}
        if status.get("schema_version") != 1:
            errors.append("Unsupported site-status schema version.")
        if status.get("mode") not in {"search", "preparing"}:
            errors.append("site-status mode must be search or preparing.")
        if status.get("mode") == "preparing":
            preparation = status.get("preparation") or {}
            if not isinstance(preparation.get("percentage"), (int, float)):
                errors.append("Preparing mode requires a numeric progress percentage.")
            if not str(preparation.get("examination_name", "")).strip():
                errors.append("Preparing mode requires an examination name.")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read site status: {exc}")

    return errors


if __name__ == "__main__":
    public_root = Path(__file__).resolve().parents[1] / "public"
    failures = validate_public_directory(public_root)
    if failures:
        for failure in failures:
            print("ERROR:", failure)
        raise SystemExit(1)
    print("Public manifest, datasets, hashes, record counts, and site status are valid.")
