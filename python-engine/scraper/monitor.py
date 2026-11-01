import json
import re
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
    if parsed.username or parsed.password:
        raise ValueError("Source URLs must not embed usernames or passwords.")
    return parsed.hostname.lower(), url


def _response_content_length(response) -> str | None:
    content_range = response.headers.get("Content-Range", "")
    if getattr(response, "status", None) == 206:
        if "/" in content_range:
            total = content_range.rsplit("/", 1)[-1].strip()
            if total.isdigit():
                return total
        # Content-Length on a 206 response describes only the returned range,
        # not the complete source document.
        return None
    return response.headers.get("Content-Length")


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
        if exc.code in (405, 501):
            try:
                request = Request(
                    url,
                    headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
                    method="GET",
                )
                with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    final_url = urlsplit(response.geturl())
                    final_host = (final_url.hostname or "").lower()
                    if final_url.scheme != "https" or final_host != original_host:
                        return {"source_id": source_id, "status": "redirect_rejected", "checked_at": checked_at}
                    response.read(1)
                    return {
                        "source_id": source_id,
                        "status": "reachable",
                        "http_status": response.status,
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "content_length": _response_content_length(response),
                        "checked_at": checked_at,
                    }
            except HTTPError as get_error:
                exc = get_error
            except (URLError, TimeoutError, OSError) as get_error:
                return {
                    "source_id": source_id,
                    "status": "unreachable",
                    "error": str(get_error)[:300],
                    "checked_at": checked_at,
                }
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

    sources = registry["sources"]
    seen_ids = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"Source entry {index} must be an object.")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", source_id):
            raise ValueError(
                f"Source entry {index} requires a unique ID using letters, numbers, hyphens, or underscores."
            )
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source id: {source_id}")
        seen_ids.add(source_id)
        if source.get("authority") not in {"PRC", "CSC"}:
            raise ValueError(f"Source {source_id} must specify PRC or CSC authority.")
        if not isinstance(source.get("exam"), str) or not source["exam"].strip():
            raise ValueError(f"Source {source_id} requires an examination identifier.")
        if source.get("source_type") not in {"official", "verified_third_party"}:
            raise ValueError(f"Source {source_id} has an unsupported source_type.")
        if not isinstance(source.get("enabled"), bool):
            raise ValueError(f"Source {source_id} requires an enabled boolean.")
        _validate_https_url(source.get("url", ""))
    return sources


def monitor_registry(path: str | Path) -> dict:
    sources = load_registry(path)
    scopes = {}
    for source in sources:
        scope = (source.get("authority"), source.get("exam"))
        scopes.setdefault(scope, []).append(source)

    results = []
    for scope_sources in scopes.values():
        official = [item for item in scope_sources if item.get("source_type") == "official"]
        third_party = [
            item for item in scope_sources
            if item.get("source_type") == "verified_third_party"
        ]
        official_results = [monitor_source(item) for item in official]
        results.extend(official_results)

        official_available = any(
            item.get("status") in {"reachable", "baseline_created", "changed"}
            for item in official_results
        )
        if official_available:
            results.extend({
                "source_id": str(item.get("id", "unknown")),
                "status": "skipped_official_available",
                "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            } for item in third_party)
        elif official:
            results.extend(monitor_source(item) for item in third_party)
        else:
            results.extend({
                "source_id": str(item.get("id", "unknown")),
                "status": "skipped_no_official_source_configured",
                "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            } for item in third_party)

    return {
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_count": len(sources),
        "results": results,
        "changes_detected": False,
        "notice": (
            "Official sources are checked first. Verified third-party sources are "
            "checked only when configured official sources for the same authority "
            "and examination are unavailable. Monitoring checks HTTP metadata only."
        ),
    }
