#!/usr/bin/env python3
"""
PRC March 2026 LEPT Secondary - official public-preview capture, sharded.

Modes
  --shard I --shards N   Capture viewer pages for shard I of N (run in parallel jobs).
  --merge   --shards N   Merge shard captures, parse, validate, write the same
                         evidence/report files the single-job version wrote.
  (no flags)             Legacy single-job run: capture everything, then merge.

Same rules as before: ordinary public preview UI only, no download endpoint,
no access-control circumvention. Any access challenge stops the run.
"""
import argparse, gzip, hashlib, json, re, shutil, sys, time, unicodedata
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

ARTICLES = [
    "https://www.prc.gov.ph/index.php/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39",
    "https://www.prc.gov.ph/node/8928",
    "https://prc.gov.ph/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39",
]
DRIVE_ID = "1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7"
EXPECTED = 45001
OUT = Path("official-prc-secondary-evidence")
OUT.mkdir(exist_ok=True)
SHARD_DIR = Path("shard-output")
UA = "PH-EXAM-RESULTS-official-content-research/1.0 (GitHub Actions)"
PREVIEW_URL = "https://drive.google.com/file/d/" + DRIVE_ID + "/preview"
opener = build_opener(HTTPCookieProcessor(CookieJar()))
events = []
MODE = "legacy"

# Viewer-loop tuning
POLL_MS = 150
STABLE_REQUIRED = 2
PER_PAGE_DEADLINE_S = 35
DEEP_CHALLENGE_CHECK_EVERY = 100
PROGRESS_EVERY = 25
CHALLENGE_TERMS = (
    "request access", "sign in to continue", "verify you are human",
    "captcha", "access denied",
)


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
        host = (urlparse(final_url).hostname or "").lower()
        if host != "prc.gov.ph" and not host.endswith(".prc.gov.ph"):
            raise RuntimeError("Unexpected official-page redirect host")
        low = body_text.lower()
        if any(x in low for x in CHALLENGE_TERMS):
            raise RuntimeError("Official page requires human verification or access")
        if status and status >= 400:
            raise RuntimeError("Official page HTTP " + str(status))
        return html, {"status": status, "content_type": "text/html; browser=chromium", "final_url": final_url}


def target_name_is_valid(value):
    if len(value) < 5:
        return False
    punctuation = set(" ,.'\u2019\u2018-\u2010\u2011\u2012\u2013\u2014_")
    return all(
        unicodedata.category(char)[0] in {"L", "M", "N"} or char.isspace() or char in punctuation
        for char in value
    )


