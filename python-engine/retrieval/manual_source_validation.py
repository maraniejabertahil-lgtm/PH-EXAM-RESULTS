"""Owner-triggered validation-only confirmation for disabled official sources.

This module deliberately does not fetch Drive content, acquire PDFs, extract data,
or publish results. It only records that an exact owner-approved Drive ID was
selected for a disabled source marked manual_drop_required.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit


def build_manual_source_validation_report(
    registry: dict,
    source_id: str,
    drive_file_id: str,
    confirm_validation_only: bool,
    created_at: str | None = None,
) -> dict:
    if confirm_validation_only is not True:
        raise ValueError("Explicit validation-only confirmation is required.")

    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("A source ID is required.")
    if not isinstance(drive_file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", drive_file_id):
        raise ValueError("The Drive file ID format is invalid.")

    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("The source registry is invalid.")

    matches = [item for item in sources if isinstance(item, dict) and item.get("id") == source_id]
    if len(matches) != 1:
        raise ValueError("The source ID must match exactly one registry entry.")
    source = matches[0]

    if source.get("enabled") is not False:
        raise ValueError("Manual validation is only allowed for a disabled source.")
    if source.get("manual_drop_required") is not True:
        raise ValueError("The source is not marked as requiring manual handling.")
    if source.get("source_type") != "official" or source.get("authorized") is not True:
        raise ValueError("The source must be an owner-authorized official source.")
    if source.get("file_format") != "pdf":
        raise ValueError("The source must declare PDF as its expected format.")

    approved_ids = source.get("drive_file_ids")
    if not isinstance(approved_ids, list) or drive_file_id not in approved_ids:
        raise ValueError("The Drive file ID is not in this source's exact owner-approved allowlist.")

    source_url = source.get("url")
    try:
        parsed = urlsplit(source_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("The registered official source URL is invalid.") from None

    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return {
        "status": "manual_source_confirmed_validation_only",
        "validation_only": True,
        "source_id": source_id,
        "authority": source.get("authority"),
        "exam": source.get("exam"),
        "source_type": source.get("source_type"),
        "source_enabled": False,
        "manual_drop_required": True,
        "source_page_url": source_url,
        "drive_file_id": drive_file_id,
        "detected_url": "https://drive.google.com/uc?export=download&id=" + quote(drive_file_id, safe=""),
        "detection_method": "manual_drop",
        "created_at": timestamp,
        "pdf_acquired": False,
        "extraction_performed": False,
        "published": False,
        "notes": "Owner-confirmed allowlisted Drive ID only. No network request or PDF download was performed.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a validation-only report for an owner-approved disabled source.")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--drive-file-id", required=True)
    parser.add_argument("--confirm-validation-only", required=True, choices=["true", "false"])
    args = parser.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    report = build_manual_source_validation_report(
        registry=registry,
        source_id=args.source_id,
        drive_file_id=args.drive_file_id,
        confirm_validation_only=args.confirm_validation_only == "true",
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
