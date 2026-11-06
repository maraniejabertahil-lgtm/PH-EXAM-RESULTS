"""Minimal Cloudflare D1 REST API client for private operational metadata.

No SQL driver is used. Credentials are read only from process environment and
are never included in exceptions or log output.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any


class D1Error(RuntimeError):
    """Raised when the Cloudflare D1 REST API cannot complete a query."""


class D1Client:
    def __init__(self, account_id: str, database_id: str, api_token: str, *, opener=None):
        if not all(isinstance(v, str) and v.strip() for v in (account_id, database_id, api_token)):
            raise ValueError("Cloudflare D1 configuration is incomplete.")
        self._account_id = account_id.strip()
        self._database_id = database_id.strip()
        self._api_token = api_token.strip()
        self._opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "D1Client | None":
        values = (os.getenv("CF_ACCOUNT_ID"), os.getenv("CF_D1_DATABASE_ID"), os.getenv("CF_D1_API_TOKEN"))
        if not any(values):
            return None
        if not all(values):
            raise D1Error("Cloudflare D1 configuration is incomplete.")
        return cls(*values)

    def query(self, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
            raise ValueError("A valid bounded SQL statement is required.")
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self._account_id}/d1/database/{self._database_id}/query"
        )
        payload = json.dumps({"sql": sql, "params": list(params)}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise D1Error("Cloudflare D1 request failed.") from exc
        if not isinstance(body, dict) or body.get("success") is not True:
            raise D1Error("Cloudflare D1 rejected the query.")
        result = body.get("result")
        if not isinstance(result, list) or not result or not isinstance(result[0], dict):
            return []
        rows = result[0].get("results", [])
        return rows if isinstance(rows, list) else []

    def record_event(
        self, *, event_type: str, status: str, summary: str,
        authority: str | None = None, exam: str | None = None,
        exam_year: int | None = None, source_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        allowed_events = {"watcher_scan", "release_detected", "processing_started", "greenlight_passed", "greenlight_failed", "publication_completed", "publication_failed"}
        allowed_status = {"started", "passed", "failed", "completed"}
        if event_type not in allowed_events or status not in allowed_status:
            raise ValueError("Unsupported operational event type or status.")
        safe_summary = " ".join(str(summary).split())[:240]
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query(
            "INSERT INTO monitoring_logs "
            "(id,event_type,status,summary,authority,exam,exam_year,source_id,correlation_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            [event_id,event_type,status,safe_summary,authority,exam,exam_year,source_id,correlation_id,created_at],
        )
        return event_id

    def upsert_import_batch(
        self, *, batch_id: str, authority: str, exam: str, exam_year: int,
        status: str, greenlight_score: int | None = None,
        announced_count: int | None = None, extracted_count: int | None = None,
        source_id: str | None = None, summary: str = "",
    ) -> None:
        if status not in {"processing", "greenlight_passed", "greenlight_failed", "published", "failed"}:
            raise ValueError("Unsupported import batch status.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.query(
            "INSERT INTO import_batches "
            "(batch_id,authority,exam,exam_year,source_id,status,greenlight_score,announced_count,extracted_count,summary,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(batch_id) DO UPDATE SET status=excluded.status, "
            "greenlight_score=excluded.greenlight_score, announced_count=excluded.announced_count, "
            "extracted_count=excluded.extracted_count, summary=excluded.summary, updated_at=excluded.updated_at",
            [batch_id,authority,exam,exam_year,source_id,status,greenlight_score,announced_count,extracted_count," ".join(str(summary).split())[:240],now,now],
        )
