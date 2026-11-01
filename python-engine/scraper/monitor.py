import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


USER_AGENT = "PH-EXAM-RESULTS-SourceMonitor/1.0"
TIMEOUT_SECONDS = 15


def _is_approved_source(source: dict) -> tuple[bool, str]:
    kind = source.get("source_type")
    if kind == "official" and source.get("authorized") is True:
        return True, ""
    if kind == "verified_third_party" and source.get("verified_by_owner") is True:
        return True, ""
    return False, "Source is not explicitly authorized or owner-verified."


def _validate_https_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url or "")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only valid HTTPS source URLs are allowed.")
    return parsed.hostname.lower(), url


def monitor_source(source: dict) -> dict:
    source_id = str(source.get("id", "unknown"))
    approved, reason = _is_approved_source(source)
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not approved:
        return {"source_id": source_id, "status": "rejected", "reason": reason, "checked_at": checked_at}
    if source.get("enabled") is not True:
        return {"source_id": source_id, "status": "disabled", "checked_at": checked_at}

    try:
        original_host, url = _validate_https_url(source.get("url", ""))
        request = Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            final_host = (urlsplit(response.geturl()).hostname or "").lower()
            if urlsplit(response.geturl()).scheme != "https" or final_host != original_host:
                return {
                    "source_id": source_id,
                    "status": "redirect_rejected",
                    "checked_at": checked_at,
                }
            return {
                "source_id": source_id,
                "status": "reachable",
                "http_status": response.status,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_length": response.headers.get("Content-Length"),
                "checked_at": checked_at,
            }
    except HTTPError as exc:
        status = "blocked" if exc.code in (401, 403, 429) else "http_error"
        return {
            "source_id": source_id,
            "status": status,
            "http_status": exc.code,
            "checked_at": checked_at,
        }
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        return {
            "source_id": source_id,
            "status": "unreachable",
            "error": str(exc)[:300],
            "checked_at": checked_at,
        }


def load_registry(path: str | Path) -> list[dict]:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise ValueError("Source registry must contain a sources array.")
    return registry["sources"]


def monitor_registry(path: str | Path) -> dict:
    sources = load_registry(path)
    results = [monitor_source(source) for source in sources]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_count": len(sources),
        "results": results,
        "changes_detected": False,
        "notice": (
            "This monitor checks source reachability and HTTP metadata only. "
            "A changed source requires authorized acquisition and review."
        ),
    }
