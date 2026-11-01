import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


USER_AGENT = "PH-EXAM-RESULTS-Acquirer/1.0"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class DownloadError(Exception):
    """Raised when a source document cannot be acquired safely."""


def download_approved_file(
    url: str,
    destination: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Download an HTTPS file without following cross-host redirects."""
    original = urlsplit(url or "")
    if original.scheme != "https" or not original.hostname:
        raise DownloadError("Only valid HTTPS source URLs are allowed.")

    request = Request(url, headers={"User-Agent": USER_AGENT})
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0

    try:
        with urlopen(request, timeout=30) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() != original.hostname.lower():
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
