"""Safe Phase 2 bridge from a validated Watcher event to Python PDF text extraction.

This module never converts PDF text into passer records and never publishes data.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

from extractor.pdf_parser import extract_pdf_lines
from scraper.downloader import download_approved_file
from scraper.monitor import _is_approved_source


class DetectedSourceError(Exception):
    """Raised when a Watcher event is not safe to process."""


def _same_origin(left: str, right: str) -> bool:
    a, b = urlsplit(left), urlsplit(right)
    return (
        a.scheme == b.scheme == "https"
        and (a.hostname or "").lower() == (b.hostname or "").lower()
        and (a.port or 443) == (b.port or 443)
        and not a.username and not a.password
        and not b.username and not b.password
    )


def process_detected_pdf(payload: dict, registry_path: str | Path, output_path: str | Path) -> dict:
    required = ("source_id", "authority", "exam", "detected_url")
    if not isinstance(payload, dict) or any(
        not isinstance(payload.get(key), str) or not payload[key].strip()
        for key in required
    ):
        raise DetectedSourceError("Watcher payload is missing required text fields.")

    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise DetectedSourceError("Source registry must contain a sources array.")

    matches = [
        item for item in registry["sources"]
        if isinstance(item, dict) and item.get("id") == payload["source_id"]
    ]
    if len(matches) != 1:
        raise DetectedSourceError("Source ID must match exactly one registry entry.")
    source = matches[0]

    approved, reason = _is_approved_source(source)
    if not approved or source.get("enabled") is not True:
        raise DetectedSourceError(reason or "Source is not enabled and owner-authorized.")
    if source.get("authority") != payload["authority"] or source.get("exam") != payload["exam"]:
        raise DetectedSourceError("Watcher authority/exam does not match the approved source.")
    detected_url = payload["detected_url"]
    parsed = urlsplit(detected_url)
    drive_mode = False
    if (parsed.hostname or "").lower() == "drive.google.com":
        from urllib.parse import parse_qs
        query = parse_qs(parsed.query)
        file_id = query.get("id", [""])[0]
        allowed_ids = source.get("drive_file_ids", [])
        if (
            parsed.scheme != "https" or parsed.path != "/uc"
            or query.get("export") != ["download"]
            or not isinstance(allowed_ids, list) or file_id not in allowed_ids
            or parsed.username or parsed.password
        ):
            raise DetectedSourceError("Google Drive URL does not match an exact owner-approved file ID.")
        drive_mode = True
    elif not _same_origin(str(source.get("url", "")), detected_url):
        raise DetectedSourceError("Detected PDF is outside the exact approved HTTPS origin.")
    if not drive_mode and not (
        parsed.path.lower().endswith(".pdf")
        or str(payload.get("content_type", "")).lower() == "application/pdf"
    ):
        raise DetectedSourceError("Detected resource is not identified as a PDF.")

    if source.get("file_format") != "pdf":
        raise DetectedSourceError("Approved source file_format must be pdf.")
    if source.get("auto_acquire") is not True:
        report = {
            "status": "awaiting_owner_acquisition_approval",
            "source_id": source["id"],
            "authority": source["authority"],
            "exam": source["exam"],
            "detected_url": detected_url,
            "manual_review_required": True,
            "notice": "Detection was validated, but auto_acquire is not enabled. No file was downloaded.",
        }
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    acquisition_source = {**source, "url": detected_url}
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf_path = destination.with_suffix(".pdf")
    acquisition = download_approved_file(acquisition_source, pdf_path)
    try:
        with pdf_path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise DetectedSourceError("Downloaded content does not have a valid PDF file signature.")
        lines = extract_pdf_lines(pdf_path)
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise

    has_text = len(lines) > 0
    report = {
        "status": (
            "text_extracted_manual_review_required"
            if has_text else "pdf_acquired_no_text_manual_visual_review_required"
        ),
        "source_id": source["id"],
        "authority": source["authority"],
        "exam": source["exam"],
        "detected_url": detected_url,
        "source_file": pdf_path.name,
        "source_file_sha256": acquisition["sha256"],
        "source_file_size_bytes": acquisition["size_bytes"],
        "extracted_line_count": len(lines),
        "manual_review_required": True,
        "visual_pdf_review_required": not has_text,
        "notice": (
            "PDF text was extracted, but this is not passer-record extraction. "
            "No names were normalized, validated, deduplicated, or published."
            if has_text else
            "The PDF was acquired and passed its signature check, but no selectable text was extracted. "
            "It may be scanned or image-based and requires visual review of the retained original PDF. "
            "No OCR, passer-record extraction, or publication was performed."
        ),
        "lines": lines,
    }
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Process one validated Watcher PDF event.")
    parser.add_argument("--payload", required=True, help="Path to JSON Watcher client payload.")
    parser.add_argument("--registry", default="python-engine/config/sources.json")
    parser.add_argument("--output", required=True, help="Path for the private JSON review artifact.")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        report = process_detected_pdf(payload, args.registry, args.output)
    except Exception as exc:
        print(json.dumps({"status": "processing_rejected_or_failed", "error": str(exc)[:500]}))
        return 1
    print(json.dumps({
        "status": report["status"],
        "source_id": report.get("source_id"),
        "extracted_line_count": report.get("extracted_line_count", 0),
        "manual_review_required": report.get("manual_review_required", True),
        "output": args.output,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
