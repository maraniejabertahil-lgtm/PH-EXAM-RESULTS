#!/usr/bin/env python3
"""Independently verify first/last PRC records in the ordinary public Drive preview.

The verifier deliberately does not download the source PDF or use private endpoints.
It checks the visible viewer page, captures a screenshot, validates the image, and
records a SHA-256 digest. OCR is advisory only; human review remains pending.
"""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import sync_playwright

DRIVE_ID = "1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7"
URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("official-prc-secondary-visual-check")
EXTRACTION_REPORT = Path("official-prc-secondary-evidence/extraction-report.json")
USER_AGENT = "PH-EXAM-RESULTS-official-content-research/1.0 (GitHub Actions)"
VIEWPORT = {"width": 1800, "height": 1500}
OUT.mkdir(exist_ok=True)


def blocked(text):
    low = text.lower()
    return any(x in low for x in (
        "request access", "sign in to continue", "verify you are human",
        "captcha", "access denied"
    ))


def target_line_present(text, sequence, name):
    """Match a complete visible sequence/name line, tolerating whitespace only."""
    pattern = re.compile(rf"(?m)^\s*{sequence}\s+{re.escape(name)}\s*$")
    return bool(pattern.search(text))


def viewer_page_confirmed(text, page_number, page_count):
    return bool(re.search(
        rf"\bPage\s+{page_number}\s+of\s+{page_count}\b", text
    ))


def wait_for_target_page(page, body, control, page_number, page_count, sequence, name):
    """Wait for both the visible page indicator and exact target line to appear."""
    deadline = time.monotonic() + 45
    last = ""
    stable = 0
    previous_signature = None
    while time.monotonic() < deadline:
        current_page = control.input_value(timeout=5000).strip()
        last = body.inner_text(timeout=15000)
        signature = (
            current_page,
            viewer_page_confirmed(last, page_number, page_count),
            target_line_present(last, sequence, name),
        )
        if current_page == str(page_number) and signature[1] and signature[2]:
            if signature == previous_signature:
                stable += 1
            else:
                stable = 0
            if stable >= 2:
                if blocked(last + page.content()[:100000]):
                    raise RuntimeError("Access challenge appeared during page verification")
                return last
        else:
            stable = 0
        previous_signature = signature
        page.wait_for_timeout(400)
    diagnostic = {
        "requested_page": page_number,
        "viewer_control_value": control.input_value(timeout=5000),
        "page_marker_seen": viewer_page_confirmed(last, page_number, page_count),
        "target_line_seen": target_line_present(last, sequence, name),
        "visible_text_excerpt": last[-5000:],
        "url": page.url,
    }
    raise RuntimeError(
        "Target page did not independently verify: "
        + json.dumps(diagnostic, ensure_ascii=False)
    )


def main():
    extraction = json.loads(EXTRACTION_REPORT.read_text(encoding="utf-8"))
    expected = extraction.get("visual_verification_evidence", {})
    targets = []
    for sequence in ("1", "45001"):
        entry = expected.get(sequence)
        if not isinstance(entry, dict) or not entry.get("name"):
            raise RuntimeError("Extraction report is missing first/last record visual targets")
        targets.append({
            "viewer_page": int(entry["viewer_page"]),
            "printed_page": int(entry["printed_page"]),
            "sequence": int(sequence),
            "name": entry["name"],
        })

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            device_scale_factor=2,
        )
        page = context.new_page()
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        host = urlparse(page.url).hostname or ""
        if host not in {"drive.google.com", "docs.google.com"}:
            raise RuntimeError("Unexpected public-preview redirect host: " + host)
        body = page.locator("body")
        initial = body.inner_text(timeout=15000)
        if blocked(initial + page.content()[:100000]):
            raise RuntimeError("Public preview requires permission or human verification")
        page_count_match = re.search(r"Page\s+1\s+of\s+(\d+)", initial)
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
            if not 1 <= number <= page_count:
                raise RuntimeError(
                    f"Target viewer page {number} is outside page count {page_count}"
                )

            # Page 1 is already selected on initial load. Do not submit it again:
            # doing so can reset the text layer while the verification samples it.
            current = control.input_value(timeout=5000).strip()
            if current != str(number):
                control.fill(str(number))
                control.press("Enter")

            visible = wait_for_target_page(
                page, body, control, number, page_count,
                target["sequence"], target["name"]
            )
            screenshot = OUT / f"official-secondary-source-page-{target['printed_page']:04}.png"
            page.screenshot(
                path=str(screenshot), full_page=False,
                animations="disabled", timeout=30000
            )
            with Image.open(screenshot) as image:
                width, height = image.size
                image.verify()
            if width < 500 or height < 500:
                raise RuntimeError("Captured preview screenshot is unexpectedly small")
            screenshot_bytes = screenshot.read_bytes()
            if not screenshot_bytes:
                raise RuntimeError("Captured preview screenshot is empty")
            digest = hashlib.sha256(screenshot_bytes).hexdigest()

            # OCR is an advisory cross-check, never a substitute for visible text.
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
                "viewer_marker_confirmed": viewer_page_confirmed(visible, number, page_count),
                "viewer_text_confirmed": target_line_present(
                    visible, target["sequence"], target["name"]
                ),
                "screenshot": str(screenshot),
                "screenshot_dimensions": [width, height],
                "screenshot_sha256": digest,
                "screenshot_bytes": len(screenshot_bytes),
                "ocr_text_file": str(ocr_path),
                "ocr_contains_expected_name": target["name"] in ocr,
                "human_visual_verification": "PENDING",
            })
        context.close()
        browser.close()

    if len(results) != 2 or any(not item["screenshot_sha256"] for item in results):
        raise RuntimeError("Both target screenshots and hashes are mandatory")

    report = {
        "source": URL,
        "viewer_pages": page_count,
        "method": (
            "ordinary public preview UI; current page control; exact visible "
            "sequence/name line; rendered viewer screenshots"
        ),
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "visible_text_is_primary_evidence": True,
        "ocr_is_advisory_only": True,
        "human_visual_verification": "PENDING",
        "results": results,
    }
    (OUT / "visual-check-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Carry independent screenshot digests into extraction evidence. This does
    # not certify human review or alter candidate/Greenlight/publication status.
    for item in results:
        evidence = extraction["visual_verification_evidence"][str(item["sequence"])]
        evidence["screenshot_sha256"] = item["screenshot_sha256"]
        evidence["screenshot"] = item["screenshot"]
    extraction["visual_human_review_status"] = "PENDING"
    EXTRACTION_REPORT.write_text(
        json.dumps(extraction, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
