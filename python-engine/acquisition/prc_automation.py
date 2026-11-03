"""Compliant public PRC result discovery and linked-Drive acquisition.

Only follows links published by the official PRC page. Google Drive retrieval uses
its ordinary public-download endpoint; it never supplies credentials, solves
CAPTCHAs, or follows sign-in/verification interstitials.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

USER_AGENT = "PH-EXAM-RESULTS-PythonAcquirer/1.0 (+https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS)"
MAX_HTML = 3 * 1024 * 1024
MAX_PDF = 50 * 1024 * 1024
ALLOWED_DRIVE_HOSTS = {"drive.google.com", "drive.usercontent.google.com"}


class PRCAutomationError(RuntimeError):
    pass


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None
            self._text = []


def _https(url: str, label: str) -> str:
    p = urlsplit(url or "")
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise PRCAutomationError(f"{label} must be a credential-free HTTPS URL.")
    return url


def _origin(url: str):
    p = urlsplit(_https(url, "URL"))
    return p.scheme, p.hostname.lower(), p.port or 443


def _get(url: str, limit: int, timeout: int = 25):
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,application/octet-stream",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            return response.status, response.headers, response.geturl(), body
    except HTTPError as exc:
        return exc.code, exc.headers, exc.geturl(), exc.read(min(limit, 8192))
    except (URLError, TimeoutError, OSError) as exc:
        raise PRCAutomationError(f"Public source request failed: {exc}") from exc


def _robots_allow(robots_url: str, target_url: str) -> bool:
    status, headers, final_url, body = _get(robots_url, 1024 * 1024)
    if status == 404:
        lines = []
    elif status == 200:
        if _origin(final_url) != _origin(robots_url):
            raise PRCAutomationError("robots.txt redirected outside its official origin.")
        lines = body.decode("utf-8", errors="replace").splitlines()
    else:
        raise PRCAutomationError(f"Cannot verify robots.txt policy (HTTP {status}).")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(lines)
    return parser.can_fetch(USER_AGENT, target_url)


def discover_result_articles(listing_url: str, robots_url: str, max_pages: int = 3):
    """Find linked PRC result-release articles from the official listing page."""
    _https(listing_url, "PRC listing URL")
    if _origin(listing_url) != _origin(robots_url):
        raise PRCAutomationError("PRC listing and robots URLs must share the approved origin.")
    if not _robots_allow(robots_url, listing_url):
        raise PRCAutomationError("PRC robots.txt disallows the official listing page.")
    status, headers, final_url, body = _get(listing_url, MAX_HTML)
    if status != 200 or "text/html" not in (headers.get("Content-Type") or "").lower():
        raise PRCAutomationError(f"PRC listing retrieval failed (HTTP {status}).")
    if _origin(final_url) != _origin(listing_url):
        raise PRCAutomationError("PRC listing redirected outside the official origin.")
    parser = _Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    found = []
    for href, label in parser.links:
        absolute = urljoin(final_url, href)
        parsed = urlsplit(absolute)
        text = label.casefold()
        if (
            _origin(absolute) == _origin(listing_url)
            and "/article/" in parsed.path
            and ("result" in text or "licensure examination" in text)
        ):
            found.append({"article_url": absolute, "title": label})
    # Keep deterministic order and avoid duplicate links.
    unique = []
    seen = set()
    for item in found:
        if item["article_url"] not in seen:
            seen.add(item["article_url"])
            unique.append(item)
    return unique[: max(1, min(int(max_pages) * 10, 30))]


def _drive_id(url: str) -> str:
    p = urlsplit(_https(url, "Official linked document URL"))
    if p.hostname.lower() not in ALLOWED_DRIVE_HOSTS:
        raise PRCAutomationError("Official result document is not hosted on an allowed public Google Drive host.")
    match = re.search(r"/file/d/([A-Za-z0-9_-]{10,})", p.path)
    if match:
        return match.group(1)
    query = parse_qs(p.query)
    file_id = (query.get("id") or [None])[0]
    if file_id and re.fullmatch(r"[A-Za-z0-9_-]{10,}", file_id):
        return file_id
    raise PRCAutomationError("Could not identify a Google Drive file ID in the official link.")


def parse_official_article(article_url: str, html: bytes):
    """Return official article facts and its exact linked successful-examinees PDFs."""
    parser = _Links()
    text_parser = _Text()
    decoded = html.decode("utf-8", errors="replace")
    parser.feed(decoded)
    text_parser.feed(decoded)
    page_text = " ".join(text_parser.parts)
    # PRC release articles state e.g. '18,376 elementary teachers ... passed'.
    counts = {}
    for level in ("elementary", "secondary"):
        match = re.search(
            rf"([0-9][0-9,]*)\s+{level}\s+(?:teachers|passers|examinees)?[\s\S]{0,240}?\bpassed\b",
            page_text, re.I,
        )
        if match:
            counts[level] = int(match.group(1).replace(",", ""))
    docs = []
    for href, label in parser.links:
        label_norm = " ".join(label.casefold().split())
        if "list of successful examinees" not in label_norm:
            continue
        absolute = urljoin(article_url, href)
        try:
            file_id = _drive_id(absolute)
        except PRCAutomationError:
            continue
        level = "elementary" if "elementary" in label_norm else "secondary" if "secondary" in label_norm else None
        if level:
            docs.append({"level": level, "url": absolute, "drive_file_id": file_id})
    return {"announced_counts": counts, "documents": docs, "article_url": article_url}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def acquire_public_drive_pdf(*, official_article_url: str, linked_document_url: str,
                             output_path: str | Path, attempt_log_path: str | Path,
                             timeout: int = 30):
    """Download only a directly public PDF linked from the supplied official article."""
    article_url = _https(official_article_url, "Official article URL")
    document_url = _https(linked_document_url, "Official linked document URL")
    if _origin(article_url)[1] != "www.prc.gov.ph":
        raise PRCAutomationError("Article is not on the approved PRC official host.")
    file_id = _drive_id(document_url)
    log = {
        "schema_version": 1, "source_id": "PRC-EXAM-RESULTS-HOMEPAGE",
        "article_url": article_url, "official_link": document_url,
        "drive_file_id": file_id, "attempted_at_unix": int(time.time()),
        "method": "public_google_drive_download_endpoint",
        "credentials_used": False, "access_control_bypass_attempted": False,
        "acquired": False,
    }
    # Confirm the file ID is actually present in the official article HTML.
    if not _robots_allow("https://www.prc.gov.ph/robots.txt", article_url):
        raise PRCAutomationError("PRC robots.txt disallows this official article.")
    status, headers, final_url, article_html = _get(article_url, MAX_HTML, timeout)
    if status != 200 or "text/html" not in (headers.get("Content-Type") or "").lower():
        raise PRCAutomationError(f"Official PRC article unavailable (HTTP {status}).")
    if _origin(final_url)[1] != "www.prc.gov.ph":
        raise PRCAutomationError("Official article redirected outside PRC.")
    parsed = parse_official_article(article_url, article_html)
    if not any(item["drive_file_id"] == file_id for item in parsed["documents"]):
        raise PRCAutomationError("Drive file ID is not linked as a successful-examinees list by this official article.")

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    status, headers, final_url, data = _get(download_url, MAX_PDF, timeout)
    content_type = (headers.get("Content-Type") or "").split(";", 1)[0].lower()
    final_host = (urlsplit(final_url).hostname or "").lower()
    valid = (
        status == 200 and final_host in ALLOWED_DRIVE_HOSTS
        and content_type == "application/pdf" and b"%PDF-" in data[:1024]
        and len(data) <= MAX_PDF
    )
    log.update({
        "http_status": status, "content_type": content_type,
        "final_url": final_url, "bytes_received": len(data),
        "pdf_signature_valid": b"%PDF-" in data[:1024],
        "sha256": hashlib.sha256(data).hexdigest() if valid else None,
    })
    Path(attempt_log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(attempt_log_path).write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not valid:
        reason = "Google Drive returned a non-PDF response; sign-in, CAPTCHA, or verification pages are not bypassed."
        raise PRCAutomationError(f"{reason} HTTP {status}, content-type={content_type or 'missing'}.")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(destination)
    log["acquired"] = True
    Path(attempt_log_path).write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(destination), "sha256": log["sha256"], "size_bytes": len(data), "evidence": str(attempt_log_path)}


def extract_sequence_name_pairs(extraction: dict, announced_count: int):
    """Conservative PRC roll extractor; accepts only a unique complete sequence mapping."""
    if isinstance(announced_count, bool) or not isinstance(announced_count, int) or announced_count < 1:
        raise PRCAutomationError("announced_count must be a positive integer.")
    candidates = []
    for page in extraction.get("pages", []):
        for table in page.get("tables", []):
            if not isinstance(table, list):
                continue
            for row in table:
                if not isinstance(row, (list, tuple)):
                    continue
                cells = [str(cell).strip() if cell is not None else "" for cell in row]
                for idx, cell in enumerate(cells[:-1]):
                    if not re.fullmatch(r"\d{1,6}", cell):
                        continue
                    seq = int(cell)
                    if not 1 <= seq <= announced_count:
                        continue
                    name = cells[idx + 1]
                    if re.fullmatch(r"[A-Z][A-Z .,'’()\-]{2,}", name, re.I) and re.search(r"[A-Za-z]", name):
                        candidates.append((seq, " ".join(name.split())))
    # Remove exact duplicate detections caused by overlapping table strategies.
    unique = {}
    for seq, name in candidates:
        if seq in unique and unique[seq] != name:
            raise PRCAutomationError(f"Conflicting names detected for official sequence {seq}.")
        unique[seq] = name
    expected = set(range(1, announced_count + 1))
    actual = set(unique)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PRCAutomationError(
            f"Extraction is incomplete: {len(unique)}/{announced_count} sequences; "
            f"missing={missing[:10]}, extra={extra[:10]}. No publication permitted."
        )
    records = [{"name": unique[i], "sequence_number": str(i)} for i in range(1, announced_count + 1)]
    if len({r["name"] for r in records}) != len(records):
        raise PRCAutomationError("Duplicate passer names detected; no publication permitted.")
    return records
