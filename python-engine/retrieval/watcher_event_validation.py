"""Validation helpers for Watcher-originated Google Drive events."""

import re
from urllib.parse import parse_qs, urlsplit


def is_approved_drive_event(payload: dict, source: dict, detected) -> bool:
    """Accept only exact allowlisted IDs or opt-in links from the exact official page."""
    try:
        if detected.scheme != "https" or detected.hostname != "drive.google.com":
            return False
        if detected.username or detected.password or detected.port not in (None, 443):
            return False
        if detected.path != "/uc":
            return False
    except ValueError:
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
        page_origin = (
            page.scheme,
            (page.hostname or "").lower(),
            page.port or 443,
        )
        if (
            page.scheme != "https"
            or not page.hostname
            or page.username is not None
            or page.password is not None
            or page.port not in (None, 443)
        ):
            return False

        article_url = payload.get("source_article_url")
        if source.get("discover_official_result_articles") is True:
            if not isinstance(article_url, str) or not article_url:
                return False
        elif article_url not in (None, ""):
            return False

        if article_url:
            article = urlsplit(article_url)
            article_origin = (
                article.scheme,
                (article.hostname or "").lower(),
                article.port or 443,
            )
            allowed_path = (
                article.path.startswith("/article/")
                or re.fullmatch(r"/node/[0-9]+/?", article.path) is not None
            )
            if (
                article_origin != page_origin
                or article.scheme != "https"
                or article.username is not None
                or article.password is not None
                or article.port not in (None, 443)
                or article.query
                or article.fragment
                or not allowed_path
            ):
                return False
        return True
    except ValueError:
        return False
