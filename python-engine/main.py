#!/usr/bin/env python3
"""CLI entry point for the PH-EXAM-RESULTS Python processing engine."""

import argparse
import csv
import json
import sys
from pathlib import Path

from scraper.monitor import monitor_registry
from database.d1_client import D1Client, D1Error

from extractor.pdf_parser import PDFExtractionError, extract_pdf_lines
from processor.duplicates import find_duplicates
from processor.normalizer import normalize_record
from processor.validator import validate_batch


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

    report = {
        "schema_version": 1,
        "authority": args.authority,
        "examination": args.exam,
        "year": args.year,
        "source_file": source.name,
        "validation": validation,
        "duplicates": duplicates,
        "records": records,
        "publication_eligible": (
            validation["is_valid"]
            and not duplicates["exact_duplicates"]
            and not duplicates["fuzzy_candidates"]
        ),
        "notice": (
            "Processing output is not approved for publication. "
            "A human review and GitHub Pull Request approval are still required."
        ),
    }

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(destination),
        "total_records": validation["total_records"],
        "valid_records": validation["valid_records"],
        "invalid_records": len(validation["invalid_records"]),
        "exact_duplicates": len(duplicates["exact_duplicates"]),
        "fuzzy_candidates": len(duplicates["fuzzy_candidates"]),
        "publication_eligible": report["publication_eligible"],
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
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: Could not monitor source registry: {exc}", file=sys.stderr)
        return 2

    d1_status = "not_configured"
    try:
        client = D1Client.from_environment()
        schema_path = Path(__file__).parent / "database" / "schema.sql"
        client.apply_schema(schema_path)
        for item in report["results"]:
            source_id = item["source_id"]
            previous = client.get_source_state(source_id)
            if item["status"] == "reachable":
                if previous is None:
                    item["status"] = "baseline_created"
                elif (
                    item.get("etag") != previous.get("etag")
                    or item.get("last_modified") != previous.get("last_modified")
                ):
                    item["status"] = "changed"
                    report["changes_detected"] = True
                client.save_source_state(
                    source_id, item.get("etag"), item.get("last_modified"), item["checked_at"]
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

    report["d1_status"] = d1_status
    destination = Path(args.output)
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
    }, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="PH-EXAM-RESULTS Python engine")
    commands = parser.add_subparsers(dest="command", required=True)

    monitor_parser = commands.add_parser("monitor", help="Check approved source endpoints")\n    monitor_parser.add_argument("--registry", default="config/sources.json")\n    monitor_parser.add_argument("--output", default="artifacts/monitor-report.json")\n    monitor_parser.set_defaults(handler=monitor_sources)\n\n    csv_parser = commands.add_parser("process", help="Normalize and validate a CSV batch")
    csv_parser.add_argument("--input", required=True)
    csv_parser.add_argument("--authority", required=True, choices=("PRC", "CSC"))
    csv_parser.add_argument("--exam", required=True)
    csv_parser.add_argument("--year", required=True, type=int)
    csv_parser.add_argument("--output", required=True)
    csv_parser.set_defaults(handler=process_csv)

    pdf_parser = commands.add_parser("extract-pdf", help="Extract text from a text-based PDF")
    pdf_parser.add_argument("--input", required=True)
    pdf_parser.add_argument("--output", required=True)
    pdf_parser.set_defaults(handler=extract_pdf)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.handler(parsed))
