import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


class D1Error(Exception):
    """Raised when the Cloudflare D1 REST API fails."""


class D1Client:
    def __init__(self, account_id: str, database_id: str, api_token: str):
        self.account_id = account_id
        self.database_id = database_id
        self.api_token = api_token
        self.endpoint = (
            "https://api.cloudflare.com/client/v4/accounts/"
            + account_id
            + "/d1/database/"
            + database_id
            + "/query"
        )

    @classmethod
    def from_environment(cls):
        token = os.getenv("CF_API_TOKEN")
        account_id = os.getenv("CF_ACCOUNT_ID")
        database_id = os.getenv("D1_DATABASE_ID")
        if not token or not account_id or not database_id:
            raise D1Error(
                "D1 is not configured. Set CF_API_TOKEN, CF_ACCOUNT_ID, and D1_DATABASE_ID."
            )
        return cls(account_id, database_id, token)

    def query(self, sql: str, params: list | None = None) -> list:
        payload = json.dumps({"sql": sql, "params": params or []}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": "Bearer " + self.api_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise D1Error(f"D1 request failed: {exc}") from exc

        if not result.get("success"):
            errors = result.get("errors") or []
            message = "; ".join(str(item.get("message", "D1 API error")) for item in errors)
            raise D1Error(message or "D1 API returned an unsuccessful response.")

        payload_result = result.get("result") or []
        if not payload_result:
            return []
        first = payload_result[0]
        if not first.get("success", True):
            raise D1Error("D1 query execution failed.")
        return first.get("results") or []

    def apply_schema(self, schema_path: str | Path):
        schema = Path(schema_path).read_text(encoding="utf-8")
        statements = [part.strip() for part in schema.split(";") if part.strip()]
        for statement in statements:
            self.query(statement)

    def get_source_state(self, source_id: str):
        rows = self.query(
            "SELECT source_id, etag, last_modified, content_length, checked_at "
            "FROM source_states WHERE source_id = ?",
            [source_id],
        )
        return rows[0] if rows else None

    def save_source_state(self, source_id: str, etag: str | None, last_modified: str | None, content_length: str | None, checked_at: str):
        self.query(
            "INSERT INTO source_states (source_id, etag, last_modified, content_length, checked_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id) DO UPDATE SET "
            "etag = excluded.etag, last_modified = excluded.last_modified, "
            "content_length = excluded.content_length, checked_at = excluded.checked_at",
            [source_id, etag, last_modified, content_length, checked_at],
        )



    def get_release_prediction(self, authority: str, exam: str, year: int):
        rows = self.query(
            "SELECT predicted_date, actual_date, data_points FROM release_predictions "
            "WHERE authority = ? AND exam = ? AND year = ?",
            [authority.upper(), exam, int(year)],
        )
        return rows[0] if rows else None

    def get_actual_release_dates(self, authority: str, exam: str, limit: int = 6) -> list[str]:
        rows = self.query(
            "SELECT actual_date FROM release_predictions "
            "WHERE authority = ? AND exam = ? AND actual_date IS NOT NULL "
            "ORDER BY actual_date DESC LIMIT ?",
            [authority.upper(), exam, int(limit)],
        )
        return [str(row["actual_date"]) for row in rows if row.get("actual_date")]

    def save_release_prediction(
        self,
        authority: str,
        exam: str,
        year: int,
        predicted_date: str,
        data_points: int,
    ):
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.query(
            "INSERT INTO release_predictions "
            "(authority, exam, year, predicted_date, actual_date, data_points, updated_at) "
            "VALUES (?, ?, ?, ?, NULL, ?, ?) "
            "ON CONFLICT(authority, exam, year) DO UPDATE SET "
            "predicted_date = excluded.predicted_date, "
            "data_points = excluded.data_points, updated_at = excluded.updated_at",
            [authority.upper(), exam, int(year), predicted_date, int(data_points), timestamp],
        )


    def record_import_batch(self, report: dict, source_reference: str = "") -> str:
        batch_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        validation = report.get("validation", {})
        duplicates = report.get("duplicates", {})
        self.query(
            "INSERT INTO import_batches "
            "(batch_id, authority, exam, year, total_records, valid_records, "
            "invalid_records, exact_duplicates, fuzzy_candidates, status, "
            "created_at, source_reference, report_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                batch_id,
                report.get("authority"),
                report.get("examination"),
                int(report.get("year")),
                int(validation.get("total_records", 0)),
                int(validation.get("valid_records", 0)),
                len(validation.get("invalid_records", [])),
                len(duplicates.get("exact_duplicates", [])),
                len(duplicates.get("fuzzy_candidates", [])),
                "validation_passed" if validation.get("is_valid") else "validation_failed",
                timestamp,
                source_reference or None,
                report.get("source_file"),
            ],
        )
        return batch_id

    def record_actual_release_date(self, authority: str, exam: str, year: int, actual_date: str):
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.query(
            "INSERT INTO release_predictions "
            "(authority, exam, year, predicted_date, actual_date, data_points, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, 0, ?) "
            "ON CONFLICT(authority, exam, year) DO UPDATE SET "
            "actual_date = excluded.actual_date, updated_at = excluded.updated_at",
            [authority.upper(), exam, int(year), actual_date, timestamp],
        )


    def update_import_batch_status(self, batch_id: str, status: str):
        self.query(
            "UPDATE import_batches SET status = ? WHERE batch_id = ?",
            [status, batch_id],
        )


    def get_storage_stats(self) -> dict:
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            + self.account_id
            + "/d1/database/"
            + self.database_id
            + "?fields=file_size,name,version"
        )
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer " + self.api_token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise D1Error(f"Could not retrieve D1 database details: {exc}") from exc
        if not payload.get("success"):
            errors = payload.get("errors") or []
            message = "; ".join(str(item.get("message", "D1 API error")) for item in errors)
            raise D1Error(message or "D1 database details request failed.")
        result = payload.get("result") or {}
        if result.get("file_size") is None:
            raise D1Error("Cloudflare did not return the D1 file_size field.")
        return {
            "estimated_storage_bytes": int(result["file_size"]),
            "database_name": result.get("name"),
            "database_version": result.get("version"),
        }

    def record_monitoring_log(self, source_id: str, status: str, timestamp: str, error: str | None = None, etag: str | None = None, last_modified: str | None = None):
        self.query(
            "INSERT INTO monitoring_logs "
            "(id, source_id, status, run_timestamp, error_details, etag, last_modified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [str(uuid4()), source_id, status, timestamp, error, etag, last_modified],
        )
