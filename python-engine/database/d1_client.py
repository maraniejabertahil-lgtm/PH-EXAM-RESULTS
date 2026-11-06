"""Cloudflare D1 REST API client for private operational metadata.

No direct SQL driver is used. Missing D1 configuration disables telemetry without
blocking examination processing or publication.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://api.cloudflare.com/client/v4"
ALLOWED_STATUSES = {"running", "success", "failed", "blocked", "warning"}
ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}
ALLOWED_METADATA_KEYS = {
    "run_id", "run_number", "workflow", "job", "branch", "commit",
    "source_id", "authority", "exam", "duration_ms", "checked_targets",
    "skipped_targets", "records", "greenlight_score",
}

def _config():
    token = os.getenv("CF_D1_API_TOKEN", "").strip()
    account = os.getenv("CF_ACCOUNT_ID", "").strip()
    database = os.getenv("CF_D1_DATABASE_ID", "").strip()
    return (token, account, database) if token and account and database else None

def _metadata(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ALLOWED_METADATA_KEYS if key in value and isinstance(value[key], (str, int, float, bool))}

def execute(sql: str, params=(), *, opener=urlopen, timeout=15):
    config = _config()
    if config is None:
        raise RuntimeError("Cloudflare D1 is not configured.")
    token, account, database = config
    url = f"{API_ROOT}/accounts/{account}/d1/database/{database}/query"
    body = json.dumps({"sql": sql, "params": list(params)}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1024).decode("utf-8", "replace")
        raise RuntimeError(f"Cloudflare D1 API returned HTTP {exc.code}: {detail[:300]}") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cloudflare D1 request failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Cloudflare D1 API reported an unsuccessful query.")
    return payload.get("result", [])

def record_activity(event: dict) -> bool:
    """Insert one idempotent event. Returns False when D1 is not configured."""
    if _config() is None or not isinstance(event, dict):
        return False
    event_id = str(event.get("event_id") or "").strip()[:160]
    execution_id = str(event.get("execution_id") or "").strip()[:160]
    component = str(event.get("component") or "unknown").strip()[:80]
    operation = str(event.get("operation") or "unknown").strip()[:120]
    status = event.get("status", "warning")
    severity = event.get("severity", "info")
    if not event_id or not execution_id or status not in ALLOWED_STATUSES or severity not in ALLOWED_SEVERITIES:
        return False
    occurred_at = str(event.get("occurred_at") or datetime.now(timezone.utc).isoformat())
    duration = event.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        duration = None
    message = str(event.get("message") or operation)[:240]
    error_code = str(event.get("error_code") or "")[:80] or None
    error_message = str(event.get("error_message") or "")[:1000] or None
    source = str(event.get("source") or "system")[:40]
    metadata = json.dumps(_metadata(event.get("metadata")), ensure_ascii=False, separators=(",", ":"))
    sql = """INSERT OR IGNORE INTO monitoring_logs
      (event_id, execution_id, occurred_at, component, operation, status, severity,
       duration_ms, message, error_code, error_message, source, metadata_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    try:
        execute(sql, (event_id, execution_id, occurred_at, component, operation, status, severity,
                      duration, message, error_code, error_message, source, metadata))
        return True
    except Exception as exc:
        print(f"ACTIVITY_LOG_WARNING: {str(exc)[:300]}", file=sys.stderr)
        return False

def apply_schema(schema_path: str | Path | None = None) -> None:
    path = Path(schema_path) if schema_path else Path(__file__).parent / "migrations" / "0001_monitoring.sql"
    for statement in (part.strip() for part in path.read_text(encoding="utf-8").split(";")):
        if statement:
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
