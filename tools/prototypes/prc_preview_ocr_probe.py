#!/usr/bin/env python3
"""Capture exact official PRC public-preview pages for human visual verification.

Uses only the ordinary public Google Drive preview UI and its visible page control.
No download endpoint, private API, login, CAPTCHA solving, or access-control bypass.
"""
import hashlib, json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("official-prc-visual-check")
OUT.mkdir(exist_ok=True)
# Viewer pages 215 and 302 correspond to printed source pages 216 and 303.
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
            viewport={"width": 1600, "height": 1200},
            device_scale_factor=1.5,
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
            n = target["viewer_page"]
            control.fill(str(n))
            control.press("Enter")
            page.wait_for_function(
                """(n) => {
                    const e = document.querySelector('input[aria-label^="Page is"]');
                    return e && e.getAttribute("aria-label") === "Page is " + n;
                }""",
                arg=n, timeout=20000,
            )
            page.wait_for_timeout(1200)
            visible = body.inner_text(timeout=10000)
            if blocked(visible):
                raise RuntimeError("Access challenge appeared during page navigation")
            marker = f"Page {n} of 368"
            if marker not in visible:
                raise RuntimeError(f"Viewer did not confirm requested page {n}")
            if target["expected_visible_text"] not in visible:
                raise RuntimeError(
                    f"Expected sequence/name text not visible on viewer page {n}"
                )
            shot = OUT / f"official-viewer-page-{n:03}.png"
            page.screenshot(path=str(shot), full_page=True, timeout=20000)
            digest = hashlib.sha256(shot.read_bytes()).hexdigest()
            text_file = OUT / f"official-viewer-page-{n:03}.txt"
            text_file.write_text(visible, encoding="utf-8")
            results.append({
                **target,
                "http_status": response.status if response else None,
                "viewer_marker": marker,
                "expected_text_visible": True,
                "screenshot": str(shot),
                "screenshot_sha256": digest,
                "screenshot_bytes": shot.stat().st_size,
            })
        browser.close()

    report = {
        "source": URL,
        "method": "ordinary public preview UI; visible page-number control; full viewport screenshot",
        "pdf_downloaded": False,
        "access_controls_bypassed": False,
        "results": results,
    }
    (OUT / "visual-check-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
