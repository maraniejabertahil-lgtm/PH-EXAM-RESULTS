"""Evidence-first gate for official PDF retrieval and third-party fallback.

This module does not fetch URLs or bypass access controls. The acquisition
worker supplies bounded HTTP attempt results; this module records sanitized
evidence and decides whether policy permits a third-party fallback attempt.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_VERSION = 1
_ALLOWED_METHODS = {"HEAD", "GET_RANGE", "GET"}
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:token|api[_-]?key|access[_-]?key|auth|signature|(^|[_-])sig($|[_-])|session|cookie|password|secret)",
    re.IGNORECASE,
)
_HUMAN_VERIFICATION_MARKERS = (
    "captcha",
    "verify you are human",
    "human verification",
    "security verification",
    "checking your browser",
    "turnstile",
)
_AUTHENTICATION_MARKERS = (
    "sign in",
    "log in",
    "login required",
    "authentication required",
    "permission required",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_https_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("URL must be a non-empty string.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only HTTPS URLs without embedded credentials are allowed.")
    safe_query = [
        (key, "[REDACTED]" if _SENSITIVE_QUERY_KEY.search(key) else val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(("https", parsed.netloc, parsed.path, urlencode(safe_query), ""))


def create_attempt_log(
    *, source_id: str, authority: str, exam: str,
    official_source_url: str, official_document_url: str,
) -> dict[str, Any]:
    """Create a machine-readable record before any fallback is considered."""
    if authority not in {"PRC", "CSC"}:
        raise ValueError("Only PRC and CSC official sources are supported.")
    if not source_id.strip() or not exam.strip():
        raise ValueError("source_id and exam are required.")
    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id,
        "authority": authority,
        "exam": exam,
        "official_source_url": _safe_https_url(official_source_url),
        "official_document_url": _safe_https_url(official_document_url),
        "created_at": _utc_now(),
        "provenance": "official_attempt_pending",
        "official_pdf_acquired": False,
        "attempts": [],
    }


def _classify_attempt(
    *, status_code: int, content_type: str, method: str,
    body_prefix: bytes, pdf_signature_valid: bool,
) -> tuple[str, str]:
    body_text = body_prefix[:4096].decode("utf-8", errors="ignore").lower()
    if any(marker in body_text for marker in _HUMAN_VERIFICATION_MARKERS):
        return "human_verification_required", "Official endpoint presented a human-verification barrier; stop automated retrieval."
    if status_code in {401, 407} or any(marker in body_text for marker in _AUTHENTICATION_MARKERS):
        return "authentication_required", "Official endpoint requires authentication; do not attempt to bypass it."
    if status_code == 403:
        return "http_access_denied", "Official endpoint denied the request after this compliant retrieval attempt."
    if status_code == 404:
        return "document_not_found", "Official document URL returned HTTP 404."
    if status_code >= 500:
        return "official_server_error", f"Official endpoint returned HTTP {status_code}."
    if status_code == 200 and method == "GET" and pdf_signature_valid:
        return "official_pdf_verified", "Full HTTP 200 GET returned a verified PDF signature."
    if 200 <= status_code < 300 and pdf_signature_valid:
        return "pdf_signature_seen_partial_or_metadata", "PDF signature observed, but a complete HTTP 200 GET is still required for acquisition."
    if 200 <= status_code < 300 and content_type == "text/html":
        return "html_or_interstitial_not_pdf", "Official URL returned HTML rather than a verified PDF."
    if status_code >= 400:
        return "official_http_error", f"Official endpoint returned HTTP {status_code}."
    return "invalid_or_unverified_pdf", "Response did not provide a verifiable PDF payload."


def record_attempt(
    log: dict[str, Any], *, method: str, status_code: int,
    content_type: str, final_url: str, body_prefix: bytes = b"",
    attempted_at: str | None = None,
) -> dict[str, Any]:
    """Append one bounded HTTP attempt; only a full verified GET counts as acquired."""
    normalized_method = method.upper()
    if normalized_method not in _ALLOWED_METHODS:
        raise ValueError(f"Unsupported retrieval method: {method}")
    if not isinstance(status_code, int) or status_code < 100 or status_code > 599:
        raise ValueError("status_code must be a valid HTTP status code.")
    safe_final_url = _safe_https_url(final_url)
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    signature_valid = b"%PDF-" in body_prefix[:1024]
    outcome, failure_class_or_reason = _classify_attempt(
        status_code=status_code,
        content_type=normalized_type,
        method=normalized_method,
        body_prefix=body_prefix,
        pdf_signature_valid=signature_valid,
    )
    acquired = outcome == "official_pdf_verified" and normalized_method == "GET"
    attempt = {
        "attempted_at": attempted_at or _utc_now(),
        "method": normalized_method,
        "http_status": status_code,
        "content_type": normalized_type,
        "final_url": safe_final_url,
        "pdf_signature_valid": signature_valid,
        "outcome": outcome,
        "failure_class": None if acquired else outcome,
        "failure_reason": None if acquired else failure_class_or_reason,
        "official_pdf_acquired": acquired,
    }
    log.setdefault("attempts", []).append(attempt)
    if acquired:
        log["official_pdf_acquired"] = True
        log["provenance"] = "official_direct"
    elif not log.get("official_pdf_acquired"):
        log["provenance"] = "official_attempts_incomplete"
    return attempt


def write_attempt_log(log: dict[str, Any], output_path: str | Path) -> Path:
    """Persist official-attempt evidence atomically before fallback evaluation."""
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    rendered = json.dumps(log, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(destination)
    return destination


def third_party_fallback_gate(attempt_log_path: str | Path) -> dict[str, Any]:
    """Allow fallback only after a persisted, multi-method official failure record.

    Human-verification barriers require manual review. An authentication barrier
    may authorize only the configured public third-party fallback; it never
    authorizes access-control circumvention.
    """
    path = Path(attempt_log_path).expanduser()
    if not path.is_file():
        return {"allowed": False, "reason": "official_attempt_log_not_persisted"}
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"allowed": False, "reason": "official_attempt_log_unreadable"}
    if not isinstance(log, dict) or log.get("schema_version") != SCHEMA_VERSION:
        return {"allowed": False, "reason": "official_attempt_log_invalid"}
    if log.get("authority") not in {"PRC", "CSC"} or not log.get("source_id"):
        return {"allowed": False, "reason": "official_attempt_identity_missing"}
    if log.get("official_pdf_acquired") is True or log.get("provenance") == "official_direct":
        return {"allowed": False, "reason": "official_pdf_available_use_official_direct"}
    attempts = log.get("attempts")
    if not isinstance(attempts, list) or len(attempts) < 2:
        return {"allowed": False, "reason": "insufficient_official_retrieval_attempts"}
    methods = {item.get("method") for item in attempts if isinstance(item, dict)}
    if "HEAD" not in methods or "GET" not in methods:
        return {"allowed": False, "reason": "official_attempts_lack_head_and_full_get_methods"}
    if any(
        isinstance(item, dict) and item.get("failure_class") == "human_verification_required"
        for item in attempts
    ):
        return {"allowed": False, "reason": "manual_drop_required_access_barrier"}
    if any(isinstance(item, dict) and item.get("official_pdf_acquired") is True for item in attempts):
        return {"allowed": False, "reason": "official_pdf_available_use_official_direct"}
    if any(not isinstance(item, dict) or not item.get("attempted_at") or not item.get("http_status") for item in attempts):
        return {"allowed": False, "reason": "official_attempt_log_incomplete"}
    authentication_barrier = any(
        isinstance(item, dict) and item.get("failure_class") == "authentication_required"
        for item in attempts
    )
    return {
        "allowed": True,
        "reason": (
            "official_authentication_required_public_fallback_allowed"
            if authentication_barrier
            else "official_unavailable_after_logged_head_and_get_attempts"
        ),
        "attempt_count": len(attempts),
        "provenance": "third_party_fallback_pending_validation",
    }
