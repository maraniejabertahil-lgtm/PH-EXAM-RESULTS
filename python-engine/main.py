#!/usr/bin/env python3
"""CLI entry point for the PH-EXAM-RESULTS Python processing engine."""

import argparse
import csv
import hashlib
import json
from datetime import date
import os
import re
import sys
from pathlib import Path

from database.d1_client import D1Client, D1Error
from extractor.pdf_parser import PDFExtractionError, extract_pdf_lines
from processor.duplicates import find_duplicates
from processor.normalizer import normalize_record
from processor.validator import validate_batch
from prediction.release_predictor import predict_next_release
from preparation.status_builder import write_status
from publisher.gitops_manager import create_publication_pull_request, GitOpsError
from scraper.monitor import monitor_registry
from scraper.downloader import download_approved_file, DownloadError



def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()



def process_csv(args) -> int:
    source = Path(args.input)
    if not source.is_file() or source.suffix.lower() != ".csv":
        print("ERROR: --input must point to an existing CSV file.", file=sys.stderr)
        return 2

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "name" not in {
                field.strip().lower() for field in reader.fieldnames
            }:
                print("ERROR: CSV must contain a 'name' column.", file=sys.stderr)
                return 2
            rows = [
                {str(k).strip().lower(): v for k, v in row.items() if k is not None}
                for row in reader
            ]
    except (OSError, UnicodeError, csv.Error) as exc:
        print(f"ERROR: Could not read CSV: {exc}", file=sys.stderr)
        return 2

    records = [
        normalize_record(row, args.authority, args.exam, args.year)
        for row in rows
    ]
    validation = validate_batch(records)
    duplicates = find_duplicates(records)

    actual_release_date = args.actual_release_date or None
    if actual_release_date:
        try:
            date.fromisoformat(actual_release_date)
        except ValueError:
            print("ERROR: --actual-release-date must use YYYY-MM-DD.", file=sys.stderr)
            return 2

    report = {
        "schema_version": 1,
        "authority": args.authority,
        "examination": args.exam,
        "year": args.year,
        "source_file": source.name,
        "source_file_sha256": file_sha256(source),
        "source_reference": args.source_reference or None,
        "actual_release_date": actual_release_date,
        "validation": validation,
        "duplicates": duplicates,
        "records": records,
        "publication_eligible": (
            validation["is_valid"]
            and not duplicates["exact_duplicates"]
        ),
        "manual_review_required": bool(duplicates["fuzzy_candidates"]),
        "notice": (
            "Processing output is not approved for publication. "
            "A human review and GitHub Pull Request approval are still required."
        ),
    }

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    d1_status = "not_configured"
    try:
        client = D1Client.from_environment()
        client.apply_schema(Path(__file__).parent / "database" / "schema.sql")
        report["d1_batch_id"] = client.record_import_batch(report, args.source_reference)
        if actual_release_date:
            client.record_actual_release_date(
                args.authority, args.exam, args.year, actual_release_date
            )
        d1_status = "connected"
    except D1Error as exc:
        report["d1_notice"] = str(exc)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(destination),
        "d1_status": d1_status,
        "total_records": validation["total_records"],
        "valid_records": validation["valid_records"],
        "invalid_records": len(validation["invalid_records"]),
        "exact_duplicates": len(duplicates["exact_duplicates"]),
        "fuzzy_candidates": len(duplicates["fuzzy_candidates"]),
        "publication_eligible": report["publication_eligible"],
        "manual_review_required": report["manual_review_required"],
    }, indent=2))
    return 0 if validation["is_valid"] else 1


