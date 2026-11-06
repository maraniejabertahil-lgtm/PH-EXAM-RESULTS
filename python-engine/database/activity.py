"""Best-effort operational activity recording; never blocks Greenlight or publication."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from database.d1_client import D1Client, D1Error


def _metadata_client() -> D1Client | None:
    try:
        return D1Client.from_env()
    except (D1Error, ValueError):
        print("OPERATIONAL METADATA WARNING: D1 configuration unavailable.", file=sys.stderr)
        return None


def _identity(batch: dict[str, Any]) -> dict[str, Any]:
    def short(value: Any) -> str | None:
        return value.strip()[:80] if isinstance(value, str) and value.strip() else None
    year = batch.get("year")
    return {
        "authority": short(batch.get("authority")),
        "exam": short(batch.get("exam")),
        "exam_year": year if isinstance(year, int) and not isinstance(year, bool) else None,
        "source_id": short(batch.get("source_id")),
    }


def record_pipeline_event(batch: dict[str, Any], *, event_type: str, status: str, summary: str,
                          batch_status: str | None = None, report: dict[str, Any] | None = None,
                          correlation_id: str | None = None, batch_bytes: bytes = b"") -> None:
    client = _metadata_client()
    if client is None:
        return
    identity = _identity(batch)
    batch_id = hashlib.sha256(batch_bytes).hexdigest() if batch_bytes else None
    try:
        client.record_event(event_type=event_type, status=status, summary=summary,
                            authority=identity["authority"], exam=identity["exam"],
                            exam_year=identity["exam_year"], source_id=identity["source_id"],
                            correlation_id=correlation_id or batch_id)
        if batch_status and batch_id and identity["authority"] and identity["exam"] and identity["exam_year"]:
            report = report if isinstance(report, dict) else {}
            announced = batch.get("announced_count")
            extracted = report.get("record_count")
            score = report.get("greenlight_score")
            client.upsert_import_batch(
                batch_id=batch_id, authority=identity["authority"], exam=identity["exam"],
                exam_year=identity["exam_year"], source_id=identity["source_id"], status=batch_status,
                greenlight_score=score if isinstance(score, int) else None,
                announced_count=announced if isinstance(announced, int) else None,
                extracted_count=extracted if isinstance(extracted, int) else None,
                summary=summary,
            )
    except (D1Error, ValueError, TypeError):
        print("OPERATIONAL METADATA WARNING: D1 write failed; processing continues.", file=sys.stderr)


def read_validation_report(root: Path) -> dict[str, Any]:
    path = root / "python-engine" / "artifacts" / "validation-report.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
