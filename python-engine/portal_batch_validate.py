"""Validate a reviewed CSC portal batch locally; this module never publishes it."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acquisition.official_portal_handoff import (
    OfficialPortalHandoffError,
    verify_official_portal_handoff,
)
from processor.greenlight import validate_records, write_validation_report
from publisher.json_builder import build_dataset


class PortalBatchError(RuntimeError):
    """Raised when a reviewed portal batch fails provenance or validation."""


def validate_portal_batch(
    batch: dict[str, Any], *, repository_root: str | Path
) -> dict[str, Any]:
    """Validate owner-reviewed records and build local artifacts only."""
    root = Path(repository_root).resolve()
    required = (
        "authority", "exam", "year", "announced_count", "source_id",
        "official_source_url", "official_portal_url", "publicly_released",
        "official_content_reviewed", "record_mapping_reviewed", "records",
    )
    missing = [key for key in required if key not in batch]
    if missing:
        raise PortalBatchError("Missing required fields: " + ", ".join(missing))
    if batch.get("authority") != "CSC" or batch.get("provenance") != "official_direct":
        raise PortalBatchError("This validator accepts CSC official-direct batches only.")
    if batch.get("publicly_released") is not True:
        raise PortalBatchError("Only publicly released results may be processed.")
    if batch.get("official_content_mode") != "owner_reviewed_portal_handoff":
        raise PortalBatchError("Invalid official_content_mode.")
    if batch.get("official_content_reviewed") is not True:
        raise PortalBatchError("Owner review of the complete official result is required.")
    if batch.get("record_mapping_reviewed") is not True:
        raise PortalBatchError("Owner review of every exact name/sequence pair is required.")
    if not isinstance(batch.get("records"), list) or not batch["records"]:
        raise PortalBatchError("A non-empty reviewed records list is required.")

    registry_path = root / "python-engine/config/sources.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    matches = [
        source for source in registry.get("sources", [])
        if source.get("id") == batch.get("source_id")
    ]
    if len(matches) != 1:
        raise PortalBatchError("source_id must match exactly one source registry entry.")
    source = matches[0]
    if (
        source.get("authority") != "CSC"
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("content_access_mode") != "owner_reviewed_portal_handoff"
        or source.get("url") != batch.get("official_source_url")
    ):
        raise PortalBatchError("Batch does not match an enabled official CSC portal source.")
    if source.get("exam_scope") != "all" and source.get("exam") != batch.get("exam"):
        raise PortalBatchError("Exam identifier does not match the approved source.")

    evidence_path = root / "python-engine/artifacts/official-content-evidence.json"
    try:
        evidence = verify_official_portal_handoff(
            source=source,
            portal_url=batch["official_portal_url"],
            evidence_path=evidence_path,
        )
    except OfficialPortalHandoffError as exc:
        raise PortalBatchError(str(exc)) from exc

    report = validate_records(
        batch["records"],
        announced_count=batch["announced_count"],
        provenance="official_direct",
    )
    report["source_id"] = source["id"]
    report["official_source_url"] = source["url"]
    report["official_portal_url"] = batch["official_portal_url"]
    report["official_content_mode"] = "owner_reviewed_portal_handoff"
    report["official_content_evidence"] = str(evidence_path.relative_to(root))
    report["source_pdf_sha256"] = None

    report_path = root / "python-engine/artifacts/validation-report.json"
    write_validation_report(report, report_path)
    if report.get("publication_allowed") is not True or report.get("greenlight_score") != 100:
        raise PortalBatchError(
            f"Greenlight rejected the batch ({report.get('greenlight_score', 0)}/100)."
        )

    output_dir = root / "python-engine/artifacts/dataset"
    manifest = build_dataset(
        batch["records"],
        authority="CSC",
        exam=batch["exam"],
        year=batch["year"],
        output_dir=output_dir,
        greenlight_report=report,
        provenance="official_direct",
    )
    return {"report": report, "report_path": report_path, "manifest": manifest, "evidence": evidence}
