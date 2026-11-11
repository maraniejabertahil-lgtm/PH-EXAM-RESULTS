"""Publish the March 2026 LEPT Elementary and Secondary datasets atomically.

Both exact candidate batches must pass Greenlight and carry separate Owner
review receipts before one data-only PR can be opened and merged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from acquisition.public_preview import load_public_preview_capture
from main import (
    GitHubGitOps,
    PipelineError,
    _build_public_catalog,
    _validate_owner_review_receipt,
    process_batch,
    write_validation_report,
)

EXPECTED_COUNTS = {
    "LEPT-ELEMENTARY": 18_376,
    "LEPT-SECONDARY": 45_001,
}
TOTAL_EXPECTED = sum(EXPECTED_COUNTS.values())


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Unable to read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} must be a JSON object.")
    return value


def _require_owner_dispatch(repository: str, actor: str) -> str:
    """Bind the publication request to an authenticated repository-owner dispatch."""
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise PipelineError("GITHUB_REPOSITORY must identify the publication repository.")
    owner = repository.split("/", 1)[0].strip()
    if not owner or not isinstance(actor, str) or actor.strip().casefold() != owner.casefold():
        raise PipelineError("Only the authenticated repository Owner may submit the paired publication run.")
    return actor.strip()


def build_combined_greenlight_report(
    records_by_exam: dict[str, list[dict[str, str]]],
    owner_reviews: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Create one auditable 100-point gate only after both exact lists pass."""
    if set(records_by_exam) != set(EXPECTED_COUNTS) or set(owner_reviews) != set(EXPECTED_COUNTS):
        raise PipelineError("Both LEPT levels and both Owner review receipts are required.")
    canonical: list[dict[str, str]] = []
    checks: dict[str, bool] = {}
    for exam, expected in EXPECTED_COUNTS.items():
        records = records_by_exam[exam]
        if len(records) != expected:
            raise PipelineError(f"{exam} record count is {len(records)}, expected {expected}.")
        review = owner_reviews[exam]
        if (
            review.get("decision") != "approved"
            or review.get("source_evidence_reviewed") is not True
            or review.get("records_reviewed") is not True
            or not review.get("reviewer")
            or not review.get("candidate_sha256")
            or not review.get("capture_manifest_sha256")
        ):
            raise PipelineError(f"{exam} Owner review receipt is incomplete or not approved.")
        checks[f"{exam.lower()}_greenlight_passed"] = True
        checks[f"{exam.lower()}_owner_review_approved"] = True
        checks[f"{exam.lower()}_official_count_matched"] = True
        for record in records:
            canonical.append({
                "exam": exam,
                "sequence_number": str(record["sequence_number"]),
                "name": record["name"],
            })
    if len(canonical) != TOTAL_EXPECTED:
        raise PipelineError("Combined LEPT count does not match the official total.")
    checks["both_levels_present"] = True
    checks["combined_count_matched"] = True
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "status": "GREENLIGHT",
        "greenlight_score": 100,
        "publication_allowed": True,
        "checks": checks,
        "authority": "PRC",
        "exam": "LEPT-MARCH-2026",
        "year": 2026,
        "record_count": TOTAL_EXPECTED,
        "announced_count": TOTAL_EXPECTED,
        "records_sha256": digest,
        "provenance": "official_direct",
        "owner_reviews": owner_reviews,
    }



