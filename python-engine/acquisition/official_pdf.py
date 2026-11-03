"""Single-document, same-origin official PDF acquisition with fail-closed checks."""
from __future__ import annotations

import hashlib
import os
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from acquisition.official_first_policy import create_attempt_log, record_attempt, write_attempt_log

USER_AGENT = "PH-EXAM-RESULTS-PythonAcquirer/1.0"
MAX_BYTES = 50 * 1024 * 1024


class AcquisitionError(RuntimeError):
    pass


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def _url(value, label):
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AcquisitionError(f"{label} must be a credential-free HTTPS URL.")
    return parsed


def _origin(value):
    p = _url(value, "URL")
    return p.scheme, p.hostname.lower(), p.port or 443


def _request(url, method, timeout, limit):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,application/octet-stream"}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            data = b"" if method == "HEAD" else response.read(limit + 1)
            return response.status, response.headers, response.geturl(), data
    except HTTPError as exc:
        return exc.code, exc.headers, exc.geturl(), exc.read(4096) if method != "HEAD" else b""
    except (URLError, TimeoutError, OSError) as exc:
        raise AcquisitionError(f"Official {method} request failed: {exc}") from exc


def _robots_allowed(robots_url, target_url, timeout):
    status, headers, final_url, body = _request(robots_url, "GET", timeout, 1024 * 1024)
    if status == 404:
        lines = []
    elif status != 200:
        raise AcquisitionError(f"Unable to verify robots.txt policy (HTTP {status}).")
    else:
        lines = body.decode("utf-8", errors="replace").splitlines()
    if _origin(final_url) != _origin(robots_url):
        raise AcquisitionError("robots.txt redirected outside the approved origin.")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(lines)
    return parser.can_fetch(USER_AGENT, target_url)


def acquire_official_pdf(*, source, article_url, document_url, output_path, attempt_log_path, timeout=20):
    if not isinstance(source, dict) or source.get("source_type") != "official" or source.get("authorized") is not True or source.get("enabled") is not True:
        raise AcquisitionError("Source is not enabled and owner-authorized.")
    if _origin(article_url) != _origin(source.get("url", "")):
        raise AcquisitionError("Official article is outside the approved source origin.")

    log = create_attempt_log(
        source_id=source["id"], authority=source["authority"], exam=source["exam"],
        official_source_url=source["url"], official_document_url=document_url,
    )
    log["official_article_url"] = article_url
    log["retrieval_user_agent"] = USER_AGENT

    if _origin(document_url) != _origin(source.get("url", "")):
        log["attempts"].append({
            "attempted_at": log["created_at"], "method": "LINK_POLICY",
            "http_status": None, "content_type": None, "final_url": document_url,
            "pdf_signature_valid": False, "outcome": "manual_drop_required_external_host",
            "failure_class": "external_document_access_policy_unverified",
            "failure_reason": "The official article links to an external host whose public-download and robots policy is not verified; no sign-in or access-control bypass was attempted.",
            "official_pdf_acquired": False,
        })
        write_attempt_log(log, attempt_log_path)
        raise AcquisitionError("Official document uses an external host; use manual drop until that host's public-download policy is verified.")
    if source.get("robots_policy_verified") is not True or not source.get("robots_policy_url"):
        write_attempt_log(log, attempt_log_path)
        raise AcquisitionError("A verified robots.txt policy URL is required.")
    try:
        if not _robots_allowed(source["robots_policy_url"], article_url, timeout):
            raise AcquisitionError("robots.txt disallows the official article.")
        if not _robots_allowed(source["robots_policy_url"], document_url, timeout):
            raise AcquisitionError("robots.txt disallows the official PDF.")
        status, headers, final_url, html = _request(article_url, "GET", timeout, 2 * 1024 * 1024)
        if status != 200 or "text/html" not in (headers.get("Content-Type") or "").lower():
            raise AcquisitionError(f"Official article retrieval failed (HTTP {status}).")
        if _origin(final_url) != _origin(source["url"]):
            raise AcquisitionError("Official article redirected outside the approved origin.")
        links = _AnchorParser()
        links.feed(html.decode("utf-8", errors="replace"))
        if document_url not in {urljoin(final_url, href) for href in links.hrefs}:
            raise AcquisitionError("PDF URL is not linked from the supplied official article.")
        head_status, head_headers, head_final, head_body = _request(document_url, "HEAD", timeout, 1024)
        record_attempt(log, method="HEAD", status_code=head_status, content_type=head_headers.get("Content-Type", ""), final_url=head_final, body_prefix=head_body[:1024])
        write_attempt_log(log, attempt_log_path)
        if head_status in {401, 407}:
            raise AcquisitionError("Official PDF requires authentication; use manual review.")
        get_status, get_headers, get_final, data = _request(document_url, "GET", timeout, MAX_BYTES)
        content_type = (get_headers.get("Content-Type") or "").split(";", 1)[0].lower()
        verified = (
            get_status == 200
            and content_type in {"application/pdf", "application/octet-stream"}
            and b"%PDF-" in data[:1024]
            and len(data) <= MAX_BYTES
            and _origin(get_final) == _origin(source["url"])
        )
        record_attempt(log, method="GET", status_code=get_status, content_type=content_type, final_url=get_final, body_prefix=data[:1024])
        if not verified:
            attempt = log["attempts"][-1]
            attempt["official_pdf_acquired"] = False
            if log.get("official_pdf_acquired"):
                log["official_pdf_acquired"] = False
            log["provenance"] = "official_attempts_incomplete"
            if len(data) > MAX_BYTES:
                attempt["failure_class"] = "pdf_size_limit_exceeded"
                attempt["failure_reason"] = "Official PDF exceeded the configured 50 MiB safety limit."
            elif _origin(get_final) != _origin(source["url"]):
                attempt["failure_class"] = "redirect_outside_approved_origin"
                attempt["failure_reason"] = "Official PDF redirected outside the approved source origin."
            elif content_type not in {"application/pdf", "application/octet-stream"}:
                attempt["failure_class"] = attempt.get("failure_class") or "invalid_content_type"
                attempt["failure_reason"] = "Official PDF response had an unapproved content type."
            write_attempt_log(log, attempt_log_path)
            raise AcquisitionError(f"Official response was not a verified PDF (HTTP {get_status}, {content_type or 'no content type'}).")
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        digest = hashlib.sha256(data).hexdigest()
        log["source_pdf_sha256"] = digest
        log["source_pdf_size_bytes"] = len(data)
        write_attempt_log(log, attempt_log_path)
        return {"path": str(destination), "sha256": digest, "size_bytes": len(data), "attempt_log_path": str(attempt_log_path)}
    except AcquisitionError:
        write_attempt_log(log, attempt_log_path)
        raise
