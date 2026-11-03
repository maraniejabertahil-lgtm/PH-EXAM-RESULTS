"""Build Greenlight-gated Array-of-Arrays JSON datasets and size-limited shards.

The builder writes content-addressed shard files and atomically replaces the
manifest last. Existing shards are never deleted, so a failed build cannot
remove the last known-good manifest or its referenced data files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

from processor.greenlight import records_sha256

COLUMNS = ["name", "rating", "region", "seq"]
DEFAULT_MAX_SHARD_BYTES = 10 * 1024 * 1024
_EXAM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_SEQUENCE_PATTERN = re.compile(r"^[0-9]+$")


class DatasetBuildError(RuntimeError):
    """Raised when dataset input is invalid or a safe build cannot complete."""


def _json_bytes(payload: dict[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DatasetBuildError(f"Dataset contains a non-JSON value: {exc}") from exc
    return rendered.encode("utf-8")


def _validate_record(record: dict[str, Any], index: int) -> list[Any]:
    if not isinstance(record, dict):
        raise DatasetBuildError(f"Record {index} must be a dictionary.")
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DatasetBuildError(f"Record {index} has a blank or invalid name.")
    sequence = record.get("sequence_number")
    if isinstance(sequence, bool) or not isinstance(sequence, (str, int)):
        raise DatasetBuildError(f"Record {index} has an invalid sequence number.")
    sequence_text = str(sequence)
    sequence_check = sequence_text.strip()
    if not _SEQUENCE_PATTERN.fullmatch(sequence_check) or int(sequence_check) < 1:
        raise DatasetBuildError(f"Record {index} sequence number must be a positive integer string.")

    rating = record.get("rating")
    if isinstance(rating, bool) or not (
        rating is None or isinstance(rating, (str, int, float))
    ):
        raise DatasetBuildError(f"Record {index} has an unsupported rating value.")
    if isinstance(rating, float) and not math.isfinite(rating):
        raise DatasetBuildError(f"Record {index} rating must be finite.")

    region = record.get("region")
    if region is not None and not isinstance(region, str):
        raise DatasetBuildError(f"Record {index} region must be text or null.")
    # Only the public schema fields are emitted. Sequence text remains a string
    # so values such as 001 are not converted to 1.
    return [name, rating, region, sequence_text]


def _initial(name: str) -> str:
    for character in name:
        if character.isalpha() or character.isdigit():
            upper = character.upper()
            return upper if len(upper) == 1 and "A" <= upper <= "Z" else "OTHER"
    return "OTHER"


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DatasetBuildError(f"Unable to write dataset artifact {path.name}: {exc}") from exc


def _partition_rows(rows: list[list[Any]], max_bytes: int) -> list[list[list[Any]]]:
    if not rows:
        return [[]]
    chunks: list[list[list[Any]]] = []
    current: list[list[Any]] = []
    for row in rows:
        candidate = current + [row]
        candidate_size = len(_json_bytes({"columns": COLUMNS, "data": candidate}))
        if candidate_size <= max_bytes:
            current = candidate
            continue
        if not current:
            raise DatasetBuildError(
                f"A single record requires {candidate_size} bytes, exceeding the {max_bytes}-byte shard limit."
            )
        chunks.append(current)
        current = [row]
        single_size = len(_json_bytes({"columns": COLUMNS, "data": current}))
        if single_size > max_bytes:
            raise DatasetBuildError(
                f"A single record requires {single_size} bytes, exceeding the {max_bytes}-byte shard limit."
            )
    if current:
        chunks.append(current)
    return chunks


def build_dataset(
    records: Iterable[dict[str, Any]],
    *,
    authority: str,
    exam: str,
    year: int,
    output_dir: str | Path,
    greenlight_report: dict[str, Any],
    provenance: str = "official_direct",
    max_shard_bytes: int = DEFAULT_MAX_SHARD_BYTES,
) -> dict[str, Any]:
    """Write an Array-of-Arrays dataset only when Greenlight score is exactly 100."""
    if authority not in {"PRC", "CSC"}:
        raise DatasetBuildError("authority must be PRC or CSC.")
    if not isinstance(exam, str) or not _EXAM_PATTERN.fullmatch(exam):
        raise DatasetBuildError("exam must be a safe identifier using letters, digits, dot, underscore, or hyphen.")
    if isinstance(year, bool) or not isinstance(year, int) or year < 1900 or year > 2200:
        raise DatasetBuildError("year must be a four-digit integer between 1900 and 2200.")
    if provenance not in {"official_direct", "third_party_fallback"}:
        raise DatasetBuildError("Unsupported dataset provenance.")
    if not isinstance(max_shard_bytes, int) or max_shard_bytes <= 0:
        raise DatasetBuildError("max_shard_bytes must be a positive integer.")

    if not isinstance(greenlight_report, dict):
        raise DatasetBuildError("A Greenlight validation report is required.")
    checks = greenlight_report.get("checks")
    if (
        greenlight_report.get("status") != "GREENLIGHT"
        or greenlight_report.get("greenlight_score") != 100
        or greenlight_report.get("publication_allowed") is not True
        or greenlight_report.get("provenance") != provenance
        or not isinstance(checks, dict)
        or not checks
        or not all(value is True for value in checks.values())
    ):
        raise DatasetBuildError("Publication denied: the supplied Greenlight report is not a complete 100-point pass.")

    try:
        source_rows = list(records)
    except TypeError as exc:
        raise DatasetBuildError("records must be an iterable of record dictionaries.") from exc
    if len(source_rows) != greenlight_report.get("record_count"):
        raise DatasetBuildError("Record count does not match the Greenlight report.")
    if len(source_rows) != greenlight_report.get("announced_count"):
        raise DatasetBuildError("Record count does not match the authority's announced count.")

    if greenlight_report.get("records_sha256") != records_sha256(source_rows):
        raise DatasetBuildError("The supplied records do not match the exact rows evaluated by Greenlight.")

    rows = [_validate_record(record, index) for index, record in enumerate(source_rows, start=1)]
    # Alphabetical ordering supports predictable name-range shards. Sequence
    # values are retained in the output and can still be searched/displayed.
    rows.sort(key=lambda row: (row[0].casefold(), row[0], int(row[3])))
    chunks = _partition_rows(rows, max_shard_bytes)

    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    shard_entries: list[dict[str, Any]] = []
    range_counts: dict[tuple[str, str], int] = {}

    for index, chunk in enumerate(chunks, start=1):
        payload = {"columns": COLUMNS, "data": chunk}
        content = _json_bytes(payload)
        if len(content) > max_shard_bytes:
            raise DatasetBuildError("Internal shard sizing check failed; refusing to write oversized JSON.")
        digest = hashlib.sha256(content).hexdigest()
        first_initial = _initial(chunk[0][0]) if chunk else "OTHER"
        last_initial = _initial(chunk[-1][0]) if chunk else "OTHER"
        if len(chunks) == 1:
            base_name = str(year)
        else:
            range_key = (first_initial, last_initial)
            range_counts[range_key] = range_counts.get(range_key, 0) + 1
            part = range_counts[range_key]
            base_name = f"{year}-{first_initial}-{last_initial}-{part:03d}"
        file_name = f"{base_name}-{digest[:12]}.json"
        _atomic_write(destination / file_name, content)
        shard_entries.append({
            "file": file_name,
            "size_bytes": len(content),
            "sha256": digest,
            "record_count": len(chunk),
            "first_name": chunk[0][0] if chunk else None,
            "last_name": chunk[-1][0] if chunk else None,
            "first_initial": first_initial,
            "last_initial": last_initial,
        })

    manifest = {
        "schema_version": 1,
        "authority": authority,
        "exam": exam,
        "year": year,
        "provenance": provenance,
        "columns": COLUMNS,
        "record_count": len(rows),
        "announced_count": greenlight_report["announced_count"],
        "greenlight_score": 100,
        "records_sha256": greenlight_report["records_sha256"],
        "source_a_id": greenlight_report.get("source_a_id") if provenance == "third_party_fallback" else None,
        "source_b_id": greenlight_report.get("source_b_id") if provenance == "third_party_fallback" else None,
        "comparison_records_sha256": greenlight_report.get("comparison_records_sha256") if provenance == "third_party_fallback" else None,
        "shard_count": len(shard_entries),
        "max_shard_bytes": max_shard_bytes,
        "shards": shard_entries,
    }
    manifest_bytes = _json_bytes(manifest) + b"\n"
    _atomic_write(destination / "manifest.json", manifest_bytes)
    return manifest
