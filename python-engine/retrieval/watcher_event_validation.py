"""Validation helpers for Watcher-originated Google Drive events."""

import re
from urllib.parse import parse_qs, urlsplit


def is_approved_drive_event(payload: dict, source: dict, detected) -> bool:
    """Accept only exact allowlisted IDs or opt-in links from the exact official page."""
    if detected.scheme != "https" or detected.hostname != "drive.google.com":
        return False
    if detected.username or detected.password or detected.port not in (None, 443):
        return False
    if detected.path != "/uc":
        return False

    query = parse_qs(detected.query, keep_blank_values=True)
    if query.get("export") != ["download"]:
        return False
    file_ids = query.get("id", [])
    if len(file_ids) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", file_ids[0]):
        return False

    allowed_ids = source.get("drive_file_ids", [])
    if isinstance(allowed_ids, list) and file_ids[0] in allowed_ids:
        return True

    source_page_url = payload.get("source_page_url")
    if (
        source.get("allow_linked_drive_documents") is not True
        or payload.get("detection_method") != "official_page_drive_link"
        or not isinstance(source_page_url, str)
        or source_page_url != source.get("url")
    ):
        return False

    try:
        page = urlsplit(source_page_url)
        return (
            page.scheme == "https"
            and bool(page.hostname)
            and page.username is None
            and page.password is None
            and page.port in (None, 443)
        )
    except ValueError:
        return False