def extract_pdf(args) -> int:
    try:
        lines = extract_pdf_lines(args.input)
    except PDFExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = {
        "source_file": Path(args.input).name,
        "source_file_sha256": file_sha256(args.input),
        "extracted_line_count": len(lines),
        "manual_review_required": True,
        "notice": (
            "PDF text extraction is not passer-record extraction. "
            "Review the source layout and map records before validation or publication."
        ),
        "lines": lines,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Extracted {len(lines)} text lines to {destination}; manual review required.")
    return 0


def monitor_sources(args) -> int:
    try:
        report = monitor_registry(args.registry)
        sources = {
            str(source.get("id", "unknown")): source
            for source in json.loads(Path(args.registry).read_text(encoding="utf-8")).get("sources", [])
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: Could not monitor source registry: {exc}", file=sys.stderr)
        return 2

    d1_status = "not_configured"
    repo_root = Path(__file__).resolve().parents[1]
    artifact_root = repo_root / "artifacts" / "source-acquisitions"

    try:
        client = D1Client.from_environment()
        client.apply_schema(Path(__file__).parent / "database" / "schema.sql")

        for item in report["results"]:
            source_id = item["source_id"]
            source = sources.get(source_id)
            previous = client.get_source_state(source_id)

            if item["status"] == "reachable":
                if previous is None:
                    item["status"] = "baseline_created"
                elif (
                    item.get("etag") != previous.get("etag")
                    or item.get("last_modified") != previous.get("last_modified")
                    or item.get("content_length") != previous.get("content_length")
                ):
                    item["status"] = "changed"
                    report["changes_detected"] = True

                acquisition_succeeded = True
                if (
                    source
                    and source.get("auto_acquire") is True
                    and item["status"] in {"baseline_created", "changed"}
                ):
                    # Do not advance the source baseline until acquisition and its
                    # required processing/publication handoff have safely completed.
                    acquisition_succeeded = False
                    if not any(item.get(key) for key in ("etag", "last_modified", "content_length")):
                        item["status"] = "metadata_insufficient"
                        item["notice"] = "Source provides no ETag, Last-Modified, or Content-Length; automatic change detection is unsafe."
                    else:
                        file_format = str(source.get("file_format", "")).lower()
                        if file_format not in {"csv", "pdf"}:
                            item["status"] = "unsupported_file_format"
                            acquisition_succeeded = False
                        elif (
                            source.get("authority") not in {"PRC", "CSC"}
                            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", str(source.get("exam", "")))
                            or not isinstance(source.get("year"), int)
                        ):
                            item["status"] = "invalid_source_configuration"
                            acquisition_succeeded = False
                        else:
                            safe_id = re.sub(r"[^A-Za-z0-9_-]", "-", source_id)[:60] or "source"
                            destination = artifact_root / f"{safe_id}.{file_format}"
                            try:
                                acquisition = download_approved_file(source, destination)
                                item["acquisition"] = acquisition
                                if file_format == "csv":
                                    report_path = artifact_root / f"{safe_id}-processing-report.json"
                                    process_args = argparse.Namespace(
                                        input=str(destination),
                                        authority=source["authority"],
                                        exam=source["exam"],
                                        year=source["year"],
                                        output=str(report_path),
                                        source_reference=source.get("url", ""),
                                        actual_release_date=source.get("actual_release_date", ""),
                                    )
                                    process_code = process_csv(process_args)
                                    item["processing_exit_code"] = process_code
                                    if report_path.is_file():
                                        processed_report = json.loads(report_path.read_text(encoding="utf-8"))
                                        item["validation"] = processed_report.get("validation")
                                        item["duplicates"] = processed_report.get("duplicates")
                                        if process_code == 0 and processed_report.get("duplicates", {}).get("exact_duplicates"):
                                            item["status"] = "exact_duplicates_review_required"
                                            item["manual_review_required"] = True
                                            acquisition_succeeded = True
                                        elif process_code == 0:
                                            token = os.getenv("GITHUB_TOKEN")
                                            repository = os.getenv("GITHUB_REPOSITORY")
                                            if token and repository:
                                                try:
                                                    publication = create_publication_pull_request(
                                                        repo_root=repo_root,
                                                        report=processed_report,
                                                        repository=repository,
                                                        token=token,
                                                        source_reference=source.get("url", ""),
                                                        replace_existing=source.get("replace_existing") is True,
                                                    )
                                                    item["pull_request_url"] = publication.get("pull_request_url")
                                                    batch_id = processed_report.get("d1_batch_id")
                                                    if batch_id:
                                                        try:
                                                            client.update_import_batch_status(batch_id, "awaiting_approval")
                                                        except D1Error as exc:
                                                            item["batch_status_warning"] = str(exc)[:300]
                                                    acquisition_succeeded = True
                                                except GitOpsError as exc:
                                                    item["publication_error"] = str(exc)
                                            else:
                                                item["publication_error"] = "GitHub token or repository context is unavailable."
                                        else:
                                            item["status"] = "validation_failed"
                                            item["manual_review_required"] = True
                                            acquisition_succeeded = False
                                    else:
                                        item["status"] = "processing_failed"
                                        item["manual_review_required"] = True
                                        acquisition_succeeded = False
                                else:
                                    lines = extract_pdf_lines(destination)
                                    extraction_path = artifact_root / f"{safe_id}-pdf-extraction.json"
                                    extraction_path.parent.mkdir(parents=True, exist_ok=True)
                                    extraction_path.write_text(
                                        json.dumps({
                                            "source_file": destination.name,
                                            "source_file_sha256": acquisition["sha256"],
                                            "extracted_line_count": len(lines),
                                            "manual_review_required": True,
                                            "lines": lines,
                                        }, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8",
                                    )
                                    item["status"] = "manual_review_required"
                                    item["extracted_line_count"] = len(lines)
                                    acquisition_succeeded = True
                            except (DownloadError, PDFExtractionError, OSError, ValueError) as exc:
                                item["status"] = "acquisition_failed"
                                item["error"] = str(exc)[:300]
                                acquisition_succeeded = False
    
                if acquisition_succeeded:
                    client.save_source_state(
                        source_id,
                        item.get("etag"),
                        item.get("last_modified"),
                        item.get("content_length"),
                        item["checked_at"],
                    )

            client.record_monitoring_log(
                source_id,
                item["status"],
                item["checked_at"],
                item.get("error"),
                item.get("etag"),
                item.get("last_modified"),
            )
        d1_status = "connected"
    except D1Error as exc:
        report["d1_notice"] = str(exc)
        d1_configured = all(
            os.getenv(name)
            for name in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "D1_DATABASE_ID")
        )
        d1_status = "error" if d1_configured else "not_configured"

    report["d1_status"] = d1_status
    destination = Path(args.output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "source_count": report["source_count"],
        "changes_detected": report["changes_detected"],
        "d1_status": d1_status,
        "output": str(destination),
        "results": report["results"],
    }, indent=2))
    return 1 if d1_status == "error" else 0

