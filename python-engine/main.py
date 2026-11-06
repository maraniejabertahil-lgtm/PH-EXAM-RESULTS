"""Python processing-to-GitOps entry point for pre-structured result batches.

The PDF parser deliberately remains raw-only. This pipeline therefore accepts
an explicitly reviewed records JSON file; it does not infer table columns or
pretend that raw PDF text has been normalized automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from acquisition.official_first_policy import third_party_fallback_gate
from acquisition.official_pdf import AcquisitionError, acquire_official_pdf
from acquisition.official_content import (
    OfficialContentError,
    verify_official_content_link,
    verify_official_preview_link,
)
from acquisition.public_preview import PublicPreviewCaptureError, load_public_preview_capture
from extractor.pdf_parser import extract_pdf
from processor.greenlight import validate_records, write_validation_report
from publication_policy import PublicationPolicyError, requires_owner_visual_review
from processor.normalizer import NormalizationError, normalize_extracted_tables
from publisher.gitops_manager import GitHubGitOps, GitOpsError
from publisher.json_builder import build_dataset
from database.activity import read_validation_report, record_pipeline_event


class PipelineError(RuntimeError):
    """Raised when a batch cannot safely proceed to publication."""


def _repo_path(value: str, root: Path) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise PipelineError("Input paths must remain inside the checked-out repository.") from exc
    if not candidate.is_file():
        raise PipelineError(f"Required input file does not exist: {value}")
    return candidate


def _https_url(value: Any, field: str) -> str:
    from urllib.parse import urlsplit

    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{field} is required.")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PipelineError(f"{field} must be a credential-free HTTPS URL.")
    return value


def _approved_source(batch: dict[str, Any], root: Path) -> dict[str, Any]:
    registry_path = root / "python-engine" / "config" / "sources.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read approved source registry: {exc}") from exc
    sources = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(sources, list):
        raise PipelineError("Approved source registry has an invalid schema.")
    matches = [
        item for item in sources
        if isinstance(item, dict) and item.get("id") == batch.get("source_id")
    ]
    if len(matches) != 1:
        raise PipelineError("source_id must match exactly one approved registry entry.")
    source = matches[0]
    exam_matches = source.get("exam") == batch.get("exam") or (
        source.get("source_type") == "official"
        and source.get("exam_scope") == "all"
    )
    if (
        source.get("enabled") is not True
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("authority") != batch.get("authority")
        or not exam_matches
    ):
        raise PipelineError("Batch identity does not match an enabled, authorized official source.")
    if batch.get("official_source_url") != source.get("url"):
        raise PipelineError("official_source_url must exactly match the approved registry URL.")
    return source


def _approved_public_preview_source(
    batch: dict[str, Any],
    *,
    root: Path,
    exam_listing_source: dict[str, Any],
) -> dict[str, Any]:
    specific_id = batch.get("exam_specific_source_id")
    if not isinstance(specific_id, str) or not specific_id:
        raise PipelineError("Public-preview capture requires an exam-specific approved source ID.")
    registry_path = root / "python-engine" / "config" / "sources.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read approved source registry: {exc}") from exc
    sources = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(sources, list):
        raise PipelineError("Approved source registry has an invalid schema.")
    matches = [
        item for item in sources
        if isinstance(item, dict) and item.get("id") == specific_id
    ]
    if len(matches) != 1:
        raise PipelineError("exam_specific_source_id must match exactly one approved registry entry.")
    source = matches[0]
    preview_settings = source.get("public_preview")
    expected_exam = f"{batch.get('exam')}-{batch.get('year')}"
    if (
        source.get("authority") != "PRC"
        or source.get("exam") != expected_exam
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("enabled") is not True
        or source.get("auto_acquire") is not True
        or source.get("url") != batch.get("official_article_url")
        or source.get("allow_linked_drive_documents") is not True
        or not isinstance(preview_settings, dict)
        or preview_settings.get("enabled") is not True
        or preview_settings.get("method") != "ordinary_public_preview_ui"
        or isinstance(preview_settings.get("max_pages"), bool)
        or not isinstance(preview_settings.get("max_pages"), int)
        or not 1 <= preview_settings["max_pages"] <= 400
        or batch.get("source_id") != exam_listing_source.get("id")
    ):
        raise PipelineError("Batch does not match an enabled exam-specific public-preview source.")
    from urllib.parse import urlsplit

    content_url = _https_url(batch.get("official_content_url"), "official_content_url")
    parsed = urlsplit(content_url)
    match = re.fullmatch(r"/file/d/([A-Za-z0-9_-]+)/view", parsed.path)
    if (
        parsed.hostname != "drive.google.com"
        or match is None
        or not isinstance(source.get("drive_file_ids"), list)
        or match.group(1) not in source["drive_file_ids"]
    ):
        raise PipelineError("Official Drive file ID is not allowlisted for this examination.")
    return source


def process_batch(batch_path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Validate a reviewed batch and build local, non-published dataset artifacts."""
    repository_root = Path(root or Path.cwd()).resolve()
    input_path = _repo_path(str(batch_path), repository_root)
    try:
        batch = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Unable to read batch JSON: {exc}") from exc
    if not isinstance(batch, dict):
        raise PipelineError("Batch input must be a JSON object.")

    required = ("authority", "exam", "year", "announced_count", "provenance", "publicly_released")
    missing = [key for key in required if key not in batch]
    if missing:
        raise PipelineError("Batch is missing required fields: " + ", ".join(missing))

    if batch.get("publicly_released") is not True:
        raise PipelineError("Only publicly released examination results may enter the publication pipeline.")

    provenance = batch["provenance"]
    if provenance == "official_direct":
        source = _approved_source(batch, repository_root)
        _https_url(batch.get("official_source_url"), "official_source_url")
        content_mode = batch.get("official_content_mode")
        if content_mode == "manual_handoff":
            article_url = _https_url(batch.get("official_article_url"), "official_article_url")
            document_url = _https_url(batch.get("official_content_url"), "official_content_url")
            if batch.get("official_content_reviewed") is not True:
                raise PipelineError("Manual official-content handoff requires official_content_reviewed=true.")
            if batch.get("record_mapping_reviewed") is not True:
                raise PipelineError("Manual official-content handoff requires record_mapping_reviewed=true.")
            if not isinstance(batch.get("records"), list):
                raise PipelineError("Manual official-content handoff requires reviewed name/sequence records.")
            evidence_path = repository_root / "python-engine" / "artifacts" / "official-content-evidence.json"
            try:
                verify_official_content_link(
                    source=source,
                    article_url=article_url,
                    content_url=document_url,
                    evidence_path=evidence_path,
                )
            except OfficialContentError as exc:
                raise PipelineError(f"Official content handoff stopped safely: {exc}") from exc
            acquisition_log_path = str(evidence_path.relative_to(repository_root))
            source_pdf_sha256 = None
            normalized_records = batch["records"]
        elif content_mode == "public_preview_capture":
            article_url = _https_url(batch.get("official_article_url"), "official_article_url")
            document_url = _https_url(batch.get("official_content_url"), "official_content_url")
            preview_url = _https_url(batch.get("public_preview_url"), "public_preview_url")
            manifest_input = _repo_path(batch.get("capture_manifest", ""), repository_root)
            try:
                manifest_header = json.loads(manifest_input.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PipelineError(f"Unable to read public-preview capture manifest: {exc}") from exc
            manifest_schema = manifest_header.get("schema_version") if isinstance(manifest_header, dict) else None
            evidence_path = repository_root / "python-engine" / "artifacts" / "official-content-evidence.json"
            try:
                if manifest_schema == 1:
                    verify_official_content_link(
                        source=source,
                        article_url=article_url,
                        content_url=document_url,
                        evidence_path=evidence_path,
                    )
                elif manifest_schema == 2:
                    preview_source = _approved_public_preview_source(
                        batch,
                        root=repository_root,
                        exam_listing_source=source,
                    )
                    verify_official_preview_link(
                        source=preview_source,
                        article_url=article_url,
                        content_url=document_url,
                        evidence_path=evidence_path,
                    )
                else:
                    raise PipelineError("Unsupported public-preview capture manifest schema.")
                normalized_records, capture_evidence = load_public_preview_capture(
                    batch=batch, root=repository_root
                )
            except (OfficialContentError, PublicPreviewCaptureError) as exc:
                raise PipelineError(f"Official public-preview capture stopped safely: {exc}") from exc
            if (
                manifest_schema == 2
                and capture_evidence["viewer_pages"] > preview_source["public_preview"]["max_pages"]
            ):
                raise PipelineError("Captured viewer page count exceeds the exam-specific approved page cap.")
            acquisition_log_path = batch.get("capture_manifest")
            source_pdf_sha256 = None
        else:
            document_url = _https_url(batch.get("official_document_url"), "official_document_url")
            from urllib.parse import urlsplit
            document_host = urlsplit(document_url).hostname.lower()
            approved_host = urlsplit(source["url"]).hostname.lower()
            if document_host != approved_host and not (
                document_host == "drive.google.com" and source.get("allow_linked_drive_documents") is True
            ):
                raise PipelineError("Official document URL is outside the approved source origin or allowed Drive links.")
            if isinstance(batch.get("source_pdf"), str) and batch["source_pdf"].strip():
                pdf_path = _repo_path(batch["source_pdf"], repository_root)
                acquisition_log_path = None
            else:
                article_url = _https_url(batch.get("official_article_url"), "official_article_url")
                acquired = acquire_official_pdf(
                    source=source,
                    article_url=article_url,
                    document_url=document_url,
                    output_path=repository_root / "python-engine" / "artifacts" / "official-source.pdf",
                    attempt_log_path=repository_root / "python-engine" / "artifacts" / "official-attempt-log.json",
                )
                pdf_path = Path(acquired["path"])
                acquisition_log_path = acquired["attempt_log_path"]
            extraction = extract_pdf(pdf_path)
            expected_hash = batch.get("source_pdf_sha256")
            if expected_hash and expected_hash != extraction["source_file_sha256"]:
                raise PipelineError("Source PDF SHA-256 does not match the batch metadata.")
            source_pdf_sha256 = extraction["source_file_sha256"]
            if isinstance(batch.get("records"), list):
                if batch.get("record_mapping_reviewed") is not True:
                    raise PipelineError("Pre-normalized official records require record_mapping_reviewed=true.")
                normalized_records = batch["records"]
            elif isinstance(batch.get("table_mapping"), dict):
                if batch.get("table_mapping_reviewed") is not True:
                    raise PipelineError("PDF table mappings require table_mapping_reviewed=true.")
                try:
                    normalized_records = normalize_extracted_tables(extraction, batch["table_mapping"])
                except NormalizationError as exc:
                    raise PipelineError(f"PDF table normalization stopped safely: {exc}") from exc
            else:
                raise PipelineError("Provide reviewed records or an explicitly reviewed table_mapping.")
    elif provenance == "third_party_fallback":
        source = _approved_source(batch, repository_root)
        attempt_log = _repo_path(batch.get("official_attempt_log", ""), repository_root)
        gate = third_party_fallback_gate(attempt_log)
        if gate.get("allowed") is not True:
            raise PipelineError("Third-party fallback is not authorized: " + gate.get("reason", "unknown"))
        evidence = json.loads(attempt_log.read_text(encoding="utf-8"))
        if (
            evidence.get("source_id") != source.get("id")
            or evidence.get("authority") != batch.get("authority")
            or evidence.get("exam") != batch.get("exam")
            or evidence.get("official_source_url") != source.get("url")
        ):
            raise PipelineError("Official-attempt evidence does not match this approved source and examination.")
        source_a_url = _https_url(batch.get("source_a_url"), "source_a_url")
        source_b_url = _https_url(batch.get("source_b_url"), "source_b_url")
        from urllib.parse import urlsplit
        if (
            source_a_url == source_b_url
            or urlsplit(source_a_url).hostname.lower() == urlsplit(source_b_url).hostname.lower()
        ):
            raise PipelineError("Fallback sources must be independently hosted, distinct HTTPS sources.")
        source_pdf_sha256 = None
        normalized_records = batch.get("records")
        if not isinstance(normalized_records, list):
            raise PipelineError("Fallback batches require normalized records from source A.")
    else:
        raise PipelineError("provenance must be official_direct or third_party_fallback.")

    records = normalized_records
    report = validate_records(
        records,
        announced_count=batch["announced_count"],
        provenance=provenance,
        comparison_records=batch.get("comparison_records"),
        source_a_id=batch.get("source_a_id"),
        source_b_id=batch.get("source_b_id"),
    )
    report["source_id"] = batch.get("source_id")
    report["official_source_url"] = batch.get("official_source_url")
    report["official_document_url"] = batch.get("official_document_url") or batch.get("official_content_url")
    report["official_content_mode"] = batch.get("official_content_mode")
    report["source_pdf_sha256"] = source_pdf_sha256
    report["official_article_url"] = batch.get("official_article_url")
    report["official_attempt_log"] = acquisition_log_path if provenance == "official_direct" else batch.get("official_attempt_log")
    if provenance == "official_direct" and batch.get("official_content_mode") == "public_preview_capture":
        report["public_preview_capture"] = capture_evidence
    report["source_a_url"] = batch.get("source_a_url") if provenance == "third_party_fallback" else None
    report["source_b_url"] = batch.get("source_b_url") if provenance == "third_party_fallback" else None

    report_path = repository_root / "python-engine" / "artifacts" / "validation-report.json"
    write_validation_report(report, report_path)
    if report["publication_allowed"] is not True or report["greenlight_score"] != 100:
        raise PipelineError(
            f"Greenlight rejected this batch (score {report['greenlight_score']}/100); no dataset PR was created. "
            f"See {report_path.relative_to(repository_root)}."
        )

    output_dir = repository_root / "python-engine" / "artifacts" / "dataset"
    manifest = build_dataset(
        records,
        authority=batch["authority"],
        exam=batch["exam"],
        year=batch["year"],
        output_dir=output_dir,
        greenlight_report=report,
        provenance=provenance,
    )
    return {
        "report": report,
        "report_path": report_path,
        "manifest": manifest,
        "dataset_dir": output_dir,
        "authority": batch["authority"],
        "exam": batch["exam"],
        "year": batch["year"],
    }


def _build_public_catalog(
    repository_root: Path,
    *,
    authority: str,
    exam: str,
    year: int,
    manifest: dict[str, Any],
) -> bytes:
    """Rebuild the public search catalog from existing and newly built manifests."""
    data_root = repository_root / "public" / "data"
    datasets: dict[tuple[str, str, int], dict[str, Any]] = {}
    if data_root.exists() and not data_root.is_dir():
        raise PipelineError("public/data exists but is not a directory.")
    if data_root.exists():
        for path in sorted(data_root.rglob("manifest.json")):
            if path.is_symlink() or not path.is_file():
                raise PipelineError(f"Dataset manifest is not a regular file: {path}")
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PipelineError(f"Unable to read existing dataset manifest {path}: {exc}") from exc
            if not isinstance(existing, dict):
                raise PipelineError(f"Dataset manifest must be a JSON object: {path}")
            key = (existing.get("authority"), existing.get("exam"), existing.get("year"))
            if (
                not isinstance(key[0], str)
                or not isinstance(key[1], str)
                or isinstance(key[2], bool)
                or not isinstance(key[2], int)
                or existing.get("schema_version") != 1
            ):
                raise PipelineError(f"Dataset manifest identity is invalid: {path}")
            relative = path.relative_to(data_root)
            expected_parts = (key[0], key[1], str(key[2]), "manifest.json")
            if relative.parts != expected_parts:
                raise PipelineError(f"Dataset manifest identity does not match its public path: {path}")
            datasets[key] = {
                "authority": key[0],
                "exam": key[1],
                "year": key[2],
                "manifest": f"/data/{relative.as_posix()}",
            }

    if (
        manifest.get("schema_version") != 1
        or manifest.get("authority") != authority
        or manifest.get("exam") != exam
        or manifest.get("year") != year
    ):
        raise PipelineError("New dataset manifest identity does not match the validated batch.")
    relative = Path(authority) / exam / str(year) / "manifest.json"
    datasets[(authority, exam, year)] = {
        "authority": authority,
        "exam": exam,
        "year": year,
        "manifest": f"/data/{relative.as_posix()}",
    }
    catalog = {
        "schema_version": 1,
        "datasets": [
            datasets[key]
            for key in sorted(datasets, key=lambda item: (item[0], item[1], item[2]))
        ],
    }
    return (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _validate_owner_review_receipt(
    batch_path: str | Path,
    receipt_path: str | Path | None,
    *,
    processed: dict[str, Any],
    root: Path,
) -> dict[str, Any] | None:
    batch_file = _repo_path(str(batch_path), root)
    try:
        batch = json.loads(batch_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Unable to read batch for owner-review verification: {exc}") from exc
    if not isinstance(batch, dict) or batch.get("official_content_mode") != "public_preview_capture":
        return None
    try:
        if not requires_owner_visual_review(batch, root=root):
            return None
    except PublicationPolicyError as exc:
        raise PipelineError(f"Publication policy stopped safely: {exc}") from exc
    receipt_value = receipt_path or batch.get("owner_review_receipt")
    if receipt_value is None:
        raise PipelineError(
            "Owner visual-review receipt is required before publishing a public-preview capture."
        )
    receipt_file = _repo_path(str(receipt_value), root)
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Unable to read owner visual-review receipt: {exc}") from exc
    if not isinstance(receipt, dict):
        raise PipelineError("Owner visual-review receipt must be a JSON object.")

    try:
        records, capture_evidence = load_public_preview_capture(batch=batch, root=root)
    except PublicPreviewCaptureError as exc:
        raise PipelineError(f"Unable to verify owner-review candidate: {exc}") from exc
    canonical_records = [
        {"name": record["name"], "sequence_number": record["sequence_number"]}
        for record in records
    ]
    candidate_hash = hashlib.sha256(
        json.dumps(canonical_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    reviewed_at = receipt.get("reviewed_at")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")) if isinstance(reviewed_at, str) else None
    except ValueError:
        timestamp = None
    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or type(receipt.get("year")) is not int
        or type(receipt.get("announced_count")) is not int
        or type(receipt.get("record_count")) is not int
        or receipt.get("authority") != batch.get("authority")
        or receipt.get("exam") != batch.get("exam")
        or receipt.get("year") != batch.get("year")
        or receipt.get("announced_count") != batch.get("announced_count")
        or receipt.get("record_count") != len(records)
        or receipt.get("candidate_sha256") != candidate_hash
        or receipt.get("capture_manifest_sha256") != capture_evidence["capture_manifest_sha256"]
        or receipt.get("decision") != "approved"
        or receipt.get("source_evidence_reviewed") is not True
        or receipt.get("records_reviewed") is not True
        or not isinstance(receipt.get("reviewer"), str)
        or not receipt["reviewer"].strip()
        or timestamp is None
        or timestamp.tzinfo is None
    ):
        raise PipelineError("Owner review receipt is rejected or does not match the exact validated candidate.")
    if processed["report"].get("public_preview_capture", {}).get("capture_manifest_sha256") != (
        capture_evidence["capture_manifest_sha256"]
    ):
        raise PipelineError("Owner review receipt does not match the capture used by Greenlight.")
    return {
        "decision": "approved",
        "reviewer": receipt["reviewer"].strip(),
        "source_evidence_reviewed": True,
        "records_reviewed": True,
        "reviewed_at": reviewed_at,
        "candidate_sha256": candidate_hash,
        "capture_manifest_sha256": capture_evidence["capture_manifest_sha256"],
        "receipt_sha256": hashlib.sha256(receipt_file.read_bytes()).hexdigest(),
    }


def publish_batch(
    batch_path: str | Path,
    *,
    root: str | Path | None = None,
    owner_review_receipt: str | Path | None = None,
) -> dict[str, Any]:
    """Run Greenlight, build data artifacts, open a PR, dispatch CI, then merge."""
    repository_root = Path(root or Path.cwd()).resolve()
    processed = process_batch(batch_path, root=repository_root)
    owner_review = _validate_owner_review_receipt(
        batch_path,
        owner_review_receipt,
        processed=processed,
        root=repository_root,
    )
    if owner_review is not None:
        processed["report"]["owner_review"] = owner_review
        processed["report"]["public_preview_capture"]["visual_review_status"] = "APPROVED"
        write_validation_report(processed["report"], processed["report_path"])
        processed["manifest"]["official_content_mode"] = "public_preview_capture"
        processed["manifest"]["owner_review"] = owner_review
        manifest_path = processed["dataset_dir"] / "manifest.json"
        manifest_bytes = (json.dumps(processed["manifest"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        temporary_manifest = manifest_path.with_name(manifest_path.name + ".tmp")
        try:
            temporary_manifest.write_bytes(manifest_bytes)
            os.replace(temporary_manifest, manifest_path)
        except OSError as exc:
            temporary_manifest.unlink(missing_ok=True)
            raise PipelineError(f"Unable to write the owner-reviewed dataset manifest: {exc}") from exc
    authority, exam, year = processed["authority"], processed["exam"], processed["year"]
    prefix = f"public/data/{authority}/{exam}/{year}"
    artifacts = {
        f"{prefix}/{path.name}": path.read_bytes()
        for path in sorted(processed["dataset_dir"].iterdir())
        if path.is_file()
    }
    artifacts["public/data/catalog.json"] = _build_public_catalog(
        repository_root,
        authority=authority,
        exam=exam,
        year=year,
        manifest=processed["manifest"],
    )
    client = GitHubGitOps(os.environ.get("GITHUB_REPOSITORY", ""))
    opened = client.open_dataset_pr(
        artifacts=artifacts,
        greenlight_report=processed["report"],
        title=f"Publish {authority} {exam} {year} examination results",
    )
    merged = client.dispatch_ci_and_merge(
        pull_request_number=opened["pull_request_number"],
        greenlight_report=processed["report"],
        workflow_file="watcher-ci.yml",
    )
    return {"pull_request": opened, "publication": merged, "manifest": processed["manifest"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and publish a reviewed examination result batch.")
    parser.add_argument("batch", help="Repository-relative JSON file containing reviewed normalized records.")
    parser.add_argument(
        "--owner-review-receipt",
        help="Repository-relative visual-review receipt required for public-preview captures.",
    )
    args = parser.parse_args()
    batch_path = Path(args.batch)
    try:
        batch_bytes = batch_path.read_bytes()
        batch_data = json.loads(batch_bytes.decode("utf-8"))
        if not isinstance(batch_data, dict):
            batch_data = {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        batch_bytes, batch_data = b"", {}
    record_pipeline_event(
        batch_data, event_type="processing_started", status="started",
        summary="Verified import processing started.", batch_status="processing", batch_bytes=batch_bytes,
    )
    try:
        result = publish_batch(args.batch, owner_review_receipt=args.owner_review_receipt)
    except (PipelineError, AcquisitionError, GitOpsError, ValueError, TypeError) as exc:
        failed_greenlight = isinstance(exc, PipelineError) and str(exc).startswith("Greenlight rejected this batch")
        record_pipeline_event(
            batch_data,
            event_type="greenlight_failed" if failed_greenlight else "publication_failed",
            status="failed", summary="Processing stopped safely; consult the private workflow log.",
            batch_status="greenlight_failed" if failed_greenlight else "failed",
            report=read_validation_report(Path.cwd()), batch_bytes=batch_bytes,
        )
        print(f"PUBLICATION STOPPED: {exc}", file=sys.stderr)
        return 1
    report = read_validation_report(Path.cwd())
    record_pipeline_event(
        batch_data, event_type="publication_completed", status="completed",
        summary="Verified publication workflow completed successfully.", batch_status="published",
        report=report, batch_bytes=batch_bytes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
