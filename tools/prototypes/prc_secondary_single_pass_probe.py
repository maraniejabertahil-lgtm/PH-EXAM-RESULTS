#!/usr/bin/env python3
"""Measure whether the ordinary public Google Drive preview exposes the full
official result text in one browser load.

This is a read-only experiment: no PDF download, private API, undocumented URL,
access-control bypass, or publication. An incomplete capture is reported as a
failed experiment and is never accepted as a dataset.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

URL = "https://drive.google.com/file/d/1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7/preview"
EXPECTED = 45001
EXPECTED_FIRST = "AALA, ROSARIO FABELLAR"
EXPECTED_LAST = "ZURITA, JAYSON RIVERA"
OUT = Path("official-prc-secondary-one-pass-prototype")
UA = "PH-EXAM-RESULTS-official-content-research/1.0 (GitHub Actions)"
LINE = re.compile(r"^\s*(\d{1,5})[.)]?\s+(.+?)\s*$")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=UA, viewport={"width": 1600, "height": 1200}
        )
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        final_url = page.url
        host = urlparse(final_url).hostname or ""
        if host not in {"drive.google.com", "docs.google.com"}:
            browser.close()
            raise RuntimeError("Unexpected public-preview redirect host: " + host)
        text = page.locator("body").inner_text(timeout=20000)
        html = page.content()
        screenshot_path = OUT / "single-pass-preview.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        browser.close()

    lowered = (text + html[:100000]).lower()
    if any(term in lowered for term in (
        "request access", "sign in to continue", "verify you are human",
        "captcha", "access denied"
    )):
        raise RuntimeError("Public preview presented an access challenge; no bypass attempted")

    records: dict[int, str] = {}
    duplicates: list[int] = []
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        sequence = int(match.group(1))
        name = " ".join(match.group(2).split()).strip(" .")
        if not 1 <= sequence <= EXPECTED or len(name) < 5:
            continue
        if sequence in records and records[sequence] != name:
            duplicates.append(sequence)
        else:
            records[sequence] = name

    missing = sorted(set(range(1, EXPECTED + 1)) - set(records))
    first_ok = records.get(1) == EXPECTED_FIRST
    last_ok = records.get(EXPECTED) == EXPECTED_LAST
    text_path = OUT / "single-pass-visible-text.txt"
    text_path.write_text(text, encoding="utf-8")
    # The screenshot and text are captured from the same single browser load.
    screenshot_bytes = screenshot_path.read_bytes()
    page_screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()
    elapsed = round(time.perf_counter() - started, 3)
    passed = (
        len(records) == EXPECTED and not missing and not duplicates
        and first_ok and last_ok
    )
    report = {
        "schema_version": 1,
        "experiment": "ordinary_public_preview_single_pass",
        "started_at_utc": started_at,
        "elapsed_seconds": elapsed,
        "http_status": response.status if response else None,
        "requested_url": URL,
        "final_url": final_url,
        "redirect_host": host,
        "access_controls_bypassed": False,
        "pdf_downloaded": False,
        "viewer_page_indicator": re.search(r"Page\s+\d+\s+of\s+\d+", text).group(0)
            if re.search(r"Page\s+\d+\s+of\s+\d+", text) else None,
        "visible_text_characters": len(text),
        "unique_sequences_found_in_one_load": len(records),
        "announced_sequences": EXPECTED,
        "missing_sequence_count": len(missing),
        "missing_sequence_sample": missing[:30],
        "conflicting_sequence_count": len(set(duplicates)),
        "first_record_match": first_ok,
        "last_record_match": last_ok,
        "visible_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "screenshot_path": str(screenshot_path),
        "screenshot_sha256": page_screenshot_hash,
        "one_pass_coverage_complete": passed,
        "publication_performed": False,
        "note": "This experiment does not replace the proven fallback or authorize publication."
    }
    (OUT / "single-pass-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

