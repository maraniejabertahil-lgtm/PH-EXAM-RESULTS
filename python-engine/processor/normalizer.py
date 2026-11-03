"""Normalize PDF tables using an explicit, reviewed column map. No guessing or renumbering."""
from typing import Any


class NormalizationError(ValueError):
    pass


def normalize_extracted_tables(extraction: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(extraction, dict) or not isinstance(mapping, dict):
        raise NormalizationError("Extraction and mapping must be objects.")
    pages = extraction.get("pages")
    indexes = mapping.get("table_indexes")
    headers = mapping.get("header_rows", 0)
    if not isinstance(pages, list) or not pages:
        raise NormalizationError("No extracted pages.")
    if not isinstance(indexes, list) or not indexes or any(
        isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in indexes
    ) or len(set(indexes)) != len(indexes):
        raise NormalizationError("table_indexes must be unique non-negative integers.")
    if isinstance(headers, bool) or not isinstance(headers, int) or headers < 0:
        raise NormalizationError("header_rows must be a non-negative integer.")

    def column(key: str, required: bool = False):
        value = mapping.get(key)
        if value is None and not required:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise NormalizationError(f"{key} must be a non-negative zero-based column index.")
        return value

    name_col = column("name_column", True)
    seq_col = column("sequence_column", True)
    rating_col = column("rating_column")
    region_col = column("region_column")
    columns = [x for x in (name_col, seq_col, rating_col, region_col) if x is not None]
    if len(columns) != len(set(columns)):
        raise NormalizationError("Mapped fields must use distinct source columns.")
    width = max(columns) + 1
    output = []
    selected = 0

    for page_no, page in enumerate(pages, 1):
        if not isinstance(page, dict) or not isinstance(page.get("tables"), list):
            raise NormalizationError(f"Invalid table structure on page {page_no}.")
        tables = page["tables"]
        for table_index in indexes:
            if table_index >= len(tables):
                continue
            table = tables[table_index]
            if not isinstance(table, list):
                raise NormalizationError(f"Invalid table {table_index} on page {page_no}.")
            selected += 1
            for row_no, row in enumerate(table[headers:], headers + 1):
                if not isinstance(row, (list, tuple)):
                    raise NormalizationError(f"Invalid row {row_no} on page {page_no}.")
                if all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row):
                    continue
                if len(row) < width:
                    raise NormalizationError(f"Row {row_no} on page {page_no} is shorter than the mapping.")
                name, sequence = row[name_col], row[seq_col]
                if not isinstance(name, str) or not name.strip():
                    raise NormalizationError(f"Missing name on page {page_no}, row {row_no}.")
                if isinstance(sequence, bool) or not isinstance(sequence, (str, int)) or not str(sequence).strip():
                    raise NormalizationError(f"Missing sequence on page {page_no}, row {row_no}.")
                record = {"name": name, "sequence_number": str(sequence).strip()}
                if rating_col is not None:
                    value = row[rating_col]
                    record["rating"] = None if value is None or not str(value).strip() else str(value).strip()
                if region_col is not None:
                    value = row[region_col]
                    record["region"] = None if value is None or not str(value).strip() else str(value).strip()
                output.append(record)

    if selected == 0:
        raise NormalizationError("Configured table indexes were not found.")
    if not output:
        raise NormalizationError("The mapping produced no records.")
    return output
