"""Owner-reviewed handoff for results shown in an official examination portal.

No network request is made by this module. The owner must legitimately view
the complete public result and verify every exact name/sequence pair. This
path never automates interactive portal access or bypasses access controls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class OfficialPortalHandoffError(RuntimeError):
    """Raised when an official portal handoff is not adequately identified."""


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url or "")
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OfficialPortalHandoffError("Portal URLs must be credential-free HTTPS URLs.")
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or 443


def verify_official_portal_handoff(
    *, source: dict[str, Any], portal_url: str, evidence_path: str | Path
) -> dict[str, Any]:
    """Validate the approved official portal identity and persist owner attestation."""
    if (
        not isinstance(source, dict)
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("content_access_mode") != "owner_reviewed_portal_handoff"
    ):
        raise OfficialPortalHandoffError("Source is not enabled for owner-reviewed official portal handoff.")

    if _origin(portal_url) != _origin(source.get("url", "")):
        raise OfficialPortalHandoffError("Portal URL is outside the approved official origin.")
    if urlsplit(portal_url).path.rstrip("/") != urlsplit(source["url"]).path.rstrip("/"):
        raise OfficialPortalHandoffError("Portal URL must use the exact approved official portal path.")

    evidence = {
        "schema_version": 1,
        "source_id": source["id"],
        "authority": source["authority"],
        "exam": source["exam"],
        "provenance": "official_direct",
        "acquisition_method": "owner_reviewed_manual_portal_handoff",
        "official_source_url": source["url"],
        "official_portal_url": portal_url,
        "official_portal_origin_and_path_verified": True,
        "official_content_reviewed_by_owner": True,
        "record_mapping_reviewed_by_owner": True,
        "automated_portal_access_attempted": False,
        "access_control_bypass_attempted": False,
        "content_body_downloaded_by_automation": False,
        "pdf_downloaded": False,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    destination = Path(evidence_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return evidence
