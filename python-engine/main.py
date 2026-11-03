"""Python processing-to-GitOps entry point for pre-structured result batches.

The PDF parser deliberately remains raw-only. This pipeline therefore accepts
an explicitly reviewed records JSON file; it does not infer table columns or
pretend that raw PDF text has been normalized automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from acquisition.official_first_policy import third_party_fallback_gate
from acquisition.official_pdf import AcquisitionError, acquire_official_pdf
from acquisition.official_content import OfficialContentError, verify_official_content_link
from extractor.pdf_parser import extract_pdf
from processor.greenlight import validate_records, write_validation_report
from processor.normalizer import NormalizationError, normalize_extracted_tables
from publisher.gitops_manager import GitHubGitOps, GitOpsError
from publisher.json_builder import build_dataset


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
    if (
        source.get("enabled") is not True
        or source.get("source_type") != "official"
        or source.get("authorized") is not True
        or source.get("authority") != batch.get("authority")
        or source.get("exam") != batch.get("exam")
    ):
        raise PipelineError("Batch identity does not match an enabled, authorized official source.")
    if batch.get("official_source_url") != source.get("url"):
        raise PipelineError("official_source_url must exactly match the approved registry URL.")
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
    report["official_document_url"] = batch.get("official_document_url") or batch.get("official_content_url")\n    report["official_content_mode"] = batch.get("official_content_mode")
    report["source_pdf_sha256"] = source_pdf_sha256
    report["official_article_url"] = batch.get("official_article_url")
    report["official_attempt_log"] = acquisition_log_path if provenance == "official_direct" else batch.get("official_attempt_log")
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


def publish_batch(batch_path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Run Greenlight, build data artifacts, open a PR, dispatch CI, then merge."""
    repository_root = Path(root or Path.cwd()).resolve()
    processed = process_batch(batch_path, root=repository_root)
    authority, exam, year = processed["authority"], processed["exam"], processed["year"]
    prefix = f"public/data/{authority}/{exam}/{year}"
    artifacts = {
        f"{prefix}/{path.name}": path.read_bytes()
        for path in sorted(processed["dataset_dir"].iterdir())
        if path.is_file()
    }
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
    args = parser.parse_args()
    try:
        result = publish_batch(args.batch)
    except (PipelineError, AcquisitionError, GitOpsError, ValueError, TypeError) as exc:
        print(f"PUBLICATION STOPPED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