# ---------------------------------------------------------------------------
# CAPTURE (one shard = one contiguous range of viewer pages)
# ---------------------------------------------------------------------------
def capture(shard, shards):
    SHARD_DIR.mkdir(exist_ok=True)
    target_line_pattern = re.compile(r"^\s*(\d{1,5})[.)]?\s+(.+?)\s*$")
    target_pages = {}
    page_snapshots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, viewport={"width": 1600, "height": 1200})
        response = page.goto(PREVIEW_URL, wait_until="domcontentloaded", timeout=60000)
        final_url = page.url
        if (urlparse(final_url).hostname or "") not in {"drive.google.com", "docs.google.com"}:
            browser.close()
            raise RuntimeError("Unexpected public-preview redirect host")
        body = page.locator("body")
        # Poll for the viewer instead of a fixed 4 s sleep.
        initial, count_match = "", None
        ready_deadline = time.monotonic() + 25
        while time.monotonic() < ready_deadline:
            initial = body.inner_text(timeout=10000)
            count_match = re.search(r"Page 1 of\s+(\d+)", initial)
            if count_match:
                break
            page.wait_for_timeout(250)
        if not count_match:
            browser.close()
            raise RuntimeError("Could not read the public viewer's page count")
        page_count = int(count_match.group(1))
        if page_count < 1 or page_count > 2000:
            browser.close()
            raise RuntimeError("Public viewer page count is outside the safe bound")
        low = initial.lower() + page.content()[:100000].lower()
        if any(term in low for term in CHALLENGE_TERMS):
            browser.close()
            raise RuntimeError("Official public preview requires permission or human verification; manual handoff required")
        try:
            page.wait_for_selector('input[aria-label^="Page is"]', state="attached", timeout=15000)
        except Exception:
            pass
        page_input = page.locator('input[aria-label^="Page is"]')
        if page_input.count() != 1:
            browser.close()
            raise RuntimeError("Public viewer page navigation control not found")

        per = -(-page_count // shards)
        start = shard * per + 1
        end = min((shard + 1) * per, page_count)
        if start > end:
            browser.close()
            raise RuntimeError(f"Shard {shard} of {shards} has no pages (page_count={page_count})")
        print(f"[shard {shard}/{shards}] pages {start}-{end} of {page_count}", flush=True)

        loop_started = time.monotonic()
        for page_no in range(start, end + 1):
            if page_no > 1:
                page_input.click()
                page_input.fill(str(page_no))
                page_input.press("Enter")
            marker = f"Page {page_no} of {page_count}"
            deadline = time.monotonic() + PER_PAGE_DEADLINE_S
            stable_samples, previous_text, visible = 0, None, ""
            while time.monotonic() < deadline:
                visible = body.inner_text(timeout=10000)
                if marker in visible and page_input.input_value(timeout=3000) == str(page_no):
                    if visible == previous_text:
                        stable_samples += 1
                    else:
                        stable_samples = 0
                    previous_text = visible
                    if stable_samples >= STABLE_REQUIRED:
                        break
                else:
                    stable_samples, previous_text = 0, visible
                page.wait_for_timeout(POLL_MS)
            else:
                diagnostic = {
                    "shard": shard, "requested_page": page_no,
                    "input_value": page_input.input_value(timeout=3000),
                    "aria_label": page_input.get_attribute("aria-label"),
                    "visible_text_excerpt": visible[:1600],
                    "url": page.url, "stable_samples": stable_samples,
                }
                (SHARD_DIR / f"navigation-failure-shard{shard}.json").write_text(json.dumps(diagnostic, indent=2), encoding="utf-8")
                page.screenshot(path=str(SHARD_DIR / f"navigation-failure-shard{shard}.png"), full_page=True)
                raise RuntimeError("Public viewer page text did not stabilize for page " + str(page_no) + ": " + json.dumps(diagnostic, ensure_ascii=False))
            low_visible = visible.lower()
            if any(term in low_visible for term in CHALLENGE_TERMS):
                raise RuntimeError("Access challenge appeared during public-preview navigation")
            if page_no % DEEP_CHALLENGE_CHECK_EVERY == 0:
                if any(term in page.content()[:100000].lower() for term in CHALLENGE_TERMS):
                    raise RuntimeError("Access challenge appeared during public-preview navigation")
            page_snapshots.append({
                "viewer_page": page_no,
                "text": visible,
                "sha256": hashlib.sha256(visible.encode("utf-8")).hexdigest(),
                "characters": len(visible),
            })
            for line in visible.splitlines():
                candidate = target_line_pattern.match(line)
                if candidate:
                    sequence = int(candidate.group(1))
                    candidate_name = " ".join(candidate.group(2).split()).strip(" .")
                    if (
                        (sequence == 1 and page_no == 1)
                        or (sequence == EXPECTED and page_no == page_count)
                    ) and target_name_is_valid(candidate_name) and sequence not in target_pages:
                        target_pages[sequence] = {"name": candidate_name, "viewer_page": page_no, "printed_page": page_no + 1}
            if page_no == 1:
                page.screenshot(path=str(SHARD_DIR / "official-preview-page1.png"), full_page=True)
            done = page_no - start + 1
            if done % PROGRESS_EVERY == 0 or page_no == end:
                el = time.monotonic() - loop_started
                print(f"[shard {shard}] page {page_no}/{end} elapsed {el:.0f}s ({el / done:.2f}s/page)", flush=True)
        loop_seconds = round(time.monotonic() - loop_started, 1)
        status = response.status if response else None
        browser.close()

    with gzip.open(SHARD_DIR / f"shard-{shard}-snapshots.jsonl.gz", "wt", encoding="utf-8", compresslevel=3) as fh:
        for s in page_snapshots:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    (SHARD_DIR / f"shard-{shard}.json").write_text(json.dumps({
        "shard": shard, "shards": shards, "page_start": start, "page_end": end,
        "page_count": page_count, "pages_captured": len(page_snapshots),
        "target_pages": {str(k): v for k, v in target_pages.items()},
        "final_url": final_url, "status": status, "loop_seconds": loop_seconds,
    }, indent=2), encoding="utf-8")
    print(f"[shard {shard}] done: {len(page_snapshots)} pages in {loop_seconds}s", flush=True)


# ---------------------------------------------------------------------------
# MERGE (provenance check + shard merge + parse + validate + report)
# ---------------------------------------------------------------------------
def merge(shards):
    article, article_url, last_error, meta = None, None, None, {}
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
    page_html = article.decode("utf-8", "replace")
    parser = Links()
    parser.feed(page_html)
    links = [urljoin(article_url, x) for x in parser.items]
    official_link = next((x for x in links if DRIVE_ID in x), None)
    if DRIVE_ID not in page_html:
        raise RuntimeError("Expected official Drive ID not found on PRC article")
    log("official_article", url=article_url, sha256=hashlib.sha256(article).hexdigest(), drive_link=official_link, **meta)
    log("pdf_download_skipped", reason="PDF storage/download is not required; public preview is the selected content path")

    # ---- load and verify shards
    metas, page_snapshots, target_pages = [], [], {}
    expected_start, page_count = 1, None
    for i in range(shards):
        mp = SHARD_DIR / f"shard-{i}.json"
        sp = SHARD_DIR / f"shard-{i}-snapshots.jsonl.gz"
        if not mp.is_file() or not sp.is_file():
            raise RuntimeError(f"Missing capture files for shard {i}")
        m = json.loads(mp.read_text(encoding="utf-8"))
        if page_count is None:
            page_count = m["page_count"]
        if m["page_count"] != page_count or m["shards"] != shards:
            raise RuntimeError(f"Shard {i} disagrees on page count or shard count")
        if m["page_start"] != expected_start:
            raise RuntimeError(f"Shard {i} starts at {m['page_start']}, expected {expected_start}")
        snaps = []
        with gzip.open(sp, "rt", encoding="utf-8") as fh:
            for line in fh:
                snaps.append(json.loads(line))
        wanted = list(range(m["page_start"], m["page_end"] + 1))
        if [s["viewer_page"] for s in snaps] != wanted:
            raise RuntimeError(f"Shard {i} snapshots do not cover pages {wanted[0]}-{wanted[-1]} exactly")
        for k, v in m["target_pages"].items():
            target_pages[int(k)] = v
        page_snapshots.extend(snaps)
        metas.append(m)
        expected_start = m["page_end"] + 1
        log("shard_capture", shard=i, page_start=m["page_start"], page_end=m["page_end"], loop_seconds=m["loop_seconds"], final_url=m["final_url"], status=m["status"])
    if expected_start - 1 != page_count or len(page_snapshots) != page_count:
        raise RuntimeError("Shards do not cover every viewer page exactly once")
    if set(target_pages) != {1, EXPECTED}:
        raise RuntimeError("Could not bind first and last announced records to visible viewer pages")

    # Preserve every page occurrence. Deduplicating identical lines here would
    # hide a repeated sequence/name pair and could falsely pass duplicate checks.
    merged_lines = [
        line for snapshot in page_snapshots for line in snapshot["text"].splitlines()
    ]
    text = "\n".join(merged_lines)
    (OUT / "page-capture-index.json").write_text(json.dumps([
        {k: v for k, v in s.items() if k != "text"} for s in page_snapshots
    ], indent=2), encoding="utf-8")
    (OUT / "page-text-snapshots.jsonl").write_text("".join(
        json.dumps({"viewer_page": s["viewer_page"], "text": s["text"]}, ensure_ascii=False) + "\n" for s in page_snapshots
    ), encoding="utf-8")
    shot = SHARD_DIR / "official-preview-page1.png"
    if shot.is_file():
        shutil.copyfile(shot, OUT / "official-preview-page1.png")
    if len(text.strip()) < 100:
        raise RuntimeError("Public preview did not expose readable document text")
    log("official_public_preview_pages", url=PREVIEW_URL, final_url=metas[0]["final_url"],
        status=metas[0]["status"], viewer_pages=page_count,
        pages_navigated=len(page_snapshots), snapshots_retained=len(page_snapshots),
        final_document_text_characters=len(text), shards=shards,
        slowest_shard_loop_seconds=max(m["loop_seconds"] for m in metas),
        page_snapshot_index_sha256=hashlib.sha256((OUT / "page-capture-index.json").read_bytes()).hexdigest())
    (OUT / "official-preview-page-count.json").write_text(json.dumps({
        "viewer_pages_expected": page_count, "viewer_pages_navigated": len(page_snapshots),
        "snapshots_retained": len(page_snapshots), "final_document_text_characters": len(text)
    }, indent=2))
    (OUT / "official-layout-text.txt").write_text(text, encoding="utf-8")

    # ---- Unicode-aware sequence/name parsing (unchanged)
    rows, conflicts, sequence_occurrences, out_of_range_records = {}, [], {}, []
    pattern = re.compile(r"^\s*(\d{1,5})[.)]?\s+(.+?)\s*$")

    def valid_name(value):
        if len(value) < 5:
            return False
        allowed_punctuation = set(" ,.'\u2019\u2018-\u2010\u2011\u2012\u2013\u2014_()/") | {'"'}
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
        if valid_name(name):
            if not 1 <= seq <= EXPECTED:
                out_of_range_records.append({"seq": seq, "name": name})
                continue
            sequence_occurrences[seq] = sequence_occurrences.get(seq, 0) + 1
            if seq in rows and rows[seq] != name:
                conflicts.append({"seq": seq, "first": rows[seq], "second": name})
            else:
                rows[seq] = name
    missing = sorted(set(range(1, EXPECTED + 1)) - set(rows))
    records = [{"seq": str(k), "name": rows[k]} for k in sorted(rows)]
    (OUT / "extracted-records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))

    name_counts = Counter(record["name"] for record in records)
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
    duplicate_sequences = sorted(seq for seq, count in sequence_occurrences.items() if count > 1)

    expected_visual_records = {
        str(sequence): {
            "name": target_pages[sequence]["name"],
            "printed_page": target_pages[sequence]["printed_page"],
            "viewer_page": target_pages[sequence]["viewer_page"],
            "screenshot_sha256": "",
        }
        for sequence in (1, EXPECTED)
    }
    unresolved_targets = [
        {"seq": seq, "expected_name": evidence["name"], "observed_name": rows.get(int(seq))}
        for seq, evidence in expected_visual_records.items()
        if rows.get(int(seq)) != evidence["name"]
    ]
    report = {
        "exam": "March 2026 LEPT Secondary",
        "provenance": "official_direct",
        "announced_count": EXPECTED,
        "extracted_unique_sequences": len(records),
        "missing_sequence_count": len(missing),
        "missing_sequence_sample": missing[:100],
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:100],
        "duplicate_sequence_count": len(duplicate_sequences),
        "duplicate_sequence_sample": duplicate_sequences[:100],
        "out_of_range_record_count": len(out_of_range_records),
        "out_of_range_record_sample": out_of_range_records[:100],
        "duplicate_name_count": len(duplicate_names),
        "duplicate_name_sample": duplicate_names[:100],
        "blank_name_count": sum(not record["name"].strip() for record in records),
        "visual_verification_evidence": expected_visual_records,
        "unresolved_target_record_count": len(unresolved_targets),
        "unresolved_target_records": unresolved_targets,
        "visual_human_review_status": "PENDING",
        "candidate_complete": (
            len(records) == EXPECTED and not missing and not conflicts
            and not duplicate_sequences and not out_of_range_records
            and not duplicate_names
            and not any(not record["name"].strip() for record in records)
            and not unresolved_targets
        ),
        "published": False,
    }
    (OUT / "extraction-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["candidate_complete"]:
        raise RuntimeError("Extraction is incomplete or ambiguous; nothing published")
    (OUT / "attempt-evidence.json").write_text(json.dumps(events, indent=2, ensure_ascii=False))


def main():
    global MODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=None)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.shards < 1 or args.shards > 16:
        raise SystemExit("--shards must be between 1 and 16")
    if args.merge:
        MODE = "merge"
        merge(args.shards)
    elif args.shard is not None:
        if not 0 <= args.shard < args.shards:
            raise SystemExit("--shard must be in [0, shards)")
        MODE = "shard"
        capture(args.shard, args.shards)
    else:
        MODE = "legacy"
        capture(0, 1)
        merge(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("fatal", error=repr(exc))
        try:
            if MODE == "shard":
                SHARD_DIR.mkdir(exist_ok=True)
                (SHARD_DIR / f"failure-events-{int(time.time())}.json").write_text(json.dumps(events, indent=2, ensure_ascii=False))
            else:
                (OUT / "attempt-evidence.json").write_text(json.dumps(events, indent=2, ensure_ascii=False))
        except Exception:
            pass
        print("OFFICIAL-ONLY TRIAL FAILED:", repr(exc), file=sys.stderr)
        raise
