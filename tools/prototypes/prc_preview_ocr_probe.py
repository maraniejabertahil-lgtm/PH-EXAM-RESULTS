#!/usr/bin/env python3
"""Capture official PRC preview pages for human visual review.

Uses only the ordinary public Google Drive preview UI and visible page-number control.
No PDF download endpoint, private API, login, CAPTCHA solving, or access-control bypass.
Viewer text confirms navigation only. OCR is advisory and never changes a record.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from playwright.sync_api import sync_playwright

DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("official-prc-visual-check")
OUT.mkdir(exist_ok=True)
TARGETS = [
    {"viewer_page": 215, "printed_page": 216, "sequence": 10710,
     "expected_visible_text": "10710 MAGANGCONG, MUHAMMAD_THANI PAUTE"},
    {"viewer_page": 302, "printed_page": 303, "sequence": 15066,
     "expected_visible_text": "15066 ROBLES, D9 BASUG"},
]

def blocked(text):
    low = text.lower()
    return any(x in low for x in (
        "request access", "sign in to continue", "verify you are human",
        "captcha", "access denied"
    ))

def main():
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
        control = page.locator('input[aria-label^="Page is"]')
        if control.count() != 1:
            raise RuntimeError("Visible public-preview page control not found")

        for target in TARGETS:
            number = target["viewer_page"]
            control.fill(str(number))
            control.press("Enter")
            page.wait_for_function(
                """(n) => {
                    const e = document.querySelector('input[aria-label^="Page is"]');
                    return e && e.getAttribute("aria-label") === "Page is " + n;
                }""",
                arg=number, timeout=20000,
            )
            page.wait_for_timeout(1500)
            visible = body.inner_text(timeout=10000)
            if blocked(visible):
                raise RuntimeError("Access challenge appeared during page navigation")
            marker = f"Page {number} of 368"
            if marker not in visible:
                raise RuntimeError(f"Viewer did not confirm requested page {number}")
            if target["expected_visible_text"] not in visible:
                raise RuntimeError(
                    f"Expected sequence/name not exposed by viewer text on page {number}"
                )

            # Full viewer screenshot includes the rendered document page even when
            # Google hosts its page canvas inside an inaccessible nested frame.
            screenshot = OUT / f"official-source-page-{target['printed_page']:03}.png"
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
            ocr_path = OUT / f"official-source-page-{target['printed_page']:03}-ocr.txt"
            ocr_path.write_text(ocr, encoding="utf-8")
            visible_path = OUT / f"official-source-page-{target['printed_page']:03}-viewer.txt"
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
        "method": "ordinary public preview UI; visible page control; full-page rendered viewer screenshot",
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
