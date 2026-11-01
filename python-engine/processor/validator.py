import re


def validate_record(record: dict) -> list[str]:
    errors = []

    if record.get("authority") not in {"PRC", "CSC"}:
        errors.append("authority must be PRC or CSC")
    if not isinstance(record.get("examination"), str) or not record["examination"].strip():
        errors.append("examination is required")
    if not isinstance(record.get("year"), int) or not 1900 <= record["year"] <= 2100:
        errors.append("year must be a valid four-digit year")
    if not isinstance(record.get("name"), str) or not record["name"].strip():
        errors.append("name is required")
    if not isinstance(record.get("search_key"), str) or not record["search_key"].strip():
        errors.append("normalized search key is required")

    rating = record.get("rating")
    if rating is not None:
        try:
            number = float(rating)
            if not 0 <= number <= 100:
                errors.append("rating must be between 0 and 100")
        except (TypeError, ValueError):
            errors.append("rating must be numeric")

    seq = record.get("seq")
    if seq is not None and (not isinstance(seq, int) or seq < 0):
        errors.append("seq must be a non-negative integer")

    return errors


def validate_batch(records: list[dict]) -> dict:
    invalid = []
    for index, record in enumerate(records):
        errors = validate_record(record)
        if errors:
            invalid.append({"index": index, "errors": errors})
    return {
        "total_records": len(records),
        "valid_records": len(records) - len(invalid),
        "invalid_records": invalid,
        "is_valid": not invalid and bool(records),
    }
