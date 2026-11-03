"""Automated PRC article -> public PDF -> records -> Greenlight -> GitOps publication."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))

from acquisition.prc_automation import (
    PRCAutomationError, _get, acquire_public_drive_pdf, parse_official_article,
)
from extractor.pdf_parser import extract_pdf
from acquisition.prc_automation import extract_sequence_name_pairs
from processor.greenlight import validate_records, write_validation_report
from publisher.json_builder import build_dataset
from publisher.gitops_manager import GitHubGitOps, GitOpsError


def run(article_url: str, level: str, exam: str, year: int):
    if level not in {"elementary", "secondary"}:
        raise PRCAutomationError("level must be elementary or secondary.")
    parsed = urlsplit(article_url)
    if parsed.scheme != "https" or parsed.hostname != "www.prc.gov.ph" or "/article/" not in parsed.path:
        raise PRCAutomationError("Only a direct official PRC article URL is accepted.")

    status, headers, final_url, html = _get(article_url, 3 * 1024 * 1024)
    if status != 200 or "text/html" not in (headers.get("Content-Type") or "").lower():
        raise PRCAutomationError(f"Official PRC article request failed (HTTP {status}).")
    if urlsplit(final_url).hostname != "www.prc.gov.ph":
        raise PRCAutomationError("PRC article redirected outside the official host.")

    article = parse_official_article(article_url, html)
    announced_count = article["announced_counts"].get(level)
    documents = [d for d in article["documents"] if d["level"] == level]
    if not isinstance(announced_count, int) or announced_count < 1:
        raise PRCAutomationError(f"Could not identify the official announced {level} passer count.")
    if len(documents) != 1:
        raise PRCAutomationError(f"Expected exactly one official {level} successful-examinees list; found {len(documents)}.")

    artifacts = ENGINE / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    pdf_path = artifacts / f"prc-{exam}-{year}-{level}.pdf"
    attempt_path = artifacts / f"prc-{exam}-{year}-{level}-acquisition.json"
    acquired = acquire_public_drive_pdf(
        official_article_url=article_url,
        linked_document_url=documents[0]["url"],
        output_path=pdf_path,
        attempt_log_path=attempt_path,
    )
    extraction = extract_pdf(pdf_path)
    records = extract_sequence_name_pairs(extraction, announced_count)
    report = validate_records(
        records, announced_count=announced_count, provenance="official_direct"
    )
    report.update({
        "source_id": "PRC-EXAM-RESULTS-HOMEPAGE",
        "official_source_url": "https://www.prc.gov.ph/articles/exam-results",
        "official_article_url": article_url,
        "official_document_url": documents[0]["url"],
        "source_pdf_sha256": acquired["sha256"],
        "announced_count": announced_count,
        "extracted_count": len(records),
        "extraction_method": "pdfplumber_tables_sequence_name_pairs",
        "sequence_coverage": "1..announced_count",
    })
    report_path = artifacts / f"prc-{exam}-{year}-{level}-validation.json"
    write_validation_report(report, report_path)
    if report.get("publication_allowed") is not True or report.get("greenlight_score") != 100:
        raise PRCAutomationError(
            f"Greenlight rejected the PRC {level} batch ({report.get('greenlight_score')}/100). "
            "No dataset PR was created."
        )

    dataset_dir = artifacts / f"prc-{exam}-{year}-{level}-dataset"
    manifest = build_dataset(
        records, authority="PRC", exam=exam, year=year,
        output_dir=dataset_dir, greenlight_report=report,
        provenance="official_direct",
    )
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not repository:
        raise PRCAutomationError("GITHUB_REPOSITORY is required for GitOps publication.")
    prefix = f"public/data/PRC/{exam}/{year}"
    files = {
        f"{prefix}/{level}/{path.name}": path.read_bytes()
        for path in sorted(dataset_dir.iterdir()) if path.is_file()
    }
    client = GitHubGitOps(repository)
    opened = client.open_dataset_pr(
        artifacts=files, greenlight_report=report,
        title=f"Publish PRC {exam} {year} {level.title()} results",
    )
    publication = client.dispatch_ci_and_merge(
        pull_request_number=opened["pull_request_number"],
        greenlight_report=report, workflow_file="watcher-ci.yml",
    )
    return {
        "article_url": article_url, "level": level,
        "announced_count": announced_count, "extracted_count": len(records),
        "greenlight_score": report["greenlight_score"],
        "pdf_sha256": acquired["sha256"], "manifest": manifest,
        "pull_request": opened, "publication": publication,
    }


def main():
    parser = argparse.ArgumentParser(description="Automate one official PRC result release.")
    parser.add_argument("--article-url", required=True)
    parser.add_argument("--level", required=True, choices=("elementary", "secondary"))
    parser.add_argument("--exam", required=True)
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.article_url, args.level, args.exam, args.year), ensure_ascii=False, indent=2))
    except (PRCAutomationError, GitOpsError, ValueError, TypeError) as exc:
        print(f"PRC AUTOMATION STOPPED SAFELY: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