def publish_batch(args) -> int:
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Could not read processing report: {exc}", file=sys.stderr)
        return 2

    validation = report.get("validation", {})
    if not validation.get("is_valid"):
        print("ERROR: Invalid batches cannot enter the publication Pull Request.", file=sys.stderr)
        return 1
    duplicates = report.get("duplicates", {})
    if duplicates.get("exact_duplicates"):
        print(
            "ERROR: Exact duplicate records must be resolved before a publication PR can be created.",
            file=sys.stderr,
        )
        return 1

    repository = args.repository or os.getenv("GITHUB_REPOSITORY")
    token = args.token or os.getenv("GITHUB_TOKEN")
    if not repository or not token:
        print("ERROR: GITHUB_REPOSITORY and GITHUB_TOKEN are required.", file=sys.stderr)
        return 2

    try:
        result = create_publication_pull_request(
            repo_root=Path(__file__).resolve().parents[1],
            report=report,
            repository=repository,
            token=token,
            source_reference=args.source_reference,
            replace_existing=args.replace_existing,
        )
    except GitOpsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    batch_id = report.get("d1_batch_id")
    if batch_id:
        try:
            D1Client.from_environment().update_import_batch_status(batch_id, "awaiting_approval")
        except D1Error:
            pass
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0




def predict_release(args) -> int:
    try:
        client = D1Client.from_environment()
        client.apply_schema(Path(__file__).parent / "database" / "schema.sql")
        dates = client.get_actual_release_dates(args.authority, args.exam, limit=6)
    except D1Error as exc:
        print(f"ERROR: D1 is required for release prediction: {exc}", file=sys.stderr)
        return 2

    prediction = predict_next_release(dates)
    if prediction["predicted_date"]:
        client.save_release_prediction(
            args.authority,
            args.exam,
            args.year,
            prediction["predicted_date"],
            prediction["data_points"],
        )
    print(json.dumps({
        "authority": args.authority,
        "examination": args.exam,
        "target_year": args.year,
        **prediction,
    }, indent=2))
    return 0




