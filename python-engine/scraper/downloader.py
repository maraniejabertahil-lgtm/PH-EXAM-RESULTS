import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scraper.safe_http import open_same_origin

from scraper.monitor import _is_approved_source


USER_AGENT = "PH-EXAM-RESULTS-Acquirer/1.0"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class GoogleDriveRedirectHandler(HTTPRedirectHandler):
    """Allow only HTTPS redirects to Google's restricted download host families."""

    @staticmethod
    def _allowed(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and not parsed.username and not parsed.password
            and (
                host in {"drive.google.com", "drive.usercontent.google.com", "storage.googleapis.com"}
                or host.endswith(".googleusercontent.com")
                or host.endswith(".googleapis.com")
            )
        )

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if not self._allowed(new_url):
            raise DownloadError("Google Drive redirect left the restricted Google download host allowlist.")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


class DownloadError(Exception):
    """Raised when a source document cannot be acquired safely."""


def download_approved_file(
    source: dict,
    destination: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Download a file only from an explicitly approved HTTPS source."""
    approved, reason = _is_approved_source(source)
    if not approved or source.get("enabled") is not True:
        raise DownloadError(reason or "Source is disabled.")
    url = source.get("url", "")
    if not isinstance(url, str):
        raise DownloadError("Source URL must be a text URL.")
    original = urlsplit(url)
    if original.scheme != "https" or not original.hostname or original.username or original.password:
        raise DownloadError("Only valid HTTPS source URLs are allowed.")

    drive_mode = (original.hostname or "").lower() == "drive.google.com"
    if drive_mode:
        from urllib.parse import parse_qs
        query = parse_qs(original.query)
        file_id = query.get("id", [""])[0]
        if (
            original.scheme != "https"
            or (original.hostname or "").lower() != "drive.google.com"
            or original.path != "/uc"
            or query.get("export") != ["download"]
            or file_id not in source.get("drive_file_ids", [])
        ):
            raise DownloadError("Google Drive URL is not the exact approved file ID and download route.")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
    original_port = original.port or 443
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0

    try:
        opener = build_opener(GoogleDriveRedirectHandler()) if drive_mode else None
        response_context = opener.open(request, timeout=30) if drive_mode else open_same_origin(request, url, timeout=30)
        with response_context as response:
            final = urlsplit(response.geturl())
            if drive_mode:
                if not GoogleDriveRedirectHandler._allowed(response.geturl()):
                    raise DownloadError("Final Google Drive download host is not allowlisted.")
            elif (
                final.scheme != "https"
                or final.username
                or final.password
                or (final.hostname or "").lower() != original.hostname.lower()
                or (final.port or 443) != original_port
            ):
                raise DownloadError("Cross-host or non-HTTPS redirect rejected.")
            with target.open("wb") as output:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise DownloadError("Source file exceeds the configured download limit.")
                    digest.update(chunk)
                    output.write(chunk)
    except DownloadError:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {exc}") from exc

    return {
        "path": str(target),
        "size_bytes": total,
        "sha256": digest.hexdigest(),
        "source_host": original.hostname.lower(),
    }
