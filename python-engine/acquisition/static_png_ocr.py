"""Fail-closed Tier 3 OCR for reviewed, stable static PNG captures.

OCR is never a primary acquisition path. This module requires recorded Tier 1
and Tier 2 failures, a reviewed source/exam mapping, Owner-reviewed public-
viewability and access-compliance evidence, stable lossless PNG evidence, and
per-token confidence >= 95%.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class StaticPngOcrError(RuntimeError):
    """Raised when Tier 3 OCR evidence is incomplete or unsafe."""


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_TOKEN_CONFIDENCE = 95.0


def _safe_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise StaticPngOcrError(f"{label} is required.")
    unresolved = root / value
    if unresolved.is_symlink():
        raise StaticPngOcrError(f"{label} must not be a symbolic link.")
    path = unresolved.resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise StaticPngOcrError(f"{label} must remain inside the repository.") from exc
    if not path.is_file() or path.is_symlink():
        raise StaticPngOcrError(f"{label} is not a regular file: {value}")
    return path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StaticPngOcrError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise StaticPngOcrError(f"{label} must be a JSON object.")
    return value


def _review_is_current(review: Any, label: str) -> None:
    if not isinstance(review, dict):
        raise StaticPngOcrError(f"{label} is required.")
    if review.get("approved") is not True or review.get("reviewer_role") != "owner":
        raise StaticPngOcrError(f"{label} must be explicitly approved by the Owner.")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise StaticPngOcrError(f"{label} must identify its reviewer.")
    if not isinstance(review.get("evidence_ref"), str) or not review["evidence_ref"].strip():
        raise StaticPngOcrError(f"{label} must cite its review evidence.")
    reviewed_at = review.get("reviewed_at")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise StaticPngOcrError(f"{label} must include an ISO-8601 review timestamp.") from exc
    if parsed.tzinfo is None:
        raise StaticPngOcrError(f"{label} timestamp must include a timezone.")


def _load_reviewed_mapping(batch: dict[str, Any], root: Path) -> dict[str, Any]:
    config_path = root / "python-engine" / "config" / "static_png_ocr_mappings.json"
    config = _read_object(config_path, "static PNG OCR mapping registry")
    if config.get("schema_version") != 1 or not isinstance(config.get("mappings"), dict):
        raise StaticPngOcrError("Static PNG OCR mapping registry schema is invalid.")
    key = batch.get("static_png_ocr_mapping_key")
    if not isinstance(key, str) or not key:
        raise StaticPngOcrError("A reviewed static_png_ocr_mapping_key is required.")
    mapping = config["mappings"].get(key)
    if not isinstance(mapping, dict) or mapping.get("enabled") is not True:
        raise StaticPngOcrError("No enabled, source-specific Tier 3 OCR mapping exists.")
    expected = {
        "source_id": batch.get("source_id"),
        "authority": batch.get("authority"),
        "exam": batch.get("exam"),
        "year": batch.get("year"),
        "official_source_url": batch.get("official_source_url"),
    }
    for field, value in expected.items():
        if mapping.get(field) != value:
            raise StaticPngOcrError(f"Tier 3 mapping does not match batch field {field}.")
    _review_is_current(mapping.get("mapping_review"), "OCR mapping review")
    _review_is_current(mapping.get("public_viewability_review"), "Public-viewability review")
    _review_is_current(mapping.get("access_compliance_review"), "Access-compliance review")
    public_viewability = mapping.get("public_viewability")
    if not isinstance(public_viewability, dict) or public_viewability.get("publicly_viewable") is not True:
        raise StaticPngOcrError("Tier 3 requires evidence that the official content is publicly viewable.")
    if not isinstance(public_viewability.get("downloadable"), bool):
        raise StaticPngOcrError("Public-viewability evidence must record downloadable as true or false.")
    if not isinstance(public_viewability.get("evidence_ref"), str) or not public_viewability["evidence_ref"].strip():
        raise StaticPngOcrError("Public-viewability evidence must cite its verification evidence.")
    if batch.get("publicly_viewable") is not True:
        raise StaticPngOcrError("Tier 3 batch does not affirm ordinary public viewability.")
    if batch.get("content_downloadable") is not public_viewability["downloadable"]:
        raise StaticPngOcrError("Tier 3 batch downloadability does not match its reviewed public-viewability evidence.")
    pattern = mapping.get("record_pattern")
    if not isinstance(pattern, str) or not pattern:
        raise StaticPngOcrError("Reviewed OCR mapping must define record_pattern.")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise StaticPngOcrError(f"Reviewed OCR record_pattern is invalid: {exc}") from exc
    if not {"sequence", "name"}.issubset(compiled.groupindex):
        raise StaticPngOcrError("OCR record_pattern must define named sequence and name groups.")
    language = mapping.get("language", "eng")
    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9_+.-]{2,40}", language):
        raise StaticPngOcrError("OCR language setting is invalid.")
    psm = mapping.get("page_segmentation_mode", 6)
    if isinstance(psm, bool) or psm not in {3, 4, 6, 11, 12, 13}:
        raise StaticPngOcrError("OCR page segmentation mode is not allowlisted.")
    return mapping


def _verify_tier1_tier2_failure(batch: dict[str, Any], root: Path) -> dict[str, Any]:
    evidence_path = _safe_file(root, batch.get("tier_failure_evidence"), "Tier 1/Tier 2 failure evidence")
    evidence = _read_object(evidence_path, "Tier 1/Tier 2 failure evidence")
    if evidence.get("source_url") != batch.get("official_source_url"):
        raise StaticPngOcrError("Tier failure evidence does not match the approved official source.")
    for tier in ("tier1_direct_text", "tier2_rendered_dom"):
        result = evidence.get(tier)
        if not isinstance(result, dict) or result.get("status") != "unavailable":
            raise StaticPngOcrError(f"Tier 3 requires documented {tier} unavailability.")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            raise StaticPngOcrError(f"{tier} failure must include a reason.")
    if evidence.get("access_challenge_detected") is not False:
        raise StaticPngOcrError("Tier 3 must stop when an access or human-verification challenge is detected.")
    return {
        "path": str(evidence_path.relative_to(root)),
        "sha256": _sha256_file(evidence_path),
    }


def _tesseract_tsv(image_path: Path, *, language: str, psm: int) -> str:
    try:
        completed = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", language, "--psm", str(psm), "tsv"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise StaticPngOcrError("Tesseract is not installed on this runner.") from exc
    except subprocess.TimeoutExpired as exc:
        raise StaticPngOcrError(f"Tesseract exceeded the 60-second per-image limit: {image_path.name}") from exc
    except subprocess.CalledProcessError as exc:
        raise StaticPngOcrError(f"Tesseract failed for {image_path.name}: {exc.stderr[-500:]}") from exc
    return completed.stdout


def _extract_lines(tsv_text: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    required = {"level", "block_num", "par_num", "line_num", "conf", "text"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise StaticPngOcrError("Tesseract output is not valid TSV with token confidence.")
    for row in reader:
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        try:
            confidence = float(row["conf"])
        except (TypeError, ValueError) as exc:
            raise StaticPngOcrError("Tesseract returned an invalid token confidence.") from exc
        key = (row.get("page_num", "1"), row["block_num"], row["par_num"], row["line_num"])
        grouped.setdefault(key, []).append({"text": row["text"].strip(), "confidence": confidence})
    lines = []
    for key in sorted(grouped, key=lambda item: tuple(int(part) for part in item)):
        tokens = grouped[key]
        lines.append({"text": " ".join(token["text"] for token in tokens), "tokens": tokens})
    return lines


def load_static_png_ocr_capture(
    *,
    batch: dict[str, Any],
    root: str | Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """OCR reviewed static PNG captures and return only fully verified records."""
    repository_root = Path(root).resolve()
    if batch.get("official_content_mode") != "static_png_ocr":
        raise StaticPngOcrError("Tier 3 OCR mode was not explicitly selected.")
    if batch.get("provenance") != "official_direct":
        raise StaticPngOcrError("Tier 3 OCR is restricted to official_direct provenance.")
    if batch.get("access_challenge_detected") is not False:
        raise StaticPngOcrError("Tier 3 OCR is forbidden after an access challenge.")
    tier_failure = _verify_tier1_tier2_failure(batch, repository_root)
    mapping = _load_reviewed_mapping(batch, repository_root)

    content_url = urlsplit(str(batch.get("official_content_url", "")))
    preview_url = urlsplit(str(batch.get("public_preview_url", "")))
    content_match = re.fullmatch(r"/file/d/([A-Za-z0-9_-]+)/view", content_url.path)
    preview_match = re.fullmatch(r"/file/d/([A-Za-z0-9_-]+)/preview", preview_url.path)
    if (
        content_url.scheme != "https"
        or content_url.hostname != "drive.google.com"
        or content_match is None
        or preview_url.scheme != "https"
        or preview_url.hostname != "drive.google.com"
        or preview_match is None
        or content_match.group(1) != preview_match.group(1)
        or content_url.username or content_url.password
        or preview_url.username or preview_url.password
    ):
        raise StaticPngOcrError("Tier 3 screenshots must be tied to the ordinary preview for the exact allowlisted official Drive file.")

    manifest_path = _safe_file(repository_root, batch.get("static_png_ocr_manifest"), "static PNG OCR manifest")
    manifest = _read_object(manifest_path, "static PNG OCR manifest")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("capture_method") != "ordinary_public_preview_ui"
        or manifest.get("source_url") != batch.get("public_preview_url")
        or manifest.get("official_content_url") != batch.get("official_content_url")
        or manifest.get("public_preview_url") != batch.get("public_preview_url")
        or manifest.get("stable_viewport") is not True
        or manifest.get("lossless_png") is not True
        or manifest.get("access_challenge_detected") is not False
    ):
        raise StaticPngOcrError("Capture manifest does not prove a stable, compliant, lossless PNG viewport.")
    screenshots = manifest.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots:
        raise StaticPngOcrError("Static PNG OCR manifest contains no screenshots.")

    expression = re.compile(mapping["record_pattern"])
    records: list[dict[str, str]] = []
    token_evidence: list[dict[str, Any]] = []
    screenshot_evidence: list[dict[str, Any]] = []
    low_confidence: list[dict[str, Any]] = []
    for page_index, item in enumerate(screenshots, start=1):
        if not isinstance(item, dict) or item.get("page") != page_index:
            raise StaticPngOcrError("Screenshot manifest has a page gap or ordering error.")
        image_path = _safe_file(repository_root, item.get("path"), "lossless PNG screenshot")
        image_bytes = image_path.read_bytes()
        if not image_bytes.startswith(PNG_SIGNATURE):
            raise StaticPngOcrError(f"Screenshot is not a PNG image: {item.get('path')}")
        image_hash = _sha256_bytes(image_bytes)
        if image_hash != item.get("sha256"):
            raise StaticPngOcrError(f"Screenshot SHA-256 mismatch on page {page_index}.")
        tsv = _tesseract_tsv(image_path, language=mapping.get("language", "eng"), psm=mapping.get("page_segmentation_mode", 6))
        tsv_hash = _sha256_bytes(tsv.encode("utf-8"))
        screenshot_evidence.append({
            "page": page_index,
            "path": str(image_path.relative_to(repository_root)),
            "screenshot_sha256": image_hash,
            "ocr_tsv_sha256": tsv_hash,
        })
        for line in _extract_lines(tsv):
            match = expression.fullmatch(line["text"])
            if match is None:
                continue
            sequence_text = match.group("sequence")
            name = match.group("name").strip()
            if not sequence_text.isdigit() or not name:
                raise StaticPngOcrError(f"OCR mapping produced an invalid record on page {page_index}.")
            for token_index, token in enumerate(line["tokens"], start=1):
                entry = {
                    "page": page_index,
                    "token_index": token_index,
                    "text": token["text"],
                    "confidence": token["confidence"],
                }
                token_evidence.append(entry)
                if token["confidence"] < MIN_TOKEN_CONFIDENCE:
                    low_confidence.append(entry)
            records.append({"sequence_number": sequence_text, "name": name})

    report: dict[str, Any] = {
        "schema_version": 1,
        "provenance": "official_direct",
        "method": "static_png_tesseract_tsv",
        "minimum_token_confidence": MIN_TOKEN_CONFIDENCE,
        "tier_failure_evidence": tier_failure,
        "mapping_key": batch.get("static_png_ocr_mapping_key"),
        "screenshots": screenshot_evidence,
        "screenshot_count": len(screenshot_evidence),
        "ocr_tokens": token_evidence,
        "low_confidence_tokens": low_confidence,
        "record_count": len(records),
        "announced_count": batch.get("announced_count"),
        "access_controls_bypassed": False,
        "video_frame_ocr": False,
        "ocr_gate_passed": False,
        "publication_allowed": False,
    }
    report_path = repository_root / "python-engine" / "artifacts" / "static-png-ocr-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if low_confidence:
        raise StaticPngOcrError(
            f"{len(low_confidence)} OCR token(s) are below 95%; candidate is held for human review. "
            f"See {report_path.relative_to(repository_root)}."
        )

    announced = batch.get("announced_count")
    if isinstance(announced, bool) or not isinstance(announced, int) or announced < 1:
        raise StaticPngOcrError("announced_count must be a positive integer.")
    if len(records) != announced:
        raise StaticPngOcrError(f"OCR record count {len(records)} does not match announced count {announced}.")
    sequences = [int(record["sequence_number"]) for record in records]
    if len(set(sequences)) != len(sequences):
        raise StaticPngOcrError("OCR output contains duplicate sequence numbers.")
    if sorted(sequences) != list(range(1, announced + 1)):
        raise StaticPngOcrError("OCR output does not provide exact sequence coverage from 1 to announced_count.")
    normalized_names = [record["name"].casefold() for record in records]
    if len(set(normalized_names)) != len(normalized_names):
        raise StaticPngOcrError("OCR output contains duplicate names.")
    report["ocr_gate_passed"] = True
    report["sequence_coverage"] = {"first": 1, "last": announced, "complete": True}
    report["records_sha256"] = _sha256_bytes(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records, {
        "report_path": str(report_path.relative_to(repository_root)),
        "report_sha256": _sha256_file(report_path),
        "screenshot_count": len(screenshot_evidence),
        "screenshot_ocr_evidence": screenshot_evidence,
        "tier_failure_evidence": tier_failure,
        "mapping_key": batch.get("static_png_ocr_mapping_key"),
    }