def _prevalidate_owner_receipt(
    *,
    batch: dict[str, Any],
    receipt_path: Path,
    root: Path,
) -> None:
    """Bind the receipt to the exact records and capture before enabling sources."""
    receipt = _read_json(receipt_path, f"{batch.get('exam')} Owner receipt")
    records, capture_evidence = load_public_preview_capture(batch=batch, root=root)
    canonical_records = [
        {"name": record["name"], "sequence_number": record["sequence_number"]}
        for record in records
    ]
    candidate_hash = hashlib.sha256(
        json.dumps(canonical_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    expected = {
        "schema_version": 1,
        "authority": "PRC",
        "exam": batch.get("exam"),
        "year": batch.get("year"),
        "announced_count": batch.get("announced_count"),
        "record_count": len(records),
        "candidate_sha256": candidate_hash,
        "capture_manifest_sha256": capture_evidence["capture_manifest_sha256"],
        "source_evidence_reviewed": True,
        "records_reviewed": True,
        "decision": "approved",
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise PipelineError(f"{batch.get('exam')} Owner receipt does not match the exact candidate ({key}).")
    if not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip():
        raise PipelineError(f"{batch.get('exam')} Owner receipt has no reviewer.")
    if not isinstance(receipt.get("reviewed_at"), str):
        raise PipelineError(f"{batch.get('exam')} Owner receipt has no review timestamp.")


def _temporarily_enable_reviewed_sources(
    *,
    batches: dict[str, dict[str, Any]],
    root: Path,
) -> tuple[Path, bytes]:
    """Enable only the two exact source entries in this disposable runner workspace."""
    registry_path = root / "python-engine" / "config" / "sources.json"
    original = registry_path.read_bytes()
    registry = _read_json(registry_path, "approved PRC source registry")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise PipelineError("Approved source registry has no sources list.")
    for exam, batch in batches.items():
        source_id = batch.get("exam_specific_source_id")
        matches = [
            source for source in sources
            if isinstance(source, dict)
            and source.get("id") == source_id
            and source.get("authority") == "PRC"
            and source.get("exam") == f"{exam}-2026"
            and source.get("url") == batch.get("official_article_url")
        ]
        if len(matches) != 1:
            raise PipelineError(f"{exam} does not match exactly one reviewed official PRC source entry.")
        source = matches[0]
        if (
            source.get("authorized") is not True
            or source.get("source_type") != "official"
            or not isinstance(source.get("public_preview"), dict)
            or source["public_preview"].get("enabled") is not True
            or not isinstance(source.get("robots_policy_url"), str)
            or not source["robots_policy_url"].startswith("https://")
        ):
            raise PipelineError(f"{exam} source is not eligible for Owner-reviewed publication.")
        source["enabled"] = True
        source["auto_acquire"] = True
        source["robots_policy_verified"] = True
        source.pop("disable_reason", None)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return registry_path, original


def _prepare_level(
    *,
    exam: str,
    batch_path: Path,
    receipt_path: Path,
    run_id: str,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, str]]]:
    batch = _read_json(batch_path, f"{exam} release batch")
    expected = EXPECTED_COUNTS[exam]
    if (
        batch.get("authority") != "PRC"
        or batch.get("exam") != exam
        or batch.get("year") != 2026
        or batch.get("announced_count") != expected
        or batch.get("official_content_mode") != "public_preview_capture"
        or batch.get("provenance") != "official_direct"
    ):
        raise PipelineError(f"{exam} batch identity, count, or official provenance is invalid.")

    shared_dataset_dir = root / "python-engine" / "artifacts" / "dataset"
    if shared_dataset_dir.exists():
        shutil.rmtree(shared_dataset_dir)
    execution_id = f"python:lept-pair:{run_id}:{exam.lower()}"
    processed = process_batch(
        batch_path.relative_to(root).as_posix(),
        root=root,
        activity_execution_id=execution_id,
    )
    if (
        processed["report"].get("greenlight_score") != 100
        or processed["report"].get("record_count") != expected
        or processed["report"].get("publication_allowed") is not True
    ):
        raise PipelineError(f"{exam} did not pass the complete Greenlight gate.")

    owner_review = _validate_owner_review_receipt(
        batch_path.relative_to(root).as_posix(),
        receipt_path.relative_to(root).as_posix(),
        processed=processed,
        root=root,
    )
    if owner_review is None or owner_review.get("decision") != "approved":
        raise PipelineError(f"{exam} requires an approved Owner review receipt.")

    processed["report"]["owner_review"] = owner_review
    processed["report"]["public_preview_capture"]["visual_review_status"] = "APPROVED"
    write_validation_report(processed["report"], processed["report_path"])
    processed["manifest"]["official_content_mode"] = "public_preview_capture"
    processed["manifest"]["owner_review"] = owner_review
    manifest_path = processed["dataset_dir"] / "manifest.json"
    manifest_path.write_text(
        json.dumps(processed["manifest"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    snapshot_dir = root / "python-engine" / "artifacts" / f"dataset-{exam.lower()}"
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    shutil.copytree(processed["dataset_dir"], snapshot_dir)

    records, _capture_evidence = load_public_preview_capture(batch=batch, root=root)
    return batch, processed, snapshot_dir, records


def publish_lept_pair(
    *,
    run_id: str,
    elementary_batch: str | Path,
    secondary_batch: str | Path,
    elementary_receipt: str | Path,
    secondary_receipt: str | Path,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate both receipts, assemble one atomic data PR, then run gated CI."""
    if not isinstance(run_id, str) or not run_id.isdigit():
        raise PipelineError("The source live-retrieval run ID must be numeric.")
    owner_actor = _require_owner_dispatch(
        os.environ.get("GITHUB_REPOSITORY", ""),
        os.environ.get("GITHUB_ACTOR", ""),
    )
    repository_root = Path(root or Path.cwd()).resolve()
    paths = {
        "LEPT-ELEMENTARY": (
            (repository_root / elementary_batch).resolve(),
            (repository_root / elementary_receipt).resolve(),
        ),
        "LEPT-SECONDARY": (
            (repository_root / secondary_batch).resolve(),
            (repository_root / secondary_receipt).resolve(),
        ),
    }
    for exam, (batch_path, receipt_path) in paths.items():
        for candidate_path in (batch_path, receipt_path):
            try:
                candidate_path.relative_to(repository_root)
            except ValueError as exc:
                raise PipelineError(f"{exam} inputs must remain inside the repository workspace.") from exc
            if not candidate_path.is_file():
                raise PipelineError(f"{exam} input file is missing: {candidate_path.relative_to(repository_root)}")

    batches = {
        exam: _read_json(paths[exam][0], f"{exam} release batch")
        for exam in EXPECTED_COUNTS
    }
    for exam in EXPECTED_COUNTS:
        _prevalidate_owner_receipt(
            batch=batches[exam],
            receipt_path=paths[exam][1],
            root=repository_root,
        )

    registry_path, original_registry = _temporarily_enable_reviewed_sources(
        batches=batches,
        root=repository_root,
    )
    prepared: dict[str, tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, str]]]] = {}
    owner_reviews: dict[str, dict[str, Any]] = {}
    records_by_exam: dict[str, list[dict[str, str]]] = {}
    try:
        for exam in EXPECTED_COUNTS:
            batch, processed, snapshot_dir, records = _prepare_level(
                exam=exam,
                batch_path=paths[exam][0],
                receipt_path=paths[exam][1],
                run_id=run_id,
                root=repository_root,
            )
            prepared[exam] = (batch, processed, snapshot_dir, records)
            owner_reviews[exam] = processed["report"]["owner_review"]
            records_by_exam[exam] = records
    finally:
        registry_path.write_bytes(original_registry)

    article_urls = {prepared[exam][0].get("official_article_url") for exam in EXPECTED_COUNTS}
    if len(article_urls) != 1 or not next(iter(article_urls)):
        raise PipelineError("Elementary and Secondary batches do not share the same official PRC announcement.")

    # Stage both reviewed datasets in the isolated runner workspace so the
    # generated catalog contains both levels before one PR is opened.
    artifacts: dict[str, bytes] = {}
    for exam, (_batch, processed, snapshot_dir, _records) in prepared.items():
        destination = repository_root / "public" / "data" / "PRC" / exam / "2026"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for item in snapshot_dir.iterdir():
            if item.is_file():
                target = destination / item.name
                shutil.copy2(item, target)
                artifacts[f"public/data/PRC/{exam}/2026/{item.name}"] = target.read_bytes()

    secondary_manifest = prepared["LEPT-SECONDARY"][1]["manifest"]
    artifacts["public/data/catalog.json"] = _build_public_catalog(
        repository_root,
        authority="PRC",
        exam="LEPT-SECONDARY",
        year=2026,
        manifest=secondary_manifest,
    )
    combined_report = build_combined_greenlight_report(records_by_exam, owner_reviews)

    client = GitHubGitOps(os.environ.get("GITHUB_REPOSITORY", ""))
    publication_run_id = os.getenv("GITHUB_RUN_ID") or run_id
    opened = client.open_dataset_pr(
        artifacts=artifacts,
        greenlight_report=combined_report,
        title="Publish PRC March 2026 LET Elementary and Secondary results",
        branch_name=f"data/lept-pair-{publication_run_id}-{combined_report['records_sha256'][:8]}",
    )
    publication = client.dispatch_ci_and_merge(
        pull_request_number=opened["pull_request_number"],
        greenlight_report=combined_report,
        workflow_file="watcher-ci.yml",
    )
    result = {
        "status": "PUBLISHED" if publication.get("merged") is True else "AWAITING_PUBLICATION",
        "owner_submission_actor": owner_actor,
        "source_live_retrieval_run_id": run_id,
        "record_count": TOTAL_EXPECTED,
        "elementary_count": EXPECTED_COUNTS["LEPT-ELEMENTARY"],
        "secondary_count": EXPECTED_COUNTS["LEPT-SECONDARY"],
        "records_sha256": combined_report["records_sha256"],
        "owner_reviews": owner_reviews,
        "pull_request": opened,
        "publication": publication,
    }
    report_path = repository_root / "python-engine" / "artifacts" / "lept-pair-publication-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish both Owner-approved March 2026 LEPT result lists atomically.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--elementary-batch", required=True)
    parser.add_argument("--secondary-batch", required=True)
    parser.add_argument("--elementary-receipt", required=True)
    parser.add_argument("--secondary-receipt", required=True)
    args = parser.parse_args()
    try:
        result = publish_lept_pair(
            run_id=args.run_id,
            elementary_batch=args.elementary_batch,
            secondary_batch=args.secondary_batch,
            elementary_receipt=args.elementary_receipt,
            secondary_receipt=args.secondary_receipt,
        )
    except Exception as exc:
        print(f"LEPT PAIR PUBLICATION STOPPED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
