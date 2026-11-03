#!/usr/bin/env python3
"""
PRC March 2026 LEPT Secondary — native PDF extraction (speed-optimized).

Acquisition:
    Accepts a locally supplied, officially obtained PDF (--pdf).
    Does not download anything and does not use browser automation.

Extraction:
    PyMuPDF native text extraction, no OCR, page ranges parsed in parallel.

Validation (unchanged, fail closed):
    - Exactly 45,001 unique sequences, coverage 1..45,001.
    - No duplicate or conflicting sequence entries.
    - Exact first and last expected names.
    - JSON is written only after every check passes (atomic replace).

Speed design:
    - ProcessPoolExecutor; each worker opens the PDF ONCE (initializer) and
      parses many page ranges.
    - sort=False first (no layout sorting). If any integrity check fails, one
      automatic retry with sort=True (the original behavior) before failing.
    - Regex runs per page inside the worker; no giant joined string.
    - Names are normalized in the worker; results return as compact lists.
    - JSON is built as one string and written once, byte-identical to
      json.dump(..., ensure_ascii=False, indent=2).

Usage:
    python tools/prc-official-lept-secondary-2026-fast.py \
        --pdf manual-drop/prc-secondary-2026.pdf [--workers N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

EXPECTED_COUNT = 45_001
EXPECTED_FIRST = "AALA, ROSARIO FABELLAR"
EXPECTED_LAST = "ZURITA, JAYSON RIVERA"

DEFAULT_OUTPUT = Path("python-engine/artifacts/dataset/prc_secondary_results.json")

# Same pattern as the original script.
RECORD_PATTERN = re.compile(
    r"^\s*(\d{1,5})\s+([A-ZÑ\s,\.\-\']+?)(?=\s{2,}|\n|$)",
    re.MULTILINE,
)
_FINDALL = RECORD_PATTERN.findall  # findall returns (seq, name) tuples without match objects


class EmptyPageError(ValueError):
    """A page had no native text; OCR is disabled so this must fail closed."""


# --------------------------------------------------------------------------
# Worker side
# --------------------------------------------------------------------------

_DOC = None  # per-process document handle, opened once by the initializer


def _init_worker(pdf_path: str) -> None:
    global _DOC
    _DOC = fitz.open(pdf_path)


def _parse_range(job: Tuple[int, int, bool]):
    """Extract and parse pages [start, end). Returns (start, records, empty_page)."""
    start, end, sort = job
    doc = _DOC
    out: List[Tuple[int, str]] = []
    append = out.append
    for i in range(start, end):
        text = doc[i].get_text("text", sort=sort)
        if not text.strip():
            return start, None, i + 1  # 1-based page number
        for seq, name in _FINDALL(text):
            # str.split() with no args collapses all whitespace runs in C.
            append((int(seq), " ".join(name.split())))
    return start, out, None


# --------------------------------------------------------------------------
# Main-process side
# --------------------------------------------------------------------------

def preflight(pdf_path: Path) -> int:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.stat().st_size == 0:
        raise ValueError("The supplied PDF is empty.")
    with pdf_path.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise ValueError("Input file does not have a valid PDF signature.")
    doc = fitz.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError("The PDF is encrypted. Do not attempt to bypass its protection.")
        if doc.page_count == 0:
            raise ValueError("The PDF contains no pages.")
        return doc.page_count
    finally:
        doc.close()


def extract_records(pdf_path: Path, pages: int, workers: int, sort: bool) -> Dict[int, str]:
    # ~4 chunks per worker balances load without many tiny tasks.
    chunk = max(1, -(-pages // (workers * 4)))
    jobs = [(s, min(s + chunk, pages), sort) for s in range(0, pages, chunk)]

    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(str(pdf_path),)
        ) as pool:
            results = list(pool.map(_parse_range, jobs))  # preserves page order
    else:
        _init_worker(str(pdf_path))
        results = [_parse_range(j) for j in jobs]

    records: Dict[int, str] = {}
    duplicates: List[int] = []
    conflicts: List[dict] = []
    get = records.get

    for _, parsed, empty_page in results:
        if empty_page is not None:
            raise EmptyPageError(
                f"Page {empty_page} contains no extractable native text. "
                "OCR is disabled; manual review is required."
            )
        for seq, name in parsed:
            if not name or not 1 <= seq <= EXPECTED_COUNT:
                continue
            prev = get(seq)
            if prev is not None:
                duplicates.append(seq)
                if prev != name:
                    conflicts.append({"sequence": seq, "first_name": prev, "second_name": name})
                continue
            records[seq] = name

    if duplicates:
        raise ValueError(f"Duplicate sequence entries detected: {sorted(set(duplicates))[:30]}")
    if conflicts:
        raise ValueError(f"Conflicting names for sequence numbers: {conflicts[:10]}")
    return records


def validate_records(records: Dict[int, str]) -> None:
    """Fail closed unless every required integrity check passes."""
    assert len(records) == EXPECTED_COUNT, (
        f"Expected {EXPECTED_COUNT:,} unique records; found {len(records):,}."
    )
    expected = set(range(1, EXPECTED_COUNT + 1))
    actual = set(records)
    assert actual == expected, (
        "Sequence coverage is incomplete or contains unexpected values. "
        f"Missing sample: {sorted(expected - actual)[:20]}; "
        f"unexpected sample: {sorted(actual - expected)[:20]}"
    )
    assert records[1] == EXPECTED_FIRST, f"First record mismatch: {records[1]!r}"
    assert records[EXPECTED_COUNT] == EXPECTED_LAST, (
        f"Last record mismatch: {records[EXPECTED_COUNT]!r}"
    )
    assert all(isinstance(n, str) and n.strip() for n in records.values()), (
        "Invalid sequence key or blank name detected."
    )


def save_json(records: Dict[int, str], output_path: Path) -> None:
    """
    Write validated records atomically.

    Output is byte-identical to
    json.dump({seq: name}, f, ensure_ascii=False, indent=2) + "\\n",
    but built as a single string and written once.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dumps = json.dumps
    body = ",\n".join(
        f'  "{seq}": {dumps(records[seq], ensure_ascii=False)}' for seq in sorted(records)
    )
    data = ("{\n" + body + "\n}\n").encode("utf-8")

    tmp: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=output_path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp = Path(f.name)
            f.write(data)  # single write; no fsync, the atomic rename is what matters here
        tmp.replace(output_path)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract and validate PRC LEPT Secondary 2026 results (fast)."
    )
    ap.add_argument("--pdf", required=True, type=Path, help="Officially obtained local PDF.")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()
    started = time.perf_counter()

    try:
        print(f"Reading PDF: {args.pdf}")
        pages = preflight(args.pdf)
        workers = max(1, min(args.workers, pages))
        t_pre = time.perf_counter()

        try:
            records = extract_records(args.pdf, pages, workers, sort=False)
            validate_records(records)
            mode = "unsorted (fast path)"
        except EmptyPageError:
            raise
        except (AssertionError, ValueError) as fast_error:
            print(f"Fast path failed integrity checks ({fast_error}); retrying with sort=True.")
            records = extract_records(args.pdf, pages, workers, sort=True)
            validate_records(records)
            mode = "sorted (fallback)"
        t_ext = time.perf_counter()

        save_json(records, args.output)
        done = time.perf_counter()

        print("All integrity assertions passed.")
        print("\nVALIDATION SUCCESS")
        print(f"Records: {len(records):,}")
        print(f"Sequence 1: {records[1]}")
        print(f"Sequence {EXPECTED_COUNT}: {records[EXPECTED_COUNT]}")
        print(f"JSON output: {args.output}")
        print(f"Mode: {mode}; pages: {pages}; workers: {workers}")
        print(
            f"Timing: preflight {t_pre - started:.3f}s | extract+validate {t_ext - t_pre:.3f}s "
            f"| write {done - t_ext:.3f}s | total {done - started:.3f}s"
        )
        return 0

    except Exception as error:
        print(f"\nEXTRACTION FAILED — NO NEW DATASET WRITTEN\n{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
