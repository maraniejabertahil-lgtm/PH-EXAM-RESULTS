import re
import unicodedata


def normalize_name(value: str) -> str:
    """Build a comparison key while preserving the original display name."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def normalize_record(
    row: dict,
    authority: str,
    examination: str,
    year: int,
) -> dict:
    raw_name = row.get("name")
    original_name = "" if raw_name is None else str(raw_name).strip()
    return {
        "authority": authority.upper().strip(),
        "examination": examination.strip(),
        "year": int(year),
        "name": original_name,
        "search_key": normalize_name(original_name),
        "rating": _optional_number(row.get("rating")),
        "region": _optional_text(row.get("region")),
        "seq": _optional_integer(row.get("seq")),
    }


def _optional_text(value):
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _optional_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _optional_integer(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
