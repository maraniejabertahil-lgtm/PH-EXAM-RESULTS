#!/usr/bin/env python3
"""Capture selected pages from the official Secondary public-preview UI."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import sync_playwright

DRIVE_ID = "1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7"
URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("official-prc-secondary-visual-check")
EXTRACTION_REPORT = Path("official-prc-secondary-evidence/extraction-report.json")
OUT.mkdir(exist_ok=True)


def blocked(text):
    low = text.lower()
    return any(x in low for x in (
        "request access", "sign in to continue", "verify you are human",
        "captcha", "access denied"
    ))


def main():
    extraction = json.loads(EXTRACTION_REPORT.read_text(encoding="utf-8"))
    expected = extraction.get("visual_verification_evidence", {})
    targets = []
    for sequence in ("1", "45001"):
        entry = expected.get(sequence)
        if not isinstance(entry, dict):
            raise RuntimeError("Extraction report is missing first/last record visual targets")
        targets.append({
            "viewer_page": entry["viewer_page"],
            "printed_page": entry["printed_page"],
            "sequence": int(sequence),
            "expected_visible_text": f"{sequence} {entry['name']}",
        })

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="PH-EXAM-RESULTS-official-content-research/1.0 (GitHub Actions)",
            viewport={"width": 1800, "height": 1500},
            device_scale_factor=2,
        )
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if (urlparse(page.url).hostname or "") not in {"drive.google.com", "docs.google.com"}:
            raise RuntimeError("Unexpected public-preview redirect host")
        body = page.locator("body")
        initial = body.inner_text(timeout=10000)
        if blocked(initial + page.content()[:100000]):
            raise RuntimeError("Public preview requires permission or human verification")
        page_count_match = re.search(r"Page 1 of\s+(\d+)", initial)
        if not page_count_match:
            raise RuntimeError("Could not read Secondary viewer page count")
        page_count = int(page_count_match.group(1))
        if page_count < 1 or page_count > 2000:
            raise RuntimeError("Secondary viewer page count is outside safe bound")
        control = page.locator('input[aria-label^="Page is"]')
        if control.count() != 1:
            raise RuntimeError("Visible public-preview page control not found")

        for target in targets:
            number = target["viewer_page"]
            control.fill(str(number))
            control.press("Enter")
            deadline = __import__("time").monotonic() + 35
            stable_samples = 0
            previous_text = None
            visible = ""
            while __import__("time").monotonic() < deadline:
                current_value = control.input_value(timeout=3000)
                visible = body.inner_text(timeout=10000)
                if current_value == str(number) and f"Page {number} of {page_count}" in visible:
                    if visible == previous_text:
                        stable_samples += 1
                    else:
                        stable_samples = 0
                    previous_text = visible
                    if stable_samples >= 2:
                        break
                else:
                    stable_samples = 0
                    previous_text = visible
                page.wait_for_timeout(500)
            else:
                raise RuntimeError(f"Public viewer text did not stabilize on page {number}")
            if blocked(visible):
                raise RuntimeError("Access challenge appeared during page navigation")
            marker = f"Page {number} of {page_count}"
            if marker not in visible:
                raise RuntimeError(f"Viewer did not confirm requested page {number}")
            if target["expected_visible_text"] not in visible:
                raise RuntimeError(f"Expected sequence/name not exposed on viewer page {number}")
            screenshot = OUT / f"official-secondary-source-page-{target['printed_page']:04}.png"
            page.screenshot(path=str(screenshot), full_page=True, timeout=30000)
            with Image.open(screenshot) as image:
                width, height = image.size
                if width < 500 or height < 500:
                    raise RuntimeError("Captured preview screenshot is unexpectedly small")
                image.verify()
            digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
            ocr = subprocess.run(
                ["tesseract", str(screenshot), "stdout", "--psm", "6"],
                check=True, capture_output=True, text=True, timeout=60
            ).stdout
            ocr_path = OUT / f"official-secondary-source-page-{target['printed_page']:04}-ocr.txt"
            ocr_path.write_text(ocr, encoding="utf-8")
            visible_path = OUT / f"official-secondary-source-page-{target['printed_page']:04}-viewer.txt"
            visible_path.write_text(visible, encoding="utf-8")
            results.append({
                **target,
                "http_status": response.status if response else None,
                "viewer_marker": marker,
                "viewer_text_confirmed": True,
                "screenshot": str(screenshot),
                "screenshot_dimensions": [width, height],
                "screenshot_sha256": digest,
                "screenshot_bytes": screenshot.stat().st_size,
                "ocr_text_file": str(ocr_path),
                "ocr_contains_expected_name": target["expected_visible_text"] in ocr,
                "human_visual_verification": "PENDING",
            })
        browser.close()

    report = {
        "source": URL,
        "viewer_pages": page_count,
        "method": "ordinary public preview UI; visible page control; rendered viewer screenshots",
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "ocr_is_advisory_only": True,
        "human_visual_verification": "PENDING",
        "results": results,
    }
    (OUT / "visual-check-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
