#!/usr/bin/env python3
"""Low-impact DOM/performance probe for the official PRC public preview.

This probe captures structural metadata and text lengths/hashes only. It does
not save passer names, screenshots, PDFs, cookies, or private endpoint data.
Navigation uses only the ordinary visible Google Drive page-number control.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

DRIVE_ID = "1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7"
PREVIEW_URL = f"https://drive.google.com/file/d/{DRIVE_ID}/preview"
OUT = Path("secondary-page-local-probe")
OUT.mkdir(exist_ok=True)
UA = "PH-EXAM-RESULTS-public-preview-diagnostic/1.0 (GitHub Actions)"
CHALLENGES = ("request access", "sign in to continue", "verify you are human", "captcha", "access denied")

DOM_INVENTORY = r"""
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const nodes = [...document.querySelectorAll("div,span,p,section,article,main")]
    .filter(el => visible(el))
    .map(el => {
      const text = el.innerText || "";
      const r = el.getBoundingClientRect();
      const directText = [...el.childNodes]
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .reduce((n, x) => n + (x.textContent || "").length, 0);
      const classes = [...el.classList].slice(0, 5);
      return {
        tag: el.tagName.toLowerCase(),
        id: el.id || "",
        classes,
        role: el.getAttribute("role") || "",
        ariaLabel: el.getAttribute("aria-label") || "",
        textLength: text.length,
        directTextLength: directText,
        childCount: el.children.length,
        width: Math.round(r.width),
        height: Math.round(r.height)
      };
    })
    .filter(x => x.textLength >= 40)
    .sort((a, b) => b.textLength - a.textLength)
    .slice(0, 35);
  return {
    bodyTextLength: (document.body && document.body.innerText || "").length,
    elementCount: document.querySelectorAll("*").length,
    iframeCount: document.querySelectorAll("iframe").length,
    nodes
  };
}
"""

def main() -> None:
    records = []
    started = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=UA,
            viewport={"width": 1440, "height": 1000},
        )
        response = page.goto(PREVIEW_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        host = urlparse(page.url).hostname or ""
        if host not in {"drive.google.com", "docs.google.com"}:
            raise RuntimeError(f"Unexpected preview host: {host}")
        if response and response.status >= 400:
            raise RuntimeError(f"Preview returned HTTP {response.status}")

        body = page.locator("body")
        initial = body.inner_text(timeout=10000)
        low = initial.lower() + page.title().lower()
        if any(term in low for term in CHALLENGES):
            raise RuntimeError("Public preview displayed an access challenge")
        match = re.search(r"Page 1 of\s+(\d+)", initial)
        if not match:
            raise RuntimeError("Could not read page count from visible preview")
        page_count = int(match.group(1))
        if not 1 <= page_count <= 2000:
            raise RuntimeError(f"Page count outside safety bound: {page_count}")
        control = page.locator('input[aria-label^="Page is"]')
        if control.count() != 1:
            raise RuntimeError("Visible page-number control not found")

        requested = sorted({1, 2, 50, 100, 225, 450, 675, 850, 900, page_count})
        requested = [n for n in requested if 1 <= n <= page_count]
        for number in requested:
            if number != 1:
                control.click()
                control.fill(str(number))
                control.press("Enter")

            marker = f"Page {number} of {page_count}"
            deadline = time.perf_counter() + 25
            previous = None
            stable = 0
            body_read_ms = []
            text = ""
            while time.perf_counter() < deadline:
                tick = time.perf_counter()
                text = body.inner_text(timeout=10000)
                body_read_ms.append((time.perf_counter() - tick) * 1000)
                if marker in text and control.input_value(timeout=3000) == str(number):
                    if text == previous:
                        stable += 1
                    else:
                        stable = 0
                    previous = text
                    if stable >= 1:
                        break
                else:
                    stable = 0
                    previous = text
                page.wait_for_timeout(150)
            else:
                raise RuntimeError(f"Visible text did not stabilize at page {number}")

            if any(term in text.lower() for term in CHALLENGES):
                raise RuntimeError("Access challenge appeared during navigation")

            inventory_started = time.perf_counter()
            inventory = page.evaluate(DOM_INVENTORY)
            inventory_ms = (time.perf_counter() - inventory_started) * 1000
            item = {
                "requested_page": number,
                "page_marker_confirmed": marker in text,
                "page_input_confirmed": control.input_value() == str(number),
                "body_text_characters": len(text),
                "body_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "body_inner_text_calls": len(body_read_ms),
                "body_inner_text_total_ms": round(sum(body_read_ms), 2),
                "body_inner_text_max_ms": round(max(body_read_ms), 2),
                "dom_inventory_ms": round(inventory_ms, 2),
                "dom": inventory,
            }
            records.append(item)
            print(
                f"[probe] page={number}/{page_count} body_chars={len(text)} "
                f"inner_text_ms={item['body_inner_text_total_ms']:.1f} "
                f"inventory_ms={inventory_ms:.1f}",
                flush=True,
            )
            page.wait_for_timeout(500)

        browser.close()

    report = {
        "source": "official_prc_linked_public_preview",
        "preview_url": PREVIEW_URL,
        "page_count": page_count,
        "sampled_pages": requested,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "captures_content": False,
        "stores_names_or_records": False,
        "stores_pdf_or_screenshots": False,
        "access_method": "ordinary public preview UI and visible page-number input",
        "samples": records,
    }
    (OUT / "dom-performance-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))

if __name__ == "__main__":
    main()
