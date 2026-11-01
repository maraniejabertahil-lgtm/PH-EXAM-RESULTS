import json
from datetime import datetime, timezone
from pathlib import Path


STAGES = {
    "monitoring": (10, "Monitoring official examination sources"),
    "source_detected": (25, "Official source update detected"),
    "document_acquired": (40, "Official result document acquired"),
    "extracting": (55, "Extracting examination records"),
    "validating": (70, "Validating examination records"),
    "awaiting_approval": (90, "Awaiting owner approval"),
}


def build_status(
    mode: str,
    authority: str | None = None,
    exam: str | None = None,
    year: int | None = None,
    examination_name: str | None = None,
    stage: str | None = None,
) -> dict:
    if mode == "search":
        return {"schema_version": 1, "mode": "search", "preparation": None}
    if mode != "preparing":
        raise ValueError("mode must be search or preparing")
    if authority not in {"PRC", "CSC"}:
        raise ValueError("preparing mode requires PRC or CSC authority")
    if not exam or not str(exam).strip():
        raise ValueError("preparing mode requires an examination identifier")
    if not isinstance(year, int) or not 1900 <= year <= 2100:
        raise ValueError("preparing mode requires a valid examination year")
    if not examination_name or not examination_name.strip():
        raise ValueError("preparing mode requires a public examination name")
    if stage not in STAGES:
        raise ValueError("stage must be one of the predefined preparation stages")

    percentage, public_status = STAGES[stage]
    return {
        "schema_version": 1,
        "mode": "preparing",
        "preparation": {
            "authority": authority,
            "exam": exam,
            "year": year,
            "examination_name": examination_name.strip(),
            "stage": stage,
            "percentage": percentage,
            "status": public_status,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


def write_status(output_path: str | Path, **kwargs) -> dict:
    status = build_status(**kwargs)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status
