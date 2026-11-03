"""Deterministic Greenlight validation for extracted examination records.

Input contract: each row contains `sequence_number` and `name`. The validator
never repairs, renumbers, fuzzy-matches, or publishes records. It returns a
100 score only when every required integrity check passes; otherwise score 0.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

_SEQUENCE_PATTERN = re.compile(r"^[0-9]+$")


def _sequence_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return None


def _normalized_name_for_duplicate_check(value: str) -> str:
    # Comparison-only normalization. Original extracted names are never changed.
    return " ".join(value.split()).casefold()


def _has_unexpected_characters(value: str) -> bool:
    for character in value:
        if character.isspace():
            continue
        category = unicodedata.category(character)
        if category[0] in {"L", "M", "N", "P", "Z"}:
            continue
        return True
    return False


def validate_records(
    records: Iterable[dict[str, Any]],
    *,
    announced_count: int,
    provenance: str = "official_direct",
) -> dict[str, Any]:
    """Validate extracted rows against the announced count and sequence coverage."""
    issues: list[dict[str, Any]] = []
    if isinstance(announced_count, bool) or not isinstance(announced_count, int) or announced_count < 0:
        raise ValueError("announced_count must be a non-negative integer.")
    if provenance not in {"official_direct", "third_party_fallback"}:
        raise ValueError("provenance must be official_direct or third_party_fallback.")

    if not isinstance(records, Iterable) or isinstance(records, (str, bytes, dict)):
        raise TypeError("records must be an iterable of row dictionaries.")
    rows = list(records)
    record_count = len(rows)
    count_match = record_count == announced_count
    if not count_match:
        issues.append({
            "code": "ANNOUNCED_COUNT_MISMATCH",
            "record_indices": [],
            "message": f"Extracted {record_count} records; authority announced {announced_count}.",
        })

    blank_indices: list[int] = []
    duplicate_name_indices: list[int] = []
    duplicate_sequence_indices: list[int] = []
    anomaly_indices: list[int] = []
    parsed_sequences: list[tuple[int, int]] = []
    seen_names: dict[str, int] = {}
    seen_sequences: dict[int, int] = {}

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            anomaly_indices.append(index)
            issues.append({
                "code": "INVALID_RECORD_TYPE",
                "record_indices": [index],
                "message": "Each extracted record must be a dictionary.",
            })
            continue

        name_value = row.get("name")
        if not isinstance(name_value, str) or not name_value.strip():
            blank_indices.append(index)
            issues.append({
                "code": "BLANK_NAME",
                "record_indices": [index],
                "message": "Record has a missing, non-text, or blank name.",
            })
        else:
            if _has_unexpected_characters(name_value):
                anomaly_indices.append(index)
                issues.append({
                    "code": "UNEXPECTED_NAME_CHARACTER",
                    "record_indices": [index],
                    "message": "Name contains a character outside the permitted Unicode letter, mark, number, punctuation, or spacing categories.",
                })
            normalized_name = _normalized_name_for_duplicate_check(name_value)
            if normalized_name in seen_names:
                duplicate_name_indices.extend([seen_names[normalized_name], index])
                issues.append({
                    "code": "DUPLICATE_NAME",
                    "record_indices": sorted(set([seen_names[normalized_name], index])),
                    "message": "Name duplicates an earlier record after case and whitespace comparison.",
                })
            else:
                seen_names[normalized_name] = index

        sequence_value = _sequence_text(row.get("sequence_number"))
        if sequence_value is None or not _SEQUENCE_PATTERN.fullmatch(sequence_value):
            anomaly_indices.append(index)
            issues.append({
                "code": "INVALID_SEQUENCE_NUMBER",
                "record_indices": [index],
                "message": "Sequence number must contain decimal digits only.",
            })
            continue
        sequence_number = int(sequence_value)
        if sequence_number < 1:
            anomaly_indices.append(index)
            issues.append({
                "code": "INVALID_SEQUENCE_NUMBER",
                "record_indices": [index],
                "message": "Sequence numbers must start at 1 or higher.",
            })
            continue
        parsed_sequences.append((index, sequence_number))
        if sequence_number in seen_sequences:
            duplicate_sequence_indices.extend([seen_sequences[sequence_number], index])
            issues.append({
                "code": "DUPLICATE_SEQUENCE_NUMBER",
                "record_indices": sorted(set([seen_sequences[sequence_number], index])),
                "message": "Sequence number duplicates an earlier record.",
            })
        else:
            seen_sequences[sequence_number] = index

    expected_sequences = set(range(1, announced_count + 1))
    actual_sequences = {sequence for _index, sequence in parsed_sequences}
    missing_sequences = sorted(expected_sequences - actual_sequences)
    unexpected_sequences = sorted(actual_sequences - expected_sequences)
    sequence_coverage = not missing_sequences and not unexpected_sequences and len(parsed_sequences) == announced_count
    if not sequence_coverage:
        issues.append({
            "code": "SEQUENCE_COVERAGE_MISMATCH",
            "record_indices": [index for index, sequence in parsed_sequences if sequence in unexpected_sequences],
            "message": "Sequence numbers do not cover exactly 1 through the announced count.",
            "missing_sequences": missing_sequences,
            "unexpected_sequences": unexpected_sequences,
        })

    zero_blanks = not blank_indices
    zero_duplicates = not duplicate_name_indices and not duplicate_sequence_indices
    zero_anomalies = not anomaly_indices
    checks = {
        "count_match": count_match,
        "zero_blanks": zero_blanks,
        "zero_duplicates": zero_duplicates,
        "zero_anomalies": zero_anomalies,
        "complete_sequence_coverage": sequence_coverage,
    }
    greenlight = all(checks.values())
    return {
        "schema_version": 1,
        "status": "GREENLIGHT" if greenlight else "REJECTED",
        "greenlight_score": 100 if greenlight else 0,
        "provenance": provenance,
        "record_count": record_count,
        "announced_count": announced_count,
        "checks": checks,
        "metrics": {
            "blank_record_count": len(set(blank_indices)),
            "duplicate_name_record_count": len(set(duplicate_name_indices)),
            "duplicate_sequence_record_count": len(set(duplicate_sequence_indices)),
            "anomaly_record_count": len(set(anomaly_indices)),
            "missing_sequence_count": len(missing_sequences),
            "unexpected_sequence_count": len(unexpected_sequences),
        },
        "issues": issues,
        "publication_allowed": greenlight,
        "note": "Validation only. This report does not publish, merge, or deploy data.",
    }


def validate_dataframe(
    frame: pd.DataFrame,
    *,
    announced_count: int,
    name_column: str,
    sequence_column: str,
    provenance: str = "official_direct",
) -> dict[str, Any]:
    """Validate a pandas table without coercing leading-zero sequence strings."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    missing = [column for column in (name_column, sequence_column) if column not in frame.columns]
    if missing:
        raise ValueError("Missing required DataFrame columns: " + ", ".join(missing))
    records = [
        {"name": row[name_column], "sequence_number": row[sequence_column]}
        for row in frame.to_dict(orient="records")
    ]
    return validate_records(records, announced_count=announced_count, provenance=provenance)


def write_validation_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a validation report atomically; the report contains no passer names."""
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination
