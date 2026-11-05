#!/usr/bin/env python3
"""Download only owner-approved, publicly accessible CSC Google Drive PDFs.

This is a diagnostic companion to the Cloudflare Worker. It does not bypass
Google permissions, CAPTCHAs, login walls, or other access controls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

ALLOWED_DRIVE_HOSTS = {"drive.google.com", "drive.usercontent.google.com"}
ALLOWED_DRIVE_PATHS = {"/uc", "/download"}
MAX_PDF_BYTES = 50 * 1024 * 1024
USER_AGENT = "PH-EXAM-RESULTS-DriveProbe/1.0"


class RetrievalError(RuntimeError):
    """A safe, actionable public-file retrieval error."""


def validate_redirect_url(url: str, file_id: str) -> None:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_DRIVE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ALLOWED_DRIVE_PATHS
        or query.get("id") != [file_id]
    ):
        raise RetrievalError(
            "Blocked Google Drive redirect: HTTPS host, download path, "
            "or exact approved file ID did not match."
        )


class ApprovedDriveRedirectHandler(HTTPRedirectHandler):
    def __init__(self, file_id: str):
        super().__init__()
        self.file_id = file_id

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_redirect_url(newurl, self.file_id)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_approved_ids(registry_path: Path, source_id: str) -> list[str]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"Cannot read source registry: {exc}") from exc

    for source in registry.get("sources", []):
        if source.get("id") != source_id:
            continue
        if not (
            source.get("source_type") == "official"
            and source.get("authority") == "CSC"
            and source.get("authorized") is True
            and source.get("enabled") is True
            and source.get("direct_drive_fallback") is True
        ):
            raise RetrievalError(
                "Source is not enabled as an authorized CSC direct-Drive fallback."
            )
        raw_ids = source.get("drive_file_ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            raise RetrievalError("No pre-approved Google Drive file IDs are configured.")
        ids = []
        for file_id in raw_ids:
            if not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", file_id):
                raise RetrievalError("Source registry contains an invalid Drive file ID.")
            if file_id not in ids:
                ids.append(file_id)
        return ids
    raise RetrievalError(f"Approved source not found: {source_id}")


def validate_pdf_bytes(data: bytes) -> None:
    if not data or b"%PDF-" not in data[:1024]:
        raise RetrievalError(
            "Google Drive response is not a verified PDF (it may be an HTML "
            "interstitial, permission page, or unavailable file)."
        )
    if len(data) > MAX_PDF_BYTES:
        raise RetrievalError(f"PDF exceeds the {MAX_PDF_BYTES}-byte safety limit.")


def download_approved_pdf(file_id: str, timeout: int = 30) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", file_id):
        raise RetrievalError("Invalid Google Drive file ID.")
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    opener = build_opener(
        HTTPCookieProcessor(CookieJar()),
        ApprovedDriveRedirectHandler(file_id),
    )
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].lower()
            data = response.read(MAX_PDF_BYTES + 1)
    except HTTPError as exc:
        raise RetrievalError(f"Google Drive returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RetrievalError(f"Google Drive retrieval failed: {exc}") from exc

    if content_type == "text/html":
        raise RetrievalError(
            "Google Drive returned HTML instead of a PDF; public download may "
            "require owner permission or a confirmation page."
        )
    validate_pdf_bytes(data)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "sources.json",
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/drive-probe"))
    args = parser.parse_args(argv)

    try:
        file_ids = load_approved_ids(args.registry, args.source_id)
    except RetrievalError as exc:
        print(json.dumps({"status": "configuration_error", "error": str(exc)}))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for file_id in file_ids:
        try:
            data = download_approved_pdf(file_id)
            output = args.output_dir / f"{args.source_id}-{file_id}.pdf"
            output.write_bytes(data)
            results.append({
                "file_id": file_id,
                "status": "downloaded_pdf",
                "bytes": len(data),
                "path": str(output),
            })
        except (RetrievalError, OSError) as exc:
            results.append({
                "file_id": file_id,
                "status": "retrieval_failed",
                "error": str(exc),
            })

    print(json.dumps({"source_id": args.source_id, "results": results}, indent=2))
    return 0 if results and all(item["status"] == "downloaded_pdf" for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
