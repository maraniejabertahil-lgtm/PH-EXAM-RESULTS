"""Fail-closed publication policy for human visual review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PublicationPolicyError(ValueError):
    """Raised when source publication policy is missing or invalid."""


def requires_owner_visual_review(batch: dict[str, Any], *, root: str | Path) -> bool:
    if batch.get("official_content_mode") != "public_preview_capture":
        return False

    registry_path = Path(root) / "python-engine" / "config" / "sources.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationPolicyError(f"Cannot read publication policy: {exc}") from exc

    sources = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(sources, list):
        raise PublicationPolicyError("Publication policy source registry has an invalid schema.")
    matches = [
        item for item in sources
        if isinstance(item, dict) and item.get("id") == batch.get("source_id")
    ]
    if len(matches) != 1:
        raise PublicationPolicyError("Batch source must match exactly one publication policy.")

    source = matches[0]
    required = source.get("owner_visual_review_required_exams", [])
    automatic = source.get("auto_publish_exams", [])
    if (
        not isinstance(required, list)
        or any(not isinstance(exam, str) or not exam for exam in required)
        or not isinstance(automatic, list)
        or any(not isinstance(exam, str) or not exam for exam in automatic)
    ):
        raise PublicationPolicyError("Source visual-review publication policy is invalid.")

    exam = batch.get("exam")
    year = batch.get("year")
    exam_year = f"{exam}-{year}" if isinstance(exam, str) and isinstance(year, int) else None
    if exam in required or exam_year in required:
        return True
    return exam_year not in automatic
