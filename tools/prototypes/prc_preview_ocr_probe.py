#!/usr/bin/env python3
"""Isolated OCR alternative probe against the ordinary public PRC-linked Drive preview UI.

No PDF download, private endpoint, login, CAPTCHA solving, or access-control bypass.
Captures only the rendered page viewport and OCRs it with the independent Tesseract engine.
"""
import hashlib, json, re, subprocess, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("official-prc-ocr-probe")
OUT.mkdir(exist_ok=True)
SAMPLE_PAGES = [1, 2, 3, 368]
SEQ = re.compile(r"^\s*(\d{1,5})\s+([A-Z][A-Z ,.'’\-]+(?:\s+[A-Z][A-Z ,.'’\-]+)*)\s*$")

def blocked(text):
    low = text.lower()
    return any(x in low for x in ("request access", "sign in to continue",
        "verify you are human", "captcha", "access denied"))

def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1800, "height": 1500},
                                device_scale_factor=2)
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if (urlparse(page.url).hostname or "") not in {"drive.google.com", "docs.google.com"}:
            raise RuntimeError("Unexpected preview redirect host")
        body = page.locator("body")
        if blocked(body.inner_text() + page.content()[:100000]):
            raise RuntimeError("Public preview requires human verification or permission")
        control = page.locator('input[aria-label^="Page is"]')
        if control.count() != 1:
            raise RuntimeError("Visible page-number control unavailable")
        for number in SAMPLE_PAGES:
            if number > 1:
                control.fill(str(number))
                control.press("Enter")
                page.wait_for_function(
                    "(n) => { const e=document.querySelector('input[aria-label^=\\\"Page is\\\"]'); return e && e.getAttribute('aria-label') === 'Page is ' + n; }",
                    arg=number, timeout=15000)
                page.wait_for_timeout(1200)
            visible = body.inner_text(timeout=10000)
            if blocked(visible):
                raise RuntimeError("Access challenge appeared during pagination")
            shot = OUT / f"viewer-page-{number:03}.png"
            page.screenshot(path=str(shot), full_page=False)
            digest = hashlib.sha256(shot.read_bytes()).hexdigest()
            proc = subprocess.run(["tesseract", str(shot), "stdout", "--psm", "6"],
                                  check=True, capture_output=True, text=True, timeout=60)
            ocr = proc.stdout
            (OUT / f"viewer-page-{number:03}.txt").write_text(ocr, encoding="utf-8")
            pairs = []
            for line in ocr.splitlines():
                m = SEQ.match(line)
                if m:
                    pairs.append({"seq": int(m.group(1)), "name": " ".join(m.group(2).split())})
            results.append({"viewer_page": number, "screenshot_sha256": digest,
                "ocr_characters": len(ocr), "pairs_found": len(pairs),
                "sequence_min": min((x["seq"] for x in pairs), default=None),
                "sequence_max": max((x["seq"] for x in pairs), default=None),
                "pairs": pairs})
        browser.close()
    report = {"source": URL, "http_status": response.status if response else None,
              "technology": "Playwright visible-page screenshot + Tesseract OCR",
              "pdf_downloaded": False, "sample_pages": results}
    (OUT / "probe-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
