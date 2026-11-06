"""Best-effort operational activity recording; never blocks Greenlight or publication."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from database.d1_client import D1Client, D1Error, record_activity

EVENT_TYPES = {
    "processing_started", "greenlight_passed", "greenlight_failed",
    "publication_completed", "publication_failed", "watcher_scan", "release_detected",
}
STATUS_MAP = {"started": "running", "passed": "success", "completed": "success", "failed": "failed"}


def _metadata_client() -> D1Client | None:
    try:
        return D1Client.from_env()
    except (D1Error, ValueError):
        print("OPERATIONAL METADATA WARNING: D1 configuration unavailable.", file=sys.stderr)
        return None


def _short(value: Any, limit: int = 80) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _identity(batch: dict[str, Any]) -> dict[str, Any]:
    year = batch.get("year", batch.get("exam_year"))
    return {
        "authority": _short(batch.get("authority")),
        "exam": _short(batch.get("exam")),
        "exam_year": year if isinstance(year, int) and not isinstance(year, bool) else None,
        "source_id": _short(batch.get("source_id")),
    }


def _safe_error(value: str | None) -> str:
    text = " ".join(str(value or "").split())[:1000]
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", text, flags=re.I)
    return text


def record_pipeline_event(
    batch: dict[str, Any], *, event_type: str, status: str, summary: str,
    operation: str, batch_status: str | None = None, report: dict[str, Any] | None = None,
    correlation_id: str | None = None, batch_bytes: bytes = b"",
    duration_ms: int | None = None, error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    if event_type not in EVENT_TYPES or status not in STATUS_MAP:
        return
    client = _metadata_client()
    if client is None:
        return
    identity = _identity(batch)
    batch_id = hashlib.sha256(batch_bytes).hexdigest() if batch_bytes else None
    execution_id = correlation_id or batch_id or "python-unidentified"
    report = report if isinstance(report, dict) else {}
    announced = batch.get("announced_count")
    extracted = report.get("record_count", report.get("extracted_count"))
    score = report.get("greenlight_score")
    metadata = {
        **identity,
        "announced_count": announced if isinstance(announced, int) and not isinstance(announced, bool) else None,
        "extracted_count": extracted if isinstance(extracted, int) and not isinstance(extracted, bool) else None,
        "greenlight_score": score if isinstance(score, int) and not isinstance(score, bool) else None,
    }
    event_id = f"{execution_id}:{operation}:{event_type}:{status}"[:160]
    display_status = STATUS_MAP[status]
    severity = "error" if status == "failed" else "info"
    try:
        record_activity({
            "event_id": event_id,
            "execution_id": execution_id,
            "component": "Python Engine",
            "operation": operation,
            "event_type": event_type,
            "status": display_status,
            "severity": severity,
            "duration_ms": duration_ms,
            "message": " ".join(str(summary).split())[:240],
            "error_code": str(error_code or "")[:80],
            "error_message": _safe_error(error_message),
            "source": "python_engine",
            "metadata": metadata,
        })
        if batch_status and batch_id and identity["authority"] and identity["exam"] and identity["exam_year"]:
            client.upsert_import_batch(
                batch_id=batch_id,
                authority=identity["authority"],
                exam=identity["exam"],
                exam_year=identity["exam_year"],
                source_id=identity["source_id"],
                status=batch_status,
                greenlight_score=metadata["greenlight_score"],
                announced_count=metadata["announced_count"],
                extracted_count=metadata["extracted_count"],
                summary=" ".join(str(summary).split())[:240],
            )
    except (D1Error, ValueError, TypeError):
        print("OPERATIONAL METADATA WARNING: D1 write failed; processing continues.", file=sys.stderr)


def read_batch_for_activity(batch_path: str | Path, root: Path) -> tuple[dict[str, Any], bytes]:
    path = Path(batch_path)
    candidate = path if path.is_absolute() else root / path
    try:
        raw = candidate.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        return (value if isinstance(value, dict) else {}), raw
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, b""


def read_validation_report(root: Path) -> dict[str, Any]:
    candidates = [
        root / "python-engine" / "artifacts" / "validation-report.json",
        root / "artifacts" / "validation-report.json",
    ]
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return {}
