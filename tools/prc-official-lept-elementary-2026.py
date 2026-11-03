#!/usr/bin/env python3
import hashlib, json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse

ARTICLE = "https://prc.gov.ph/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39"
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
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*"})
    with opener.open(req, timeout=35) as response:
        final = response.geturl()
        host = urlparse(final).hostname or ""
        allowed = host == "prc.gov.ph" or host.endswith(".prc.gov.ph") or host == "drive.google.com" or host.endswith(".googleusercontent.com")
        if not allowed:
            raise RuntimeError("Unexpected redirect host: " + host)
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("Response exceeded size limit")
        return data, {"status": response.status, "content_type": response.headers.get("Content-Type", ""), "final_url": final}

def log(stage, **fields):
    events.append({"time_utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **fields})

def main():
    article, meta = fetch(ARTICLE, 8 * 1024 * 1024)
    (OUT / "official-article.html").write_bytes(article)
    page = article.decode("utf-8", "replace")
    parser = Links()
    parser.feed(page)
    links = [urljoin(ARTICLE, x) for x in parser.items]
    official_link = next((x for x in links if DRIVE_ID in x), None)
    if DRIVE_ID not in page:
        raise RuntimeError("Expected official Drive ID not found on PRC article")
    log("official_article", url=ARTICLE, sha256=hashlib.sha256(article).hexdigest(), drive_link=official_link, **meta)

    urls = [
        "https://drive.google.com/uc?export=download&id=" + DRIVE_ID,
        "https://drive.usercontent.google.com/download?id=" + DRIVE_ID + "&export=download&confirm=t",
    ]
    pdf = None
    for index, url in enumerate(urls, 1):
        try:
            body, info = fetch(url)
            if body.startswith(b"%PDF-"):
                pdf = body
                log("official_pdf", attempt=index, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), **info)
                break
            prefix = body[:250].decode("utf-8", "replace")
            log("non_pdf_response", attempt=index, prefix=prefix, **info)
            low = body[:50000].lower()
            if b"captcha" in low or b"verify you are human" in low or b"request access" in low or b"sign in" in low:
                raise RuntimeError("Google Drive requires sign-in, permission, or human verification; stop without bypass")
        except Exception as error:
            log("download_attempt_error", attempt=index, error=repr(error))
    if pdf is None:
        raise RuntimeError("Official file not publicly retrievable through compliant unauthenticated access; no third-party fallback attempted")
    (OUT / "official-result.pdf").write_bytes(pdf)

    import pdfplumber
    page_text = []
    with pdfplumber.open(OUT / "official-result.pdf") as doc:
        for page in doc.pages:
            page_text.append(page.extract_text(layout=True) or page.extract_text() or "")
    text = "\n\f\n".join(page_text)
    (OUT / "official-layout-text.txt").write_text(text, encoding="utf-8")
    log("pdf_text_extracted", pages=len(page_text), characters=len(text))

    # Conservative explicit sequence/name parsing. Sequence values are never inferred.
    rows = {}
    conflicts = []
    pattern = re.compile(r"^\s*(\d{1,5})[.)]?\s+([A-Z][A-Z ,.'’\\-]+(?:\s+[A-Z][A-Z ,.'’\\-]+)*)\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        seq = int(match.group(1))
        name = " ".join(match.group(2).split()).strip(" .")
        if 1 <= seq <= EXPECTED and len(name) >= 5:
            if seq in rows and rows[seq] != name:
                conflicts.append({"seq": seq, "first": rows[seq], "second": name})
            else:
                rows[seq] = name
    missing = sorted(set(range(1, EXPECTED + 1)) - set(rows))
    records = [{"seq": str(k), "name": rows[k]} for k in sorted(rows)]
    (OUT / "extracted-records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    report = {
        "exam": "March 2026 LEPT Elementary",
        "provenance": "official_direct",
        "announced_count": EXPECTED,
        "extracted_unique_sequences": len(records),
        "missing_sequence_count": len(missing),
        "missing_sequence_sample": missing[:100],
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:100],
        "candidate_complete": len(records) == EXPECTED and not missing and not conflicts,
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