def write_site_status(args) -> int:
    try:
        if args.mode == "preparing":
            existing_status_path = Path(args.output)
            if existing_status_path.is_file():
                existing_status = json.loads(existing_status_path.read_text(encoding="utf-8"))
                active = existing_status.get("preparation") or {}
                if (
                    existing_status.get("mode") == "preparing"
                    and (
                        active.get("authority") != args.authority
                        or active.get("exam") != args.exam
                        or active.get("year") != args.year
                    )
                ):
                    raise ValueError(
                        "Another examination is already in Preparing Mode. "
                        "Clear or complete that mode before activating a different examination."
                    )
            client = D1Client.from_environment()
            prediction = client.get_release_prediction(args.authority, args.exam, args.year)
            if not prediction or not prediction.get("predicted_date"):
                raise ValueError("No historical release prediction exists for this examination/year.")
            predicted_date = date.fromisoformat(str(prediction["predicted_date"])[:10])
            days_until = (predicted_date - date.today()).days
            if days_until > 5:
                raise ValueError("Preparing Mode can be activated only within five days of the predicted release date.")
        status = write_status(
            args.output,
            mode=args.mode,
            authority=args.authority,
            exam=args.exam,
            year=args.year,
            examination_name=args.examination_name,
            stage=args.stage,
        )
    except (ValueError, D1Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0




def predict_all(args) -> int:
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        examinations = config.get("examinations", [])
        if not isinstance(examinations, list):
            raise ValueError("examinations must be an array")
        client = D1Client.from_environment()
        client.apply_schema(Path(__file__).parent / "database" / "schema.sql")
    except (OSError, json.JSONDecodeError, ValueError, D1Error) as exc:
        print(f"ERROR: Cannot update predictions: {exc}", file=sys.stderr)
        return 2

    results = []
    for item in examinations:
        authority = item.get("authority")
        exam = item.get("exam")
        year = item.get("target_year")
        if authority not in {"PRC", "CSC"} or not exam or not isinstance(year, int):
            print(f"Skipping invalid examination configuration: {item}", file=sys.stderr)
            continue
        dates = client.get_actual_release_dates(authority, exam, limit=6)
        prediction = predict_next_release(dates)
        if prediction["predicted_date"]:
            client.save_release_prediction(
                authority, exam, year, prediction["predicted_date"], prediction["data_points"]
            )
        results.append({
            "authority": authority,
            "exam": exam,
            "target_year": year,
            **prediction,
        })
    print(json.dumps({"configured_examinations": len(examinations), "results": results}, indent=2))
    return 0




def mark_published(args) -> int:
    try:
        batch = json.loads(Path(args.batch_file).read_text(encoding="utf-8"))
        client = D1Client.from_environment()
        client.update_import_batch_status(batch["batch_id"], "published")
    except (OSError, json.JSONDecodeError, KeyError, D1Error) as exc:
        print(f"ERROR: Could not mark import batch as published: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"batch_id": batch["batch_id"], "status": "published"}))
    return 0





def d1_size(args) -> int:
    try:
        client = D1Client.from_environment()
        stats = client.get_storage_stats()
    except D1Error as exc:
        print(f"ERROR: Could not read D1 storage usage: {exc}", file=sys.stderr)
        return 2
    stats["estimated_storage_mb"] = round(
        stats["estimated_storage_bytes"] / 1_000_000, 2
    )
    stats["free_tier_reference_mb"] = 500
    print(json.dumps(stats, indent=2))
    return 0



def build_parser():
    parser = argparse.ArgumentParser(description="PH-EXAM-RESULTS Python engine")
    commands = parser.add_subparsers(dest="command", required=True)

    monitor_parser = commands.add_parser("monitor", help="Check approved source endpoints")
    monitor_parser.add_argument("--registry", default="config/sources.json")
    monitor_parser.add_argument("--output", default="artifacts/monitor-report.json")
    monitor_parser.set_defaults(handler=monitor_sources)

    csv_parser = commands.add_parser("process", help="Normalize and validate a CSV batch")
    csv_parser.add_argument("--input", required=True)
    csv_parser.add_argument("--authority", required=True, choices=("PRC", "CSC"))
    csv_parser.add_argument("--exam", required=True)
    csv_parser.add_argument("--year", required=True, type=int)
    csv_parser.add_argument("--output", required=True)
    csv_parser.add_argument("--source-reference", default="")
    csv_parser.add_argument("--actual-release-date", default="")
    csv_parser.set_defaults(handler=process_csv)

    predict_all_parser = commands.add_parser("predict-all", help="Update predictions for configured examinations")
    predict_all_parser.add_argument("--config", default="config/examinations.json")
    predict_all_parser.set_defaults(handler=predict_all)

    published_parser = commands.add_parser("mark-published", help="Mark an imported batch published after deployment")
    published_parser.add_argument("--batch-file", required=True)
    published_parser.set_defaults(handler=mark_published)

    status_parser = commands.add_parser("site-status", help="Generate approved Preparing/Search mode status JSON")
    status_parser.add_argument("--mode", required=True, choices=("search", "preparing"))
    status_parser.add_argument("--output", default="../public/data/site-status.json")
    status_parser.add_argument("--authority", choices=("PRC", "CSC"))
    status_parser.add_argument("--exam")
    status_parser.add_argument("--year", type=int)
    status_parser.add_argument("--examination-name")
    status_parser.add_argument("--stage", choices=("monitoring", "source_detected", "document_acquired", "extracting", "validating", "awaiting_approval"))
    status_parser.set_defaults(handler=write_site_status)

    d1_size_parser = commands.add_parser("d1-size", help="Report internal D1 storage usage")
    d1_size_parser.set_defaults(handler=d1_size)

    prediction_parser = commands.add_parser("predict", help="Estimate a release date from D1 history")
    prediction_parser.add_argument("--authority", required=True, choices=("PRC", "CSC"))
    prediction_parser.add_argument("--exam", required=True)
    prediction_parser.add_argument("--year", required=True, type=int)
    prediction_parser.set_defaults(handler=predict_release)

    publish_parser = commands.add_parser("publish", help="Prepare datasets and open an owner-approval PR")
    publish_parser.add_argument("--report", required=True)
    publish_parser.add_argument("--repository")
    publish_parser.add_argument("--token")
    publish_parser.add_argument("--source-reference", default="")
    publish_parser.add_argument("--replace-existing", action="store_true")
    publish_parser.set_defaults(handler=publish_batch)

    pdf_parser = commands.add_parser("extract-pdf", help="Extract text from a text-based PDF")
    pdf_parser.add_argument("--input", required=True)
    pdf_parser.add_argument("--output", required=True)
    pdf_parser.set_defaults(handler=extract_pdf)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.handler(parsed))
