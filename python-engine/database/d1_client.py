"""Cloudflare D1 REST API client for private operational metadata.

No SQL driver is used. D1 is never accessed from the public browser. Missing or
partial credentials disable telemetry safely and never interrupt result processing.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

API_ROOT = "https://api.cloudflare.com/client/v4"
ALLOWED_STATUSES = {"running", "success", "failed", "blocked", "warning"}
ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}
LEGACY_EVENT_TYPES = {
    "processing_started", "greenlight_passed", "greenlight_failed",
    "publication_completed", "publication_failed",
}
LEGACY_STATUSES = {"started", "passed", "failed", "completed"}
ALLOWED_METADATA_KEYS = {
    "run_id", "run_number", "workflow", "job", "branch", "commit",
    "source_id", "authority", "exam", "exam_year", "duration_ms",
    "checked_targets", "skipped_targets", "records", "greenlight_score",
}


class D1Error(RuntimeError):
    """A sanitized Cloudflare D1 REST API error."""


def _config():
    values = (
        os.getenv("CF_ACCOUNT_ID", "").strip(),
        os.getenv("CF_D1_DATABASE_ID", "").strip(),
        os.getenv("CF_D1_API_TOKEN", "").strip(),
    )
    if not any(values):
        return None
    if not all(values):
        raise D1Error("Cloudflare D1 configuration is incomplete.")
    return values


def _metadata(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key] for key in ALLOWED_METADATA_KEYS
        if key in value and isinstance(value[key], (str, int, float, bool))
    }


def _rest_params(values):
    return ["" if value is None else str(value) for value in values]


def _query(account, database, token, sql, params=(), *, opener=urlopen, timeout=15):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
        raise ValueError("A valid bounded SQL statement is required.")
    parameters = _rest_params(params)
    url = f"{API_ROOT}/accounts/{account}/d1/database/{database}/query"
    body = json.dumps({"sql": sql, "params": parameters}, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise D1Error(f"Cloudflare D1 API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D1Error("Cloudflare D1 request failed.") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise D1Error("Cloudflare D1 rejected the query.")
    results = payload.get("result", [])
    if any(isinstance(item, dict) and item.get("success") is False for item in results):
        raise D1Error("Cloudflare D1 reported a failed SQL statement.")
    return results


def execute(sql: str, params=(), *, opener=urlopen, timeout=15):
    config = _config()
    if config is None:
        raise D1Error("Cloudflare D1 is not configured.")
    return _query(*config, sql, params, opener=opener, timeout=timeout)


def _legacy_event_type(component, operation, status):
    operation = str(operation).lower()
    if "greenlight" in operation:
        return "greenlight_failed" if status in {"failed", "blocked"} else "greenlight_passed"
    if status == "running":
        return "processing_started"
    if status == "failed":
        return "publication_failed"
    if status == "blocked":
        return "greenlight_failed"
    return "publication_completed"


def _legacy_status(status):
    return {
        "running": "started",
        "success": "completed",
        "failed": "failed",
        "blocked": "failed",
        "warning": "completed",
    }[status]


def record_activity(event: dict) -> bool:
    """Insert one idempotent event; telemetry failure never breaks the main pipeline."""
    if not isinstance(event, dict):
        return False
    try:
        config = _config()
    except D1Error as exc:
        print(f"ACTIVITY_LOG_WARNING: {exc}", file=sys.stderr)
        return False
    if config is None:
        return False

    event_id = str(event.get("event_id") or "").strip()[:160]
    execution_id = str(event.get("execution_id") or "").strip()[:160]
    component = str(event.get("component") or "unknown").strip()[:80]
    operation = str(event.get("operation") or "unknown").strip()[:120]
    status = event.get("status", "warning")
    severity = event.get("severity", "info")
    if not event_id or not execution_id or status not in ALLOWED_STATUSES or severity not in ALLOWED_SEVERITIES:
        return False

    metadata = _metadata(event.get("metadata"))
    occurred_at = str(event.get("occurred_at") or datetime.now(timezone.utc).isoformat())
    duration = event.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        duration = None
    message = str(event.get("message") or operation)[:240]
    error_code = str(event.get("error_code") or "")[:80]
    if status == "blocked" and not error_code:
        error_code = "BLOCKED"
    if status in {"blocked", "warning"} and severity == "info":
        severity = "warning"
    error_message = str(event.get("error_message") or "")[:1000]
    source = str(event.get("source") or "system")[:40]
    event_type = event.get("event_type")
    if event_type not in LEGACY_EVENT_TYPES:
        event_type = _legacy_event_type(component, operation, status)
    stored_status = _legacy_status(status)
    metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    sql = """INSERT OR IGNORE INTO monitoring_logs
      (id, event_id, event_type, status, summary, authority, exam, exam_year,
       source_id, correlation_id, created_at, execution_id, occurred_at, component,
       operation, severity, duration_ms, message, error_code, error_message, source, metadata_json)
      VALUES (?, ?, ?, ?, ?, NULLIF(?, ''), NULLIF(?, ''), NULLIF(?, ''),
       NULLIF(?, ''), ?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''), ?, NULLIF(?, ''),
       NULLIF(?, ''), ?, ?)"""
    try:
        _query(*config, sql, (
            event_id, event_id, event_type, stored_status, message,
            metadata.get("authority"), metadata.get("exam"), metadata.get("exam_year"),
            metadata.get("source_id"), execution_id, occurred_at, execution_id,
            occurred_at, component, operation, severity, duration, message,
            error_code, error_message, source, metadata_json,
        ))
        return True
    except Exception as exc:
        print(f"ACTIVITY_LOG_WARNING: {str(exc)[:240]}", file=sys.stderr)
        return False


class D1Client:
    """Small compatibility facade for the private metadata foundation."""

    def __init__(self, account_id: str, database_id: str, api_token: str, *, opener=None):
        if not all(isinstance(value, str) and value.strip() for value in (account_id, database_id, api_token)):
            raise ValueError("Cloudflare D1 configuration is incomplete.")
        self._account_id = account_id.strip()
        self._database_id = database_id.strip()
        self._api_token = api_token.strip()
        self._opener = opener or urlopen

    @classmethod
    def from_env(cls):
        config = _config()
        return None if config is None else cls(*config)

    def query(self, sql: str, params=()):
        results = _query(self._account_id, self._database_id, self._api_token, sql, params, opener=self._opener)
        if not results or not isinstance(results[0], dict):
            return []
        rows = results[0].get("results", [])
        return rows if isinstance(rows, list) else []

    def record_event(self, *, event_type: str, status: str, summary: str,
                     authority: str | None = None, exam: str | None = None,
                     exam_year: int | None = None, source_id: str | None = None,
                     correlation_id: str | None = None) -> str:
        if event_type not in LEGACY_EVENT_TYPES or status not in LEGACY_STATUSES:
            raise ValueError("Unsupported operational event type or status.")
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query(
            "INSERT INTO monitoring_logs (id,event_type,status,summary,authority,exam,exam_year,source_id,correlation_id,created_at) "
            "VALUES(?,?,?,?,NULLIF(?,''),NULLIF(?,''),NULLIF(?,''),NULLIF(?,''),?,?)",
            [event_id,event_type,status," ".join(str(summary).split())[:240],
             authority,exam,exam_year,source_id,correlation_id or event_id,created_at],
        )
        return event_id

    def upsert_import_batch(self, *, batch_id: str, authority: str, exam: str, exam_year: int,
                            status: str, greenlight_score: int | None = None,
                            announced_count: int | None = None, extracted_count: int | None = None,
                            source_id: str | None = None, summary: str = "") -> None:
        allowed = {"processing", "greenlight_passed", "greenlight_failed", "published", "failed"}
        if status not in allowed:
            raise ValueError("Unsupported import batch status.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query(
            "INSERT INTO import_batches (batch_id,authority,exam,exam_year,source_id,status,greenlight_score,announced_count,extracted_count,summary,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,NULLIF(?,''),NULLIF(?,''),NULLIF(?,''),?,?,?) "
            "ON CONFLICT(batch_id) DO UPDATE SET status=excluded.status, greenlight_score=excluded.greenlight_score, "
            "announced_count=excluded.announced_count, extracted_count=excluded.extracted_count, summary=excluded.summary, updated_at=excluded.updated_at",
            [batch_id,authority,exam,exam_year,source_id,status,greenlight_score,announced_count,extracted_count,
             " ".join(str(summary).split())[:240],now,now],
        )

    def upsert_release_prediction(self, *, prediction_id: str, authority: str, exam: str,
                                  exam_year: int, predicted_release_date: str, method: str,
                                  confidence: float | None = None, evidence_count: int = 0,
                                  source: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query(
            "INSERT INTO release_predictions (id,prediction_id,authority,exam,exam_year,predicted_release_date,method,confidence,evidence_count,source,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?, 'active', ?, ?) "
            "ON CONFLICT(prediction_id) DO UPDATE SET predicted_release_date=excluded.predicted_release_date, method=excluded.method, "
            "confidence=excluded.confidence, evidence_count=excluded.evidence_count, source=excluded.source, status='active', updated_at=excluded.updated_at",
            [prediction_id,prediction_id,authority,exam,exam_year,predicted_release_date,method,confidence,evidence_count,source,now,now],
        )


COLUMN_DEFINITIONS = {
    "monitoring_logs": {
        "id": "TEXT", "event_id": "TEXT", "event_type": "TEXT", "summary": "TEXT NOT NULL DEFAULT ''",
        "authority": "TEXT", "exam": "TEXT", "exam_year": "INTEGER", "source_id": "TEXT",
        "correlation_id": "TEXT", "created_at": "TEXT", "execution_id": "TEXT", "occurred_at": "TEXT",
        "component": "TEXT", "operation": "TEXT", "severity": "TEXT NOT NULL DEFAULT 'info'",
        "duration_ms": "INTEGER", "message": "TEXT", "error_code": "TEXT",
        "error_message": "TEXT", "source": "TEXT", "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "import_batches": {
        "source_id": "TEXT", "extracted_count": "INTEGER", "summary": "TEXT NOT NULL DEFAULT ''",
        "record_count": "INTEGER", "provenance": "TEXT", "started_at": "TEXT", "completed_at": "TEXT",
        "updated_at": "TEXT",
    },
    "release_predictions": {
        "id": "TEXT", "prediction_id": "TEXT", "exam_year": "INTEGER", "method": "TEXT",
        "confidence": "REAL", "evidence_count": "INTEGER NOT NULL DEFAULT 0",
        "source": "TEXT", "status": "TEXT NOT NULL DEFAULT 'active'", "updated_at": "TEXT",
    },
}


def apply_schema(schema_path: str | Path | None = None) -> None:
    path = Path(schema_path) if schema_path else Path(__file__).parent / "migrations" / "0001_monitoring.sql"
    statements = [part.strip() for part in path.read_text(encoding="utf-8").split(";") if part.strip()]
    indexes = [statement for statement in statements if statement.upper().startswith("CREATE INDEX") or statement.upper().startswith("CREATE UNIQUE INDEX")]
    tables = [statement for statement in statements if statement not in indexes]
    for statement in tables:
        execute(statement)
    for table, definitions in COLUMN_DEFINITIONS.items():
        result = execute(f"PRAGMA table_info({table})")
        rows = result[0].get("results", []) if result and isinstance(result[0], dict) else []
        existing = {row.get("name") for row in rows if isinstance(row, dict)}
        for column, definition in definitions.items():
            if column not in existing:
                execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    for statement in indexes:
        execute(statement)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage PH-EXAM-RESULTS D1 operational metadata.")
    parser.add_argument("command", choices=("migrate",))
    parser.add_argument("--schema")
    args = parser.parse_args()
    apply_schema(args.schema)
    print("D1 monitoring schema applied.")


if __name__ == "__main__":
    main()
