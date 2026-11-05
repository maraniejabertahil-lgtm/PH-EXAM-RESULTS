"""Validate every committed public dataset manifest and its immutable shards."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "python-engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from processor.greenlight import records_sha256, validate_records  # noqa: E402

EXPECTED_COLUMNS = ["name", "rating", "region", "seq"]


class DatasetValidationError(RuntimeError):
    pass


def validate_manifest(manifest_path: Path) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"{manifest_path}: cannot read manifest: {exc}") from exc

    if not isinstance(manifest, dict):
        raise DatasetValidationError(f"{manifest_path}: manifest must be an object")
    required = {
        "schema_version", "authority", "exam", "year", "provenance",
        "columns", "record_count", "announced_count", "greenlight_score",
        "records_sha256", "shard_count", "max_shard_bytes", "shards",
    }
    missing = required - manifest.keys()
    if missing:
        raise DatasetValidationError(f"{manifest_path}: missing keys {sorted(missing)}")
    if manifest["schema_version"] != 1 or manifest["columns"] != EXPECTED_COLUMNS:
        raise DatasetValidationError(f"{manifest_path}: unsupported schema or columns")
    if manifest["greenlight_score"] != 100 or manifest["provenance"] not in {
        "official_direct", "third_party_fallback"
    }:
        raise DatasetValidationError(f"{manifest_path}: dataset is not Greenlight-approved")
    if manifest["record_count"] != manifest["announced_count"]:
        raise DatasetValidationError(f"{manifest_path}: announced count mismatch")
    if not isinstance(manifest["shards"], list) or len(manifest["shards"]) != manifest["shard_count"]:
        raise DatasetValidationError(f"{manifest_path}: shard_count mismatch")

    rows: list[list] = []
    total_bytes = 0
    seen_files: set[str] = set()
    for entry in manifest["shards"]:
        filename = entry.get("file")
        if not isinstance(filename, str) or Path(filename).name != filename or filename in seen_files:
            raise DatasetValidationError(f"{manifest_path}: unsafe or duplicate shard filename")
        seen_files.add(filename)
        shard_path = manifest_path.parent / filename
        try:
            raw = shard_path.read_bytes()
            shard = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DatasetValidationError(f"{shard_path}: cannot read shard: {exc}") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != entry.get("size_bytes") or digest != entry.get("sha256"):
            raise DatasetValidationError(f"{shard_path}: size or SHA-256 mismatch")
        if len(raw) > manifest["max_shard_bytes"]:
            raise DatasetValidationError(f"{shard_path}: exceeds maximum shard size")
        if not isinstance(shard, dict) or shard.get("columns") != EXPECTED_COLUMNS:
            raise DatasetValidationError(f"{shard_path}: invalid shard columns")
        data = shard.get("data")
        if not isinstance(data, list) or len(data) != entry.get("record_count"):
            raise DatasetValidationError(f"{shard_path}: record_count mismatch")
        if any(not isinstance(row, list) or len(row) != len(EXPECTED_COLUMNS) for row in data):
            raise DatasetValidationError(f"{shard_path}: malformed Array-of-Arrays row")
        rows.extend(data)
        total_bytes += len(raw)

    if len(rows) != manifest["record_count"]:
        raise DatasetValidationError(f"{manifest_path}: total record_count mismatch")

    records = [
        {"name": row[0], "sequence_number": row[3]}
        for row in rows
    ]
    records.sort(key=lambda item: int(item["sequence_number"]) if str(item["sequence_number"]).isdigit() else -1)
    if records_sha256(records) != manifest["records_sha256"]:
        raise DatasetValidationError(f"{manifest_path}: canonical records SHA-256 mismatch")
    report = validate_records(records, announced_count=manifest["announced_count"], provenance=manifest["provenance"])
    if report["status"] != "GREENLIGHT" or report["greenlight_score"] != 100:
        raise DatasetValidationError(f"{manifest_path}: reconstructed records failed Greenlight")
    return {
        "manifest": str(manifest_path.relative_to(ROOT)),
        "records": len(records),
        "shards": len(seen_files),
        "bytes": total_bytes,
        "records_sha256": manifest["records_sha256"],
    }


def validate_site_catalogue(catalogue_path: Path, dataset_manifests: list[Path]) -> dict:
    """Validate schema-v2 website routing against each hash-bound exam manifest."""
    try:
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"{catalogue_path}: cannot read site catalogue: {exc}") from exc
    if (not isinstance(catalogue, dict) or catalogue.get("schema_version") != 2
            or not isinstance(catalogue.get("authorities"), dict)):
        raise DatasetValidationError(f"{catalogue_path}: unsupported site catalogue schema")

    expected = {}
    for path in dataset_manifests:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetValidationError(f"{path}: cannot read exam manifest: {exc}") from exc
        key = (str(item.get("authority")), str(item.get("exam")), str(item.get("year")))
        if key in expected:
            raise DatasetValidationError(f"{path}: duplicate authority/exam/year manifest")
        expected[key] = (path, item)

    seen = set()
    entry_count = 0
    for authority, authority_item in catalogue["authorities"].items():
        if authority not in {"PRC", "CSC"} or not isinstance(authority_item, dict):
            raise DatasetValidationError(f"{catalogue_path}: invalid authority entry")
        exams = authority_item.get("examinations")
        if not isinstance(exams, dict):
            raise DatasetValidationError(f"{catalogue_path}: invalid examinations catalogue")
        for exam, exam_item in exams.items():
            if not isinstance(exam_item, dict) or not isinstance(exam_item.get("years"), dict):
                raise DatasetValidationError(f"{catalogue_path}: invalid exam years")
            for year, year_item in exam_item["years"].items():
                key = (authority, exam, str(year))
                if key not in expected or key in seen:
                    raise DatasetValidationError(f"{catalogue_path}: missing or duplicate exam manifest {key}")
                seen.add(key)
                files = year_item.get("files") if isinstance(year_item, dict) else None
                manifest_path, manifest = expected[key]
                shards = manifest.get("shards")
                if not isinstance(files, dict) or not isinstance(shards, list) or len(files) != len(shards):
                    raise DatasetValidationError(f"{catalogue_path}: shard routing count mismatch for {key}")
                for index, shard in enumerate(shards, start=1):
                    shard_id = f"S{index:03d}"
                    entry = files.get(shard_id)
                    filename = shard.get("file") if isinstance(shard, dict) else None
                    digest = shard.get("sha256") if isinstance(shard, dict) else None
                    count = shard.get("record_count") if isinstance(shard, dict) else None
                    size = shard.get("size_bytes") if isinstance(shard, dict) else None
                    expected_path = f"/data/{authority}/{exam}/{year}/{filename}"
                    if (not isinstance(entry, dict) or entry.get("path") != expected_path
                            or entry.get("hash") != digest or entry.get("record_count") != count
                            or entry.get("size_bytes") != size):
                        raise DatasetValidationError(f"{catalogue_path}: catalogue shard mismatch for {key}/{shard_id}")
                    shard_path = (ROOT / "public" / entry["path"].lstrip("/")).resolve()
                    try:
                        shard_path.relative_to((ROOT / "public").resolve())
                        raw = shard_path.read_bytes()
                    except (ValueError, OSError) as exc:
                        raise DatasetValidationError(f"{catalogue_path}: unsafe or missing routed shard {entry['path']}") from exc
                    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
                        raise DatasetValidationError(f"{catalogue_path}: routed shard hash/size mismatch for {entry['path']}")
                    entry_count += 1

    if seen != set(expected):
        raise DatasetValidationError(f"{catalogue_path}: one or more exam manifests are absent from the site catalogue")
    return {"site_catalogue": str(catalogue_path.relative_to(ROOT)), "exams": len(seen), "shards": entry_count}


def main() -> int:
    data_root = ROOT / "public" / "data"
    catalogue_path = data_root / "manifest.json"
    manifests = sorted(path for path in data_root.rglob("manifest.json") if path != catalogue_path) if data_root.exists() else []
    if not manifests and not catalogue_path.exists():
        print("No public dataset manifests found; nothing to validate.")
        return 0
    failures = []
    if catalogue_path.exists():
        try:
            catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
            if isinstance(catalogue, dict) and catalogue.get("schema_version") == 2:
                print(json.dumps(validate_site_catalogue(catalogue_path, manifests), ensure_ascii=False))
            else:
                print(json.dumps(validate_manifest(catalogue_path), ensure_ascii=False))
        except (DatasetValidationError, OSError, json.JSONDecodeError) as exc:
            failures.append(str(exc))
    for path in manifests:
        try:
            print(json.dumps(validate_manifest(path), ensure_ascii=False))
        except DatasetValidationError as exc:
            failures.append(str(exc))
    if failures:
        for failure in failures:
            print(f"DATASET VALIDATION FAILED: {failure}", file=sys.stderr)
        return 1
    print(f"Validated {len(manifests)} public dataset manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
