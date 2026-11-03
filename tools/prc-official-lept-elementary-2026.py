#!/usr/bin/env python3
import hashlib, json, re, sys, unicodedata
from datetime import datetime, timezone
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

ARTICLES = [
    "https://www.prc.gov.ph/index.php/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39",
    "https://www.prc.gov.ph/index.php/article/top-10-march-2026-lept-elementary-level-announced",
    "https://prc.gov.ph/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39",
]
DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
EXPECTED = 18376
OUT = Path("official-prc-evidence")
OUT.mkdir(exist_ok=True)
UA = "PH-EXAM-RESULTS-official-content-research/1.0 (GitHub Actions)"
opener = build_opener(HTTPCookieProcessor(CookieJar()))
events = []

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.items.append(href)

def fetch(url, limit=50 * 1024 * 1024):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*", "Accept-Language": "en-US,en;q=0.9", "Cache-Control": "no-cache"})
    with opener.open(req, timeout=35) as response:
        final = response.geturl()
        host = urlparse(final).hostname or ""
        allowed = host == "prc.gov.ph" or host.endswith(".prc.gov.ph") or host == "drive.google.com" or host == "drive.usercontent.google.com" or host.endswith(".googleusercontent.com")
        if not allowed:
            raise RuntimeError("Unexpected redirect host: " + host)
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("Response exceeded size limit")
        return data, {"status": response.status, "content_type": response.headers.get("Content-Type", ""), "final_url": final}

