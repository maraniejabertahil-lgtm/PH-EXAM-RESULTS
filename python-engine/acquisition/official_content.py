"""Verify an official article's link for owner-reviewed content handoff.

This path records the official source link without downloading a PDF or accessing
the linked Google Drive file. A human owner reviews the publicly released
contents and supplies exact name/sequence pairs in the reviewed batch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from typing import Any

USER_AGENT = "PH-EXAM-RESULTS-ContentVerifier/1.0"
MAX_ARTICLE_BYTES = 2 * 1024 * 1024


class OfficialContentError(RuntimeError):
    """Raised when official content provenance cannot be verified safely."""


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def _https_url(value: str, label: str) -> str:
    parsed = urlsplit(value or "")
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OfficialContentError(f"{label} must be a credential-free HTTPS URL.")
    return value


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(_https_url(value, "URL"))
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or 443


def _request(url: str, timeout: int, limit: int) -> tuple[int, Any, str, bytes]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            return response.status, response.headers, response.geturl(), body
    except HTTPError as exc:
        return exc.code, exc.headers, exc.geturl(), exc.read(4096)
    except (URLError, TimeoutError, OSError) as exc:
        raise OfficialContentError(f"Official source request failed: {exc}") from exc


def _robots_allowed(robots_url: str, target_url: str, timeout: int) -> bool:
    status, _headers, final_url, body = _request(robots_url, timeout, 256 * 1024)
    if _origin(final_url) != _origin(robots_url):
        raise OfficialContentError("robots.txt redirected outside the approved official origin.")
    if status == 404:
        lines: list[str] = []
    elif status == 200:
        if len(body) > 256 * 1024:
            raise OfficialContentError("robots.txt exceeded the configured size limit.")
        lines = body.decode("utf-8", errors="replace").splitlines()
    else:
        raise OfficialContentError(f"Unable to verify robots.txt policy (HTTP {status}).")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(lines)
    return parser.can_fetch(USER_AGENT, target_url)


def _canonical_link(value: str) -> tuple[str, str, str, str]:
    parsed = urlsplit(value)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.path, parsed.query


def verify_official_content_link(
    *,
    source: dict[str, Any],
    article_url: str,
    content_url: str,
    evidence_path: str | Path,
    timeout: int = 20,
) -> dict[str, Any]:
    """Verify the exact official article link; never fetch the linked content."""
    if (
        not isinstance(source, dict)
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
    ):
        raise OfficialContentError("Source is not enabled and owner-authorized.")

    _https_url(article_url, "Official article URL")
    _https_url(content_url, "Official content URL")
    if _origin(article_url) != _origin(source.get("url", "")):
        raise OfficialContentError("Official article is outside the approved source origin.")
    if _origin(content_url)[1] != "drive.google.com" or source.get("allow_linked_drive_documents") is not True:
        raise OfficialContentError("Manual content handoff is restricted to explicitly allowed official Google Drive links.")
    robots_url = source.get("robots_policy_url")
    if source.get("robots_policy_verified") is not True or not isinstance(robots_url, str):
        raise OfficialContentError("A verified official robots.txt policy is required.")
    if _origin(robots_url) != _origin(source["url"]):
        raise OfficialContentError("robots_policy_url must use the approved official origin.")
    if not _robots_allowed(robots_url, article_url, timeout):
        raise OfficialContentError("robots.txt disallows the official article.")

    status, headers, final_url, body = _request(article_url, timeout, MAX_ARTICLE_BYTES)
    if status != 200:
        raise OfficialContentError(f"Official article returned HTTP {status}.")
    if len(body) > MAX_ARTICLE_BYTES:
        raise OfficialContentError("Official article exceeded the configured size limit.")
    content_type = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise OfficialContentError("Official article response was not HTML.")
    if _origin(final_url) != _origin(source["url"]):
        raise OfficialContentError("Official article redirected outside the approved source origin.")

    parser = _AnchorParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    linked_urls = {
        urljoin(final_url, href)
        for href in parser.hrefs
    }
    if not any(
        _canonical_link(linked) == _canonical_link(content_url)
        for linked in linked_urls
        if urlsplit(linked).scheme.lower() == "https"
    ):
        raise OfficialContentError("The supplied content URL is not linked from the official article.")

    evidence = {
        "schema_version": 1,
        "source_id": source["id"],
        "authority": source["authority"],
        "exam": source["exam"],
        "provenance": "official_direct",
        "acquisition_method": "owner_reviewed_manual_content_handoff",
        "official_source_url": source["url"],
        "official_article_url": article_url,
        "official_content_url": content_url,
        "official_article_link_verified": True,
        "official_content_reviewed_by_owner": True,
        "content_body_downloaded_by_automation": False,
        "pdf_downloaded": False,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "retrieval_user_agent": USER_AGENT,
    }
    destination = Path(evidence_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return evidence


def verify_official_preview_link(
    *,
    source: dict[str, Any],
    article_url: str,
    content_url: str,
    evidence_path: str | Path,
    timeout: int = 20,
) -> dict[str, Any]:
    """Verify an official PRC article link before using its ordinary public preview UI."""
    if (
        not isinstance(source, dict)
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("allow_linked_drive_documents") is not True
    ):
        raise OfficialContentError("Source is not enabled and authorized for linked public previews.")

    _https_url(article_url, "Official article URL")
    _https_url(content_url, "Official content URL")
    if _origin(article_url) != _origin(source.get("url", "")):
        raise OfficialContentError("Official article is outside the approved source origin.")
    if _origin(content_url)[1] != "drive.google.com":
        raise OfficialContentError("Public preview is restricted to verified Google Drive links.")
    robots_url = source.get("robots_policy_url")
    if source.get("robots_policy_verified") is not True or not isinstance(robots_url, str):
        raise OfficialContentError("A verified official robots.txt policy is required.")
    if _origin(robots_url) != _origin(source["url"]):
        raise OfficialContentError("robots_policy_url must use the approved official origin.")
    if not _robots_allowed(robots_url, article_url, timeout):
        raise OfficialContentError("robots.txt disallows the official article.")

    status, headers, final_url, body = _request(article_url, timeout, MAX_ARTICLE_BYTES)
    if status != 200:
        raise OfficialContentError(f"Official article returned HTTP {status}.")
    if len(body) > MAX_ARTICLE_BYTES:
        raise OfficialContentError("Official article exceeded the configured size limit.")
    content_type = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise OfficialContentError("Official article response was not HTML.")
    if _origin(final_url) != _origin(source["url"]):
        raise OfficialContentError("Official article redirected outside the approved source origin.")

    parser = _AnchorParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    if not any(
        _canonical_link(linked) == _canonical_link(content_url)
        for linked in (urljoin(final_url, href) for href in parser.hrefs)
        if urlsplit(linked).scheme.lower() == "https"
    ):
        raise OfficialContentError("The supplied Drive file is not linked from the official article.")

    evidence = {
        "schema_version": 1,
        "source_id": source["id"],
        "authority": source["authority"],
        "provenance": "official_direct",
        "acquisition_method": "ordinary_public_preview_ui",
        "official_source_url": source["url"],
        "official_article_url": article_url,
        "official_content_url": content_url,
        "official_article_link_verified": True,
        "public_preview_content_downloaded": False,
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "retrieval_user_agent": USER_AGENT,
    }
    destination = Path(evidence_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return evidence


def verify_official_public_content_link(
    *,
    source: dict[str, Any],
    article_url: str,
    content_url: str,
    allowed_hosts: list[str],
    evidence_path: str | Path,
    timeout: int = 20,
) -> dict[str, Any]:
    """Verify an ordinary public HTML/content link on an explicitly approved host."""
    if (
        not isinstance(source, dict)
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
    ):
        raise OfficialContentError("Source is not enabled and owner-authorized.")
    _https_url(article_url, "Official article URL")
    _https_url(content_url, "Official content URL")
    if _origin(article_url) != _origin(source.get("url", "")):
        raise OfficialContentError("Official article is outside the approved source origin.")
    content = urlsplit(content_url)
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or any(not isinstance(host, str) or not host for host in allowed_hosts)
        or (content.hostname or "").lower() not in {host.lower() for host in allowed_hosts}
    ):
        raise OfficialContentError("Official public-content host is not explicitly allowlisted.")
    approved_urls = source.get("public_content_urls")
    if not isinstance(approved_urls, list) or content_url not in approved_urls:
        raise OfficialContentError("Official content URL is not explicitly approved for this examination.")
    robots_url = source.get("robots_policy_url")
    if source.get("robots_policy_verified") is not True or not isinstance(robots_url, str):
        raise OfficialContentError("A verified official robots.txt policy is required.")
    if _origin(robots_url) != _origin(source["url"]):
        raise OfficialContentError("robots_policy_url must use the approved official origin.")
    if not _robots_allowed(robots_url, article_url, timeout):
        raise OfficialContentError("robots.txt disallows the official article.")
    if _origin(content_url) == _origin(article_url):
        if not _robots_allowed(robots_url, content_url, timeout):
            raise OfficialContentError("robots.txt disallows the official content URL.")
    else:
        content_robots = source.get("public_content_robots_policy_url")
        if (
            source.get("public_content_robots_policy_verified") is not True
            or not isinstance(content_robots, str)
            or _origin(content_robots) != _origin(content_url)
        ):
            raise OfficialContentError("A separately verified robots policy is required for the external content host.")
        if not _robots_allowed(content_robots, content_url, timeout):
            raise OfficialContentError("The external content host robots policy disallows this URL.")

    status, headers, final_url, body = _request(article_url, timeout, MAX_ARTICLE_BYTES)
    if status != 200:
        raise OfficialContentError(f"Official article returned HTTP {status}.")
    if len(body) > MAX_ARTICLE_BYTES:
        raise OfficialContentError("Official article exceeded the configured size limit.")
    content_type = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise OfficialContentError("Official article response was not HTML.")
    if _origin(final_url) != _origin(source["url"]):
        raise OfficialContentError("Official article redirected outside the approved source origin.")
    parser = _AnchorParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    if not any(
        _canonical_link(linked) == _canonical_link(content_url)
        for linked in (urljoin(final_url, href) for href in parser.hrefs)
        if urlsplit(linked).scheme.lower() == "https"
    ):
        raise OfficialContentError("The supplied content URL is not linked from the official article.")

    evidence = {
        "schema_version": 1,
        "source_id": source["id"],
        "authority": source["authority"],
        "provenance": "official_direct",
        "acquisition_method": "ordinary_public_content_link",
        "official_source_url": source["url"],
        "official_article_url": article_url,
        "official_content_url": content_url,
        "official_article_link_verified": True,
        "content_host_allowlisted": True,
        "robots_policy_verified": True,
        "access_controls_bypassed": False,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "retrieval_user_agent": USER_AGENT,
    }
    destination = Path(evidence_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    temporary.replace(destination)
    return evidence
