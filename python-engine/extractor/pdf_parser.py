"""Extract raw text and detected tables from an already-acquired PDF.

This module intentionally performs no network access, OCR, name correction,
sequence inference, validation, or publication. It preserves the source text
and table cell order so later processor/Greenlight stages can make decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber


class PDFExtractionError(RuntimeError):
    """Base error for local PDF extraction failures."""


class InvalidPDFError(PDFExtractionError):
    """Raised when the input is not a recognizable PDF file."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_pdf_signature(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            header = stream.read(1024)
    except OSError as exc:
        raise PDFExtractionError(f"Cannot read input PDF: {exc}") from exc
    if b"%PDF-" not in header:
        raise InvalidPDFError("Input does not contain a PDF signature in its first 1,024 bytes.")


def extract_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Return raw per-page text and table cells from a local PDF file.

    The function never downloads files and never guesses column meanings.
    Table rows are preserved in their detected order, with cells left as
    extracted by pdfplumber. A parser failure is fatal rather than returning a
    partial result that could be mistaken for a complete extraction.
    """
    path = Path(pdf_path).expanduser()
    if not path.exists() or not path.is_file():
        raise PDFExtractionError(f"PDF input does not exist or is not a file: {path}")

    _verify_pdf_signature(path)

    pages: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            if not pdf.pages:
                raise InvalidPDFError("PDF contains no pages.")
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(layout=False) or ""
                tables = page.extract_tables() or []
                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "tables": tables,
                    }
                )
    except PDFExtractionError:
        raise
    except Exception as exc:  # pdfminer/pdfplumber expose several parser-specific exceptions
        raise PDFExtractionError(f"Unable to parse PDF {path.name}: {exc}") from exc

    try:
        file_size = path.stat().st_size
        file_sha256 = _sha256_file(path)
    except OSError as exc:
        raise PDFExtractionError(f"Unable to fingerprint extracted PDF: {exc}") from exc

    return {
        "schema_version": 1,
        "extraction_status": "raw_extraction_complete",
        "source_file_name": path.name,
        "source_file_size_bytes": file_size,
        "source_file_sha256": file_sha256,
        "page_count": len(pages),
        "pages": pages,
        "limitations": [
            "Raw extraction only; no OCR was performed.",
            "No passer names or sequence numbers were inferred or corrected.",
            "No Greenlight validation or publication was performed.",
        ],
    }


def tables_to_dataframes(extraction: dict[str, Any]) -> list[pd.DataFrame]:
    """Convert detected raw tables to DataFrames without treating row 1 as headers."""
    frames: list[pd.DataFrame] = []
    for page in extraction.get("pages", []):
        for table in page.get("tables", []):
            if not table:
                continue
            rows = [list(row or []) for row in table]
            width = max((len(row) for row in rows), default=0)
            if width == 0:
                continue
            columns = [f"column_{index}" for index in range(1, width + 1)]
            padded_rows = [row + [None] * (width - len(row)) for row in rows]
            # String dtype prevents pandas from silently converting IDs or
            # sequence values into numeric types and losing leading zeroes.
            frames.append(pd.DataFrame(padded_rows, columns=columns, dtype="string"))
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract raw text and tables from a local PDF.")
    parser.add_argument("pdf", help="Path to an already-acquired PDF file")
    parser.add_argument("--output", help="Optional JSON output path; stdout is used when omitted")
    args = parser.parse_args()

    result = extract_pdf(args.pdf)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
