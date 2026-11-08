"""Acquire and normalize a detected public PRC result using reviewed mappings.

Exit codes: 0 is ready for the Greenlight/GitOps pipeline, 2 is an invalid
event, and 3 is a safe stop requiring a source, access, or mapping review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from acquisition.official_content import (
    OfficialContentError,
    verify_official_preview_link,
)
from acquisition.public_preview import (
    PublicPreviewCaptureError,
    parse_public_preview_records,
    parse_public_preview_snapshots,
)
from prc_adapters import REGISTRY, NeedsReview
from database.d1_client import record_activity

ALLOWED_HOSTS = {
    "www.prc.gov.ph",
    "prc.gov.ph",
    "drive.google.com",
    "docs.google.com",
    "drive.usercontent.google.com",
}
FORMATS = {"csv", "json", "html", "pdf"}
REQUIRED_EVENT_FIELDS = (
    "schema_version", "source_id", "article_url", "exam_code", "exam_title",
    "exam_year", "list_type", "content_urls", "detected_at",
)
MAX_CONTENT_BYTES = 25 * 1024 * 1024
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
HERE = Path(__file__).parent


class NeedsReviewError(RuntimeError):
    """Raised when an otherwise valid release cannot safely proceed."""


def _safe_https_url(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty HTTPS URL.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} is malformed.") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError(f"{label} is outside the approved credential-free HTTPS hosts.")
    return value


def validate_event(event: object) -> list[str]:
    if not isinstance(event, dict):
        return ["event must be a JSON object"]
    errors = [f"missing {key}" for key in REQUIRED_EVENT_FIELDS if key not in event]
    if errors:
        return errors
    if event["schema_version"] != "1":
        errors.append("unsupported schema_version")
    if not isinstance(event["source_id"], str) or not event["source_id"].strip():
        errors.append("source_id must be a non-empty string")
    if not isinstance(event["exam_code"], str) or not event["exam_code"].strip():
        errors.append("exam_code must be a non-empty string")
    elif event["exam_code"] == "LICENSURE-EXAM-RESULTS":
        errors.append("generic exam code is not eligible for acquisition")
    if not isinstance(event["exam_title"], str) or not event["exam_title"].strip():
        errors.append("exam_title must be a non-empty string")
    if isinstance(event["exam_year"], bool) or not isinstance(event["exam_year"], int):
        errors.append("exam_year must be an integer")
    if event["list_type"] != "successful_examinees":
        errors.append("unsupported list_type")
    if isinstance(event.get("announced_count"), bool) or not isinstance(event.get("announced_count"), int) or event["announced_count"] < 1:
        errors.append("announced_count must be a positive integer")
    if event["exam_code"] == "LEPT" and event.get("result_level") not in ("elementary", "secondary"):
        errors.append("LEPT requires result_level elementary|secondary")
    try:
        _safe_https_url(event["article_url"], "article_url")
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if urlsplit(event["article_url"]).hostname.lower() not in {"www.prc.gov.ph", "prc.gov.ph"}:
            errors.append("article_url must use an official PRC host")
    content_urls = event["content_urls"]
    if not isinstance(content_urls, list) or not content_urls:
        errors.append("content_urls must be a non-empty list")
    else:
        for index, content in enumerate(content_urls):
            if not isinstance(content, dict):
                errors.append(f"content_urls[{index}] must be an object")
                continue
            try:
                _safe_https_url(content.get("url"), f"content_urls[{index}].url")
            except ValueError as exc:
                errors.append(str(exc))
            if not isinstance(content.get("format"), str) or content["format"] not in FORMATS:
                errors.append(f"content_urls[{index}] has an unsupported format")
    return errors


def _read_registry(registry_path: str | Path | None) -> list[dict]:
    path = Path(registry_path) if registry_path else HERE / "config" / "sources.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NeedsReviewError(f"Unable to read the approved source registry: {exc}") from exc
    sources = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(sources, list) or any(not isinstance(item, dict) for item in sources):
        raise NeedsReviewError("The approved source registry has an invalid schema.")
    return sources


def _approved_source(event: dict, registry_path: str | Path | None) -> dict:
    sources = _read_registry(registry_path)
    matches = [source for source in sources if source.get("id") == event["source_id"]]
    if len(matches) != 1:
        raise NeedsReviewError("source_id must match exactly one approved registry entry.")
    source = matches[0]
    if (
        source.get("authority") != "PRC"
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("discover_official_result_articles") is not True
    ):
        raise NeedsReviewError("The event source is not an enabled, owner-authorized PRC result-listing source.")
    if source.get("auto_acquire") is not True:
        raise NeedsReviewError("Automatic acquisition is disabled for this PRC source.")
    if event["exam_code"] != "LICENSURE-EXAM-RESULTS" and source.get("exam_scope") != "all":
        raise NeedsReviewError("The approved PRC source does not cover this examination.")
    if urlsplit(event["article_url"]).hostname.lower() != urlsplit(source["url"]).hostname.lower():
        raise NeedsReviewError("The result article is outside the approved PRC source origin.")

    exam_identity = event["exam_code"]
    if event.get("result_level"):
        exam_identity += f"-{event['result_level'].upper()}"
    specific_exam = f"{exam_identity}-{event['exam_year']}"
    specific = [
        item for item in sources
        if item.get("authority") == "PRC" and item.get("exam") == specific_exam
    ]
    if len(specific) > 1:
        raise NeedsReviewError(f"Multiple source entries match {specific_exam}; owner review is required.")
    if specific:
        exam_source = specific[0]
        if exam_source.get("url") != event["article_url"]:
            raise NeedsReviewError(f"{specific_exam} event article does not match its approved exam-specific source URL.")
        if exam_source.get("enabled") is not True or exam_source.get("auto_acquire") is not True:
            reason = exam_source.get("disable_reason") or "exam-specific automatic acquisition is disabled"
            raise NeedsReviewError(f"{specific_exam} is disabled in the source registry: {reason}")
    return source


class _ApprovedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        try:
            _safe_https_url(new_url, "redirect URL")
        except ValueError as exc:
            raise NeedsReviewError(f"Rejected content redirect: {exc}") from exc
        return super().redirect_request(request, response, code, message, headers, new_url)


def fetch(url: str) -> bytes:
    """Fetch bounded public content, allowing redirects only to approved HTTPS hosts."""
    request = Request(
        url,
        headers={
            "User-Agent": "PH-EXAM-RESULTS-PRC-Ingest/1.0",
            "Accept": "application/pdf,text/csv,application/json,text/html",
        },
    )
    opener = build_opener(_ApprovedRedirectHandler())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=45) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_CONTENT_BYTES:
                    raise NeedsReviewError("Official result content exceeds the 25 MiB acquisition limit.")
                raw = response.read(MAX_CONTENT_BYTES + 1)
                if len(raw) > MAX_CONTENT_BYTES:
                    raise NeedsReviewError("Official result content exceeds the 25 MiB acquisition limit.")
                return raw
        except HTTPError as exc:
            if exc.code in TRANSIENT_HTTP_STATUSES and attempt < 2:
                retry_after = (exc.headers or {}).get("Retry-After", "")
                try:
                    delay = min(10, max(1, int(retry_after)))
                except ValueError:
                    delay = 2 ** (attempt + 1)
                time.sleep(delay)
                continue
            raise NeedsReviewError(f"Official content request returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise NeedsReviewError(f"Official content request failed after 3 attempts: {exc}") from exc
    raise NeedsReviewError("Official content request exhausted its bounded retries.")


def _validate_content_format(raw: bytes, fmt: str) -> None:
    prefix = raw[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    looks_html = prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))
    if fmt == "pdf":
        if looks_html:
            raise NeedsReviewError(
                "The official PDF link returned HTML (likely a sign-in, consent, or access page); no records were extracted."
            )
        if b"%pdf-" not in raw[:1024].lower():
            raise NeedsReviewError("The official PDF link did not return a recognizable PDF document.")
    elif looks_html and fmt != "html":
        raise NeedsReviewError(
            f"The official {fmt} link returned HTML (likely a sign-in, consent, or access page)."
        )
    elif not raw:
        raise NeedsReviewError("The official result content is empty.")


def load_mapping(event: dict, fmt: str, cfg_path: str | Path | None = None):
    path = Path(cfg_path) if cfg_path else HERE / "config" / "adapter_mappings.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NeedsReviewError(f"Unable to read reviewed adapter mappings: {exc}") from exc
    if not isinstance(config, dict):
        raise NeedsReviewError("Reviewed adapter mappings must be a JSON object.")
    return config.get(f"{event['exam_code']}:{event.get('result_level') or '*'}:{fmt}")


def _exam_specific_source(event: dict, sources: list[dict]) -> dict | None:
    identity = event["exam_code"]
    if event.get("result_level"):
        identity += f"-{event['result_level'].upper()}"
    exam = f"{identity}-{event['exam_year']}"
    matches = [
        item for item in sources
        if item.get("authority") == "PRC" and item.get("exam") == exam
    ]
    if len(matches) > 1:
        raise NeedsReviewError(f"Multiple source entries match {exam}; owner review is required.")
    return matches[0] if matches else None


def _approved_public_preview(
    event: dict,
    content_url: str,
    registry_path: str | Path | None,
) -> tuple[dict, dict] | None:
    sources = _read_registry(registry_path)
    source = _exam_specific_source(event, sources)
    if source is None:
        return None
    settings = source.get("public_preview")
    if not isinstance(settings, dict) or settings.get("enabled") is not True:
        return None
    if (
        source.get("authority") != "PRC"
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("auto_acquire") is not True
        or source.get("url") != event["article_url"]
    ):
        raise NeedsReviewError("Exam-specific public-preview source identity or approval does not match the event.")
    if settings.get("method") != "ordinary_public_preview_ui":
        raise NeedsReviewError("Configured public-preview acquisition method is not approved.")
    file_id = _drive_file_id(content_url)
    allowed_ids = source.get("drive_file_ids")
    if not isinstance(allowed_ids, list) or file_id not in allowed_ids:
        raise NeedsReviewError("Drive file ID is not allowlisted for this exam-specific public-preview source.")
    max_pages = settings.get("max_pages")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 400:
        raise NeedsReviewError("Exam-specific public-preview page cap must be between 1 and 400.")
    return source, settings


def _drive_file_id(content_url: str) -> str:
    parsed = urlsplit(content_url)
    match = re.fullmatch(r"/file/d/([A-Za-z0-9_-]+)/view", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "drive.google.com" or not match:
        raise NeedsReviewError("Public preview requires a canonical official Google Drive file URL.")
    return match.group(1)


def capture_public_preview(
    *,
    preview_url: str,
    output_dir: Path,
    settings: dict,
) -> dict:
    """Capture a bounded public viewer through its ordinary visible UI."""
    extractor_dir = HERE / "extractor"
    if str(extractor_dir) not in sys.path:
        sys.path.insert(0, str(extractor_dir))
    try:
        from playwright.sync_api import Error as PlaywrightError
        from public_preview_shards import MAX_SHARDS, capture_shard, merge_shards
    except ImportError as exc:
        raise NeedsReviewError(f"Public-preview browser capture is unavailable: {exc}") from exc

    allowed_hosts = settings.get("allowed_hosts", ["drive.google.com"])
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or any(not isinstance(host, str) or not host for host in allowed_hosts)
    ):
        raise NeedsReviewError("Public-preview mapping has an invalid allowed_hosts list.")
    shard_count = settings.get("shards", 1)
    if isinstance(shard_count, bool) or not isinstance(shard_count, int) or not 1 <= shard_count <= MAX_SHARDS:
        raise NeedsReviewError(f"Public-preview shard count must be an integer between 1 and {MAX_SHARDS}.")
    try:
        for shard in range(shard_count):
            capture_shard(
                preview_url=preview_url,
                shard=shard,
                shard_count=shard_count,
                output_dir=output_dir,
                allowed_hosts={host.lower() for host in allowed_hosts},
                page_control_selector=settings.get("page_control_selector", 'input[aria-label^="Page is"]'),
                page_count_regex=settings.get("page_count_regex", r"Page 1 of\s+(\d+)"),
                page_marker_template=settings.get("page_marker_template", "Page {page} of {count}"),
                per_page_deadline=settings.get("per_page_deadline", 35),
                poll_ms=settings.get("poll_ms", 100),
                max_pages=settings.get("max_pages", 400),
            )
    except PlaywrightError as exc:
        raise NeedsReviewError(f"Public-preview browser capture stopped safely: {exc}") from exc
    return merge_shards(shard_count=shard_count, output_dir=output_dir)


def load_public_preview_mapping(
    event: dict,
    cfg_path: str | Path | None = None,
) -> tuple[str, dict] | None:
    path = Path(cfg_path) if cfg_path else HERE / "config" / "adapter_mappings.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NeedsReviewError(f"Unable to read reviewed public-preview mappings: {exc}") from exc
    if not isinstance(config, dict):
        raise NeedsReviewError("Reviewed adapter mappings must be a JSON object.")
    identity = event["exam_code"]
    if event.get("result_level"):
        identity += f":{event['result_level']}"
    key = f"{identity}:{event['exam_year']}:public_preview"
    mapping = config.get(key)
    return (key, mapping) if mapping is not None else None


def _extract_pdf_text_evidence(raw: bytes, output: Path) -> tuple[dict, bool]:
    """Preserve raw per-page PDF text/tables and report genuine text availability."""
    extractor_dir = HERE / "extractor"
    if str(extractor_dir) not in sys.path:
        sys.path.insert(0, str(extractor_dir))
    try:
        from pdf_parser import extract_pdf
        pdf_path = output / "official-source.pdf"
        pdf_path.write_bytes(raw)
        extraction = extract_pdf(pdf_path)
    except Exception as exc:
        raise NeedsReviewError(f"PDF extraction failed during Tier 1 text inspection; human review is required: {exc}") from exc

    extraction_path = output / "pdf-text-extraction.json"
    extraction_path.write_text(
        json.dumps(extraction, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    has_text = False
    for page in extraction.get("pages", []):
        if isinstance(page.get("text"), str) and page["text"].strip():
            has_text = True
            break
        for table in page.get("tables", []):
            if any(
                isinstance(cell, str) and cell.strip()
                for row in (table or [])
                for cell in (row or [])
            ):
                has_text = True
                break
        if has_text:
            break
    evidence = {
        "status": "available" if has_text else "unavailable",
        "reason": (
            "PDF text or table-cell content was extracted."
            if has_text else
            "Every PDF page was inspected; no extractable text or table-cell content exists."
        ),
        "page_count": extraction.get("page_count"),
        "extraction_path": extraction_path.as_posix(),
        "extraction_sha256": hashlib.sha256(extraction_path.read_bytes()).hexdigest(),
        "pdf_sha256": extraction.get("source_file_sha256"),
    }
    return evidence, has_text


def _write_tier_failure_evidence(
    *,
    output: Path,
    source_url: str,
    tier1: dict,
    tier2: dict,
) -> Path:
    evidence = {
        "schema_version": 1,
        "source_url": source_url,
        "access_challenge_detected": False,
        "tier1_direct_text": tier1,
        "tier2_rendered_dom": tier2,
    }
    path = output / "tier-failures.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _preview_has_rendered_text(snapshots: list[dict]) -> bool:
    """Treat only blank snapshots/page counters as unavailable DOM text."""
    for snapshot in snapshots:
        value = snapshot.get("text")
        if not isinstance(value, str):
            continue
        without_page_marker = re.sub(
            r"(?im)^\s*page\s+\d+\s+of\s+\d+\s*$", "", value
        )
        if without_page_marker.strip():
            return True
    return False


def _load_tier3_mapping_key(source: dict, event: dict) -> str | None:
    path = HERE / "config" / "static_png_ocr_mappings.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NeedsReviewError(f"Unable to read Tier 3 OCR mapping registry: {exc}") from exc
    mappings = config.get("mappings") if isinstance(config, dict) else None
    if not isinstance(config, dict) or config.get("schema_version") != 1 or not isinstance(mappings, dict):
        raise NeedsReviewError("Tier 3 OCR mapping registry has an invalid schema.")
    exam = event["exam_code"] + (
        f"-{event['result_level'].upper()}" if event.get("result_level") else ""
    )
    matches = [
        key for key, mapping in mappings.items()
        if isinstance(mapping, dict)
        and mapping.get("enabled") is True
        and mapping.get("source_id") == source.get("id")
        and mapping.get("authority") == "PRC"
        and mapping.get("exam") == exam
        and mapping.get("year") == event["exam_year"]
        and mapping.get("official_source_url") == source.get("url")
    ]
    if len(matches) > 1:
        raise NeedsReviewError("Multiple Tier 3 OCR mappings match this source/exam; Owner review is required.")
    return matches[0] if matches else None


def _repository_relative(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as exc:
        raise NeedsReviewError("Public-preview evidence must remain inside the repository workspace.") from exc


def _write_public_preview_bundle(
    *,
    event: dict,
    content_url: str,
    preview_url: str,
    source: dict,
    mapping_key: str,
    mapping: dict,
    capture_dir: Path,
    capture_manifest: dict,
    repository_root: Path,
) -> tuple[Path, dict]:
    try:
        snapshots = [
            json.loads(line)
            for line in (capture_dir / "page-text-snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NeedsReviewError(f"Cannot read merged public-preview text snapshots: {exc}") from exc
    if not snapshots or any(not isinstance(item.get("text"), str) for item in snapshots):
        raise NeedsReviewError("Public-preview capture did not retain rendered text for every viewer page.")

    try:
        records = parse_public_preview_snapshots(snapshots, mapping)
    except PublicPreviewCaptureError as exc:
        raise NeedsReviewError(f"Public-preview extraction stopped safely: {exc}") from exc
    score, failures = greenlight(records, event["announced_count"])
    if score != 100:
        raise NeedsReviewError("Public-preview Greenlight failed: " + "; ".join(failures))

    records_path = capture_dir / "records.jsonl"
    records_path.write_text("".join(
        json.dumps({"seq": str(sequence), "name": name}, ensure_ascii=False) + "\n"
        for sequence, name in records
    ), encoding="utf-8")
    record_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()
    mapping_hash = hashlib.sha256(
        json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    extraction = {
        "candidate_complete": True,
        "provenance": "official_direct",
        "mapping_key": mapping_key,
        "mapping_sha256": mapping_hash,
        "announced_count": event["announced_count"],
        "extracted_records": len(records),
        "sequence_coverage_complete": True,
        "duplicate_sequence_count": 0,
        "duplicate_name_count": 0,
        "records_jsonl_sha256": record_hash,
    }
    extraction_path = capture_dir / "extraction-report.json"
    extraction_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if capture_manifest.get("viewer_pages_captured") != capture_manifest.get("viewer_pages_expected"):
        raise NeedsReviewError("Public-preview capture did not complete every expected viewer page.")
    if capture_manifest.get("page_coverage_complete") is not True:
        raise NeedsReviewError("Public-preview capture does not prove complete page coverage.")
    capture_manifest = dict(capture_manifest)
    capture_manifest.update({
        "provenance": "official_direct",
        "public_preview_only": True,
        "official_article_url": event["article_url"],
        "official_content_url": content_url,
        "public_preview_url": preview_url,
        "viewer_pages_navigated": capture_manifest.get("viewer_pages_captured"),
    })
    screenshot_entries = capture_manifest.get("files", {}).get("screenshots")
    if not isinstance(screenshot_entries, list):
        raise NeedsReviewError("Capture did not retain per-page screenshot evidence.")
    for item in screenshot_entries:
        item["path"] = _repository_relative(capture_dir / item["path"], repository_root)
    capture_manifest_path = capture_dir / "viewer-capture-manifest.json"
    capture_manifest_path.write_text(
        json.dumps(capture_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = capture_dir / "source-manifest.json"
    files = {
        "page_capture_index": capture_dir / "page-capture-index.json",
        "page_text_snapshots": capture_dir / "page-text-snapshots.jsonl",
        "records_jsonl": records_path,
        "extraction_report": extraction_path,
        "viewer_capture_manifest": capture_manifest_path,
    }
    source_manifest = {
        "schema_version": 2,
        "provenance": "official_direct",
        "capture_method": "ordinary_public_preview_ui",
        "public_preview_only": True,
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "official_article_url": event["article_url"],
        "official_content_url": content_url,
        "public_preview_url": preview_url,
        "viewer_pages_expected": capture_manifest["viewer_pages_expected"],
        "viewer_pages_navigated": capture_manifest["viewer_pages_navigated"],
        "page_coverage_complete": capture_manifest["page_coverage_complete"],
        "source_id": source["id"],
        "files": {
            key: {
                "path": _repository_relative(path, repository_root),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for key, path in files.items()
        },
    }
    manifest_path.write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path, {
        "records": records,
        "greenlight": score,
        "mapping_hash": mapping_hash,
        "records_hash": record_hash,
        "viewer_pages": capture_manifest["viewer_pages_expected"],
    }


def greenlight(records: list[tuple[int, str]], announced: int) -> tuple[int, list[str]]:
    failures: list[str] = []
    valid_records = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, (tuple, list)) or len(record) != 2:
            failures.append(f"invalid record shape at record {index}")
            continue
        valid_records.append((record[0], record[1]))
    sequences = []
    for index, (sequence, _name) in enumerate(valid_records, start=1):
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            failures.append(f"invalid sequence number at record {index}")
        else:
            sequences.append(sequence)
    if not records:
        failures.append("no records")
    if len(valid_records) != announced:
        failures.append(f"record count {len(valid_records)} does not match announced count {announced}")
    if len(set(sequences)) != len(sequences):
        failures.append("duplicate sequence numbers")
    if sorted(sequences) != list(range(1, announced + 1)):
        failures.append("sequence numbers do not cover exactly 1 through the announced count")

    seen_names: set[str] = set()
    for index, (sequence, name) in enumerate(valid_records, start=1):
        if not isinstance(name, str) or not name.strip():
            failures.append(f"blank name at record {index}")
            continue
        if "\ufffd" in name:
            failures.append(f"replacement character in name at record {index}")
        if any(not (character.isspace() or unicodedata.category(character)[0] in {"L", "M", "N", "P", "Z"}) for character in name):
            failures.append(f"unexpected character in name at record {index}")
        normalized = " ".join(name.split()).casefold()
        if normalized in seen_names:
            failures.append(f"duplicate name at record {index}")
        seen_names.add(normalized)
    return (100 if not failures else 0), failures



def run(
    event: object,
    output_dir: str | Path,
    *,
    fetcher=fetch,
    preview_verifier=verify_official_preview_link,
    preview_capturer=capture_public_preview,
    cfg_path: str | Path | None = None,
    registry_path: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> int:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repository_root or Path.cwd()).resolve()
    report: dict = {"published": False, "status": "started"}
    run_identity = os.getenv("GITHUB_RUN_ID") or str(time.time_ns())
    execution_id = "prc-orchestrator:" + run_identity
    started_at = time.perf_counter()
    record_activity({
        "event_id": execution_id + ":started", "execution_id": execution_id,
        "component": "Python Engine", "operation": "prc_release_acquisition",
        "status": "running", "message": "PRC release acquisition and extraction started.",
        "source": "python_engine",
    })

    def finish(status: str, code: int, **fields) -> int:
        report.update(status=status, **fields)
        (output / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        outcome = "success" if code == 0 else ("blocked" if status == "needs_review" else "failed")
        record_activity({
            "event_id": execution_id + ":finished", "execution_id": execution_id,
            "component": "Python Engine", "operation": "prc_release_acquisition",
            "status": outcome, "severity": "error" if outcome == "failed" else ("warning" if outcome == "blocked" else "info"),
            "duration_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            "message": "PRC release acquisition finished: " + status + ".",
            "error_code": "PRC_ACQUISITION_STOPPED" if outcome != "success" else None,
            "error_message": str(fields.get("reason") or "; ".join(fields.get("errors", [])))[:1000] if outcome != "success" else None,
            "source": "python_engine",
            "metadata": {"source_id": event.get("source_id", ""), "authority": "PRC", "exam": event.get("exam_code", "")}
        })
        return code

    errors = validate_event(event)
    if errors:
        return finish("invalid_event", 2, errors=errors)
    report["event"] = event
    try:
        source = _approved_source(event, registry_path)
    except NeedsReviewError as exc:
        return finish("needs_review", 3, reason=str(exc))

    content_urls = event["content_urls"]
    if len(content_urls) != 1:
        return finish("needs_review", 3, reason="multiple official content links; automatic selection is not safe")
    content = content_urls[0]
    if content["format"] != "pdf":
        return finish("needs_review", 3, reason=f"the current three-tier PRC route accepts PDF sources only, not {content['format']}")

    try:
        preview_approval = _approved_public_preview(event, content["url"], registry_path)
    except (NeedsReviewError, ValueError) as exc:
        return finish("needs_review", 3, reason=str(exc), source=content["url"])

    specific_source = preview_approval[0] if preview_approval is not None else None
    settings = preview_approval[1] if preview_approval is not None else None
    if preview_approval is not None:
        try:
            preview_verifier(
                source=specific_source,
                article_url=event["article_url"],
                content_url=content["url"],
                evidence_path=output / "official-content-evidence.json",
            )
        except (OfficialContentError, RuntimeError, OSError, ValueError) as exc:
            return finish("needs_review", 3, reason=f"Official article/link verification stopped safely: {exc}", source=content["url"])

    # Tier 1: acquire the official PDF and preserve raw text/table evidence.
    try:
        raw = fetcher(content["url"])
        if not isinstance(raw, bytes):
            raise NeedsReviewError("Content fetcher did not return bytes.")
        _validate_content_format(raw, "pdf")
        tier1, tier1_available = _extract_pdf_text_evidence(raw, output)
    except NeedsReviewError as exc:
        return finish("needs_review", 3, reason=str(exc), source=content["url"])
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return finish("needs_review", 3, reason=f"Tier 1 official PDF acquisition failed safely: {exc}", source=content["url"])

    if tier1_available:
        # Readable PDF content is not an extraction failure. Missing mappings or
        # parser/integrity errors stop here rather than activating Tier 2/OCR.
        try:
            mapping = load_mapping(event, "pdf", cfg_path)
        except NeedsReviewError as exc:
            return finish("needs_review", 3, reason=str(exc), source=content["url"], tier1=tier1)
        if mapping is None:
            return finish(
                "needs_review", 3,
                reason=f"Tier 1 extracted readable PDF content, but no reviewed PDF mapping exists for {event['exam_code']}/{event.get('result_level') or '*'}. Tier 2 is not a parser-error fallback.",
                source=content["url"], tier1=tier1,
            )
        if not isinstance(mapping, dict):
            return finish("needs_review", 3, reason="reviewed PDF mapping must be a JSON object", source=content["url"], tier1=tier1)
        try:
            records = REGISTRY["pdf"](raw, mapping)
        except NeedsReview as exc:
            return finish("needs_review", 3, reason=f"Tier 1 PDF mapping/parser requires human review: {exc}", source=content["url"], tier1=tier1)
        except (UnicodeError, ValueError, TypeError, KeyError) as exc:
            return finish("needs_review", 3, reason=f"Tier 1 PDF parsing stopped safely: {exc}", source=content["url"], tier1=tier1)

        score, failures = greenlight(records, event["announced_count"])
        if score != 100:
            return finish("needs_review", 3, reason="Tier 1 PDF Greenlight failed; later tiers are not parser-error fallbacks.", failures=failures, source=content["url"], tier1=tier1)

        pdf_path = output / "official-source.pdf"
        batch = {
            "authority": "PRC",
            "exam": event["exam_code"] + (
                f"-{event['result_level'].upper()}" if event.get("result_level") else ""
            ),
            "level": event.get("result_level"),
            "year": event["exam_year"],
            "source_id": source["id"],
            "official_source_url": source["url"],
            "official_article_url": event["article_url"],
            "official_document_url": content["url"],
            "announced_count": event["announced_count"],
            "publicly_released": True,
            "provenance": "official_direct",
            "official_content_mode": "pdf_text_extraction",
            "source_pdf": pdf_path.as_posix(),
            "source_pdf_sha256": hashlib.sha256(raw).hexdigest(),
            "records": [
                {"sequence_number": str(sequence), "name": name}
                for sequence, name in records
            ],
            "record_mapping_reviewed": True,
        }
        batch_path = output / "release-batch.json"
        batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return finish(
            "ready_for_greenlight_pipeline", 0,
            batch=batch_path.as_posix(), records=len(records), greenlight=score,
            mapping_reviewed=True, acquisition_method="official_pdf_text",
            tier1=tier1,
        )

    # Tier 2 is eligible only after every PDF page has been inspected and no
    # extractable text or table-cell content was found.
    if preview_approval is None:
        return finish(
            "needs_review", 3,
            reason="Tier 1 PDF text is genuinely unavailable, but no approved ordinary public-preview route exists for Tier 2.",
            source=content["url"], tier1=tier1,
        )

    preview_url = urlsplit(content["url"])._replace(
        path=urlsplit(content["url"]).path.rsplit("/", 1)[0] + "/preview",
        query="", fragment="",
    ).geturl()
    capture_dir = output / "public-preview-capture"
    try:
        capture_manifest = preview_capturer(
            preview_url=preview_url, output_dir=capture_dir, settings=settings,
        )
        snapshots = [
            json.loads(line)
            for line in (capture_dir / "page-text-snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (PublicPreviewCaptureError, NeedsReviewError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        return finish("needs_review", 3, reason=f"Tier 2 ordinary public-preview capture stopped safely: {exc}", source=content["url"], tier1=tier1)

    if (
        capture_manifest.get("viewer_pages_captured") != capture_manifest.get("viewer_pages_expected")
        or capture_manifest.get("page_coverage_complete") is not True
        or not snapshots
        or len(snapshots) != capture_manifest.get("viewer_pages_expected")
    ):
        return finish("needs_review", 3, reason="Tier 2 capture lacks complete page coverage; OCR is not authorized.", source=content["url"], tier1=tier1)

    tier2_available = _preview_has_rendered_text(snapshots)
    if tier2_available:
        try:
            mapping_result = load_public_preview_mapping(event, cfg_path)
        except NeedsReviewError as exc:
            return finish("needs_review", 3, reason=str(exc), source=content["url"], tier1=tier1, tier2={"status": "available"})
        if mapping_result is None:
            return finish(
                "needs_review", 3,
                reason=f"Tier 2 rendered readable DOM text, but no reviewed public-preview mapping exists for {event['exam_code']}/{event['exam_year']}. OCR is not a mapping-error fallback.",
                source=content["url"], tier1=tier1, tier2={"status": "available"},
            )
        mapping_key, mapping = mapping_result
        if not isinstance(mapping, dict):
            return finish("needs_review", 3, reason="reviewed public-preview mapping must be a JSON object", source=content["url"], tier1=tier1, tier2={"status": "available"})
        try:
            manifest_path, extracted = _write_public_preview_bundle(
                event=event, content_url=content["url"], preview_url=preview_url,
                source=specific_source, mapping_key=mapping_key, mapping=mapping,
                capture_dir=capture_dir, capture_manifest=capture_manifest,
                repository_root=repo_root,
            )
        except (PublicPreviewCaptureError, NeedsReviewError, RuntimeError, OSError, ValueError) as exc:
            return finish(
                "needs_review", 3,
                reason=f"Tier 2 readable DOM text could not be parsed/validated; later OCR fallback is forbidden: {exc}",
                source=content["url"], tier1=tier1, tier2={"status": "available"},
            )

        exam_identity = event["exam_code"] + (
            f"-{event['result_level'].upper()}" if event.get("result_level") else ""
        )
        batch = {
            "authority": "PRC", "exam": exam_identity,
            "level": event.get("result_level"), "year": event["exam_year"],
            "source_id": source["id"], "exam_specific_source_id": specific_source["id"],
            "official_source_url": source["url"], "official_article_url": event["article_url"],
            "official_content_url": content["url"], "public_preview_url": preview_url,
            "official_content_mode": "public_preview_capture",
            "capture_manifest": _repository_relative(manifest_path, repo_root),
            "public_preview_mapping_key": mapping_key,
            "announced_count": event["announced_count"],
            "publicly_released": True, "provenance": "official_direct",
        }
        batch_path = output / "release-batch.json"
        batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return finish(
            "ready_for_greenlight_pipeline", 0,
            batch=batch_path.as_posix(), records=len(extracted["records"]),
            greenlight=extracted["greenlight"], mapping_reviewed=True,
            acquisition_method="ordinary_public_preview_ui",
            viewer_pages=extracted["viewer_pages"],
            capture_manifest=_repository_relative(manifest_path, repo_root),
            tier1=tier1, tier2={"status": "available"},
        )

    tier2 = {
        "status": "unavailable",
        "reason": "Every captured viewer page was inspected; snapshots contain only blank text or page counters.",
    }
    tier_failure_path = _write_tier_failure_evidence(
        output=output, source_url=specific_source["url"], tier1=tier1, tier2=tier2,
    )
    try:
        mapping_key = _load_tier3_mapping_key(specific_source, event)
    except NeedsReviewError as exc:
        return finish("needs_review", 3, reason=str(exc), source=content["url"], tier1=tier1, tier2=tier2)
    if mapping_key is None:
        return finish(
            "needs_review", 3,
            reason="Tier 1 and Tier 2 text are genuinely unavailable, but Tier 3 remains disabled: no Owner-reviewed source/exam OCR mapping with access-directives and reuse-terms reviews exists.",
            source=content["url"], tier1=tier1, tier2=tier2,
            tier_failure_evidence=_repository_relative(tier_failure_path, repo_root),
        )

    raw_capture_manifest_path = capture_dir / "capture-manifest.json"
    try:
        raw_capture_manifest = json.loads(raw_capture_manifest_path.read_text(encoding="utf-8"))
        screenshot_entries = raw_capture_manifest.get("files", {}).get("screenshots")
        if not isinstance(screenshot_entries, list) or len(screenshot_entries) != capture_manifest.get("viewer_pages_expected"):
            raise NeedsReviewError("Tier 2 capture did not retain one screenshot for every viewer page.")
        ocr_manifest = {
            "schema_version": 1,
            "capture_method": "ordinary_public_preview_ui",
            "source_url": preview_url,
            "official_content_url": content["url"],
            "public_preview_url": preview_url,
            "stable_viewport": True,
            "lossless_png": True,
            "access_challenge_detected": False,
            "screenshots": [
                {
                    "page": item["viewer_page"],
                    "path": _repository_relative(capture_dir / item["path"], repo_root),
                    "sha256": item["sha256"],
                }
                for item in screenshot_entries
            ],
        }
        ocr_manifest_path = capture_dir / "static-png-ocr-manifest.json"
        ocr_manifest_path.write_text(json.dumps(ocr_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, NeedsReviewError) as exc:
        return finish("needs_review", 3, reason=f"Tier 3 screenshot evidence could not be prepared safely: {exc}", source=content["url"], tier1=tier1, tier2=tier2)

    exam_identity = event["exam_code"] + (
        f"-{event['result_level'].upper()}" if event.get("result_level") else ""
    )
    batch = {
        "authority": "PRC", "exam": exam_identity,
        "level": event.get("result_level"), "year": event["exam_year"],
        "source_id": specific_source["id"], "official_source_url": specific_source["url"],
        "official_article_url": event["article_url"], "official_content_url": content["url"],
        "public_preview_url": preview_url, "official_content_mode": "static_png_ocr",
        "static_png_ocr_mapping_key": mapping_key,
        "static_png_ocr_manifest": _repository_relative(ocr_manifest_path, repo_root),
        "tier_failure_evidence": _repository_relative(tier_failure_path, repo_root),
        "announced_count": event["announced_count"], "publicly_released": True,
        "provenance": "official_direct", "access_challenge_detected": False,
    }
    batch_path = output / "release-batch.json"
    batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return finish(
        "ready_for_greenlight_pipeline", 0, batch=batch_path.as_posix(),
        acquisition_method="reviewed_static_png_ocr",
        tier1=tier1, tier2=tier2,
        tier_failure_evidence=_repository_relative(tier_failure_path, repo_root),
    )

def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire and validate a detected official PRC result.")
    parser.add_argument("--event", required=True, help="Path to a PRC release event JSON object.")
    parser.add_argument("--out", default="prc-release-output", help="Output directory for status and batch artifacts.")
    parser.add_argument("--source-registry", help="Optional source registry path.")
    parser.add_argument("--adapter-mappings", help="Optional reviewed adapter mapping path.")
    args = parser.parse_args()
    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"PRC PROCESSING STOPPED: cannot read event: {exc}", file=sys.stderr)
        return 2
    result = run(
        event,
        args.out,
        cfg_path=args.adapter_mappings,
        registry_path=args.source_registry,
    )
    report_path = Path(args.out) / "report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"PRC PROCESSING STOPPED: unable to read processing report: {exc}", file=sys.stderr)
        return 2
    if result:
        print(f"PRC PROCESSING STOPPED: {report.get('reason') or report.get('errors')}", file=sys.stderr)
    else:
        print(f"PRC PROCESSING READY: {report['records']} records passed ingestion Greenlight.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