def log(stage, **fields):
    events.append({"time_utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **fields})

def fetch_with_retries(url, limit):
    last = None
    for attempt in range(1, 4):
        try:
            data, meta = fetch(url, limit)
            log("http_fetch_success", url=url, attempt=attempt, **meta)
            return data, meta
        except Exception as error:
            last = error
            log("http_fetch_retry", url=url, attempt=attempt, error=repr(error))
            if attempt < 3:
                time.sleep(attempt * 4)
    raise last

def browser_fetch(url):
    """Render an official public page in ordinary Chromium; never solve access challenges."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1000)
        final_url = page.url
        status = response.status if response else None
        body_text = page.locator("body").inner_text(timeout=10000)
        html = page.content().encode("utf-8")
        browser.close()
        if not (urlparse(final_url).hostname or "").endswith("prc.gov.ph"):
            raise RuntimeError("Unexpected official-page redirect host")
        low = body_text.lower()
        if any(x in low for x in ("captcha", "verify you are human", "request access", "sign in to continue", "access denied")):
            raise RuntimeError("Official page requires human verification or access")
        if status and status >= 400:
            raise RuntimeError("Official page HTTP " + str(status))
        return html, {"status": status, "content_type": "text/html; browser=chromium", "final_url": final_url}

def main():
    article = None
    article_url = None
    last_error = None
    for candidate in ARTICLES:
        try:
            article, meta = fetch_with_retries(candidate, 8 * 1024 * 1024)
            article_url = candidate
            break
        except Exception as error:
            last_error = error
    if article is None:
        for candidate in ARTICLES:
            try:
                article, meta = browser_fetch(candidate)
                article_url = candidate
                log("official_browser_fetch", url=candidate, **meta)
                break
            except Exception as error:
                log("official_browser_retry", url=candidate, error=repr(error))
    if article is None:
        raise RuntimeError("Official PRC article unavailable after HTTP and browser attempts: " + repr(last_error))
    (OUT / "official-article.html").write_bytes(article)
    page = article.decode("utf-8", "replace")
    parser = Links()
    parser.feed(page)
    links = [urljoin(article_url, x) for x in parser.items]
    official_link = next((x for x in links if DRIVE_ID in x), None)
    if DRIVE_ID not in page:
        raise RuntimeError("Expected official Drive ID not found on PRC article")
    log("official_article", url=article_url, sha256=hashlib.sha256(article).hexdigest(), drive_link=official_link, **meta)

    # Owner-directed content-first trial: do not call a PDF download endpoint.
    # Read only the official document's ordinary public preview interface.
    pdf = None
    log("pdf_download_skipped", reason="PDF storage/download is not required; public preview is the selected content path")

    if pdf is None:
        # Content-first alternative: ordinary public Google Drive preview UI.
        # No download endpoint, private API, or access-control circumvention.
        preview_url = "https://drive.google.com/file/d/" + DRIVE_ID + "/preview"
        page_texts = []
        page_count = 368  # Public viewer reports 368 pages; document's printed page count includes cover.
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, viewport={"width": 1600, "height": 1200})
            response = page.goto(preview_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            final_url = page.url
            if (urlparse(final_url).hostname or "") not in {"drive.google.com", "docs.google.com"}:
                browser.close()
                raise RuntimeError("Unexpected public-preview redirect host")
            body = page.locator("body")
            initial = body.inner_text(timeout=10000)
            low = initial.lower() + page.content()[:100000].lower()
            if any(term in low for term in ("request access", "sign in to continue", "verify you are human", "captcha", "access denied")):
                browser.close()
                raise RuntimeError("Official public preview requires permission or human verification; manual handoff required")
            page_input = page.locator('input[aria-label^="Page is"]')
            if page_input.count() != 1:
                browser.close()
                raise RuntimeError("Public viewer page navigation control not found")
            # Navigate only through the viewer's visible page-number control.
            # No undocumented endpoints, file export, or hidden API calls.
            for page_no in range(1, page_count + 1):
                if page_no > 1:
                    page_input.fill(str(page_no))
                    page_input.press("Enter")
                    page.wait_for_function(
                        "(n) => { const e=document.querySelector('input[aria-label^=\\\"Page is\\\"]'); return e && e.getAttribute('aria-label') === 'Page is ' + n; }",
                        arg=page_no, timeout=12000
                    )
                    page.wait_for_timeout(250)
                visible = body.inner_text(timeout=10000)
                if "Page " + str(page_no) + " of " not in visible:
                    # A second short wait handles viewer page-render latency without
                    # repeating requests or changing the access method.
                    page.wait_for_timeout(500)
                    visible = body.inner_text(timeout=10000)
                page_texts.append(visible)
            page.screenshot(path=str(OUT / "official-preview-page1.png"), full_page=True)
            browser.close()
        text = "\\n\\f\\n".join(page_texts)
        if len(text.strip()) < 100:
            raise RuntimeError("Public preview did not expose readable document text")
        log("official_public_preview_pages", url=preview_url, final_url=final_url,
            status=response.status if response else None, viewer_pages=page_count,
            pages_read=len(page_texts), visible_text_characters=len(text))
        (OUT / "official-preview-page-count.json").write_text(json.dumps({
            "viewer_pages_expected": page_count, "viewer_pages_read": len(page_texts),
            "page_text_characters": [len(x) for x in page_texts]
        }, indent=2))
        (OUT / "official-layout-text.txt").write_text(text, encoding="utf-8")
    else:
        # Parse the response in memory. The source PDF is not written to disk.
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        page_text = [page.get_text("text", sort=True) for page in doc]
        text = "\\n\\f\\n".join(page_text)
        doc.close()
        (OUT / "official-layout-text.txt").write_text(text, encoding="utf-8")
        log("pdf_text_extracted_in_memory", pages=len(page_text), characters=len(text))

    # Unicode-aware sequence/name parsing. Sequence values are never inferred.
    # Preserve source spelling and accept Unicode letters/marks (including Ñ and
    # combining accents), digits, whitespace, and ordinary name punctuation.
    rows = {}
    conflicts = []
    pattern = re.compile(r"^\\s*(\\d{1,5})[.)]?\\s+(.+?)\\s*$")

    def valid_name(value):
        if len(value) < 5:
            return False
        allowed_punctuation = set(" ,.'’‘-‐‑‒–—_")
        for char in value:
            category = unicodedata.category(char)
            if category[0] in {"L", "M", "N"} or char.isspace():
                continue
            if char in allowed_punctuation:
                continue
            return False
        return True

    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        seq = int(match.group(1))
        name = " ".join(match.group(2).split()).strip(" .")
        if 1 <= seq <= EXPECTED and valid_name(name):
            if seq in rows and rows[seq] != name:
                conflicts.append({"seq": seq, "first": rows[seq], "second": name})
            else:
                rows[seq] = name
    missing = sorted(set(range(1, EXPECTED + 1)) - set(rows))
    records = [{"seq": str(k), "name": rows[k]} for k in sorted(rows)]
    (OUT / "extracted-records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\\n" for r in records))

    from collections import Counter
    name_counts = Counter(record["name"] for record in records)
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)

    # These two source strings were previously flagged for human review.
    # Keep their exact source spelling and fail closed until a reviewer compares
    # the actual page image. Unicode acceptance must never auto-resolve ambiguity.
    manual_review_sequences = [10710, 15066]
    unresolved_reviews = [
        {"seq": seq, "name": rows.get(seq)}
        for seq in manual_review_sequences
        if seq not in rows or rows[seq] in {"MAGANGCONG, MUHAMMAD_THANI PAUTE", "ROBLES, D9 BASUG"}
    ]
    report = {
        "exam": "March 2026 LEPT Elementary",
        "provenance": "official_direct",
        "announced_count": EXPECTED,
        "extracted_unique_sequences": len(records),
        "missing_sequence_count": len(missing),
        "missing_sequence_sample": missing[:100],
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:100],
        "duplicate_name_count": len(duplicate_names),
        "duplicate_name_sample": duplicate_names[:100],
        "blank_name_count": sum(not record["name"].strip() for record in records),
        "unresolved_manual_review_count": len(unresolved_reviews),
        "unresolved_manual_reviews": unresolved_reviews,
        "candidate_complete": (
            len(records) == EXPECTED and not missing and not conflicts
            and not duplicate_names
            and not any(not record["name"].strip() for record in records)
            and not unresolved_reviews
        ),
        "published": False
    }
    (OUT / "extraction-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["candidate_complete"]:
        raise RuntimeError("Extraction is incomplete or ambiguous; nothing published")
    (OUT / "attempt-evidence.json").write_text(json.dumps(events, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("fatal", error=repr(exc))
        (OUT / "attempt-evidence.json").write_text(json.dumps(events, indent=2, ensure_ascii=False))
        print("OFFICIAL-ONLY TRIAL FAILED:", repr(exc), file=sys.stderr)
        raise
