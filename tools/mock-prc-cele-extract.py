#!/usr/bin/env python3
"""Private mock extraction for the September 2026 PRC Civil Engineers results.

Official PRC PDF is attempted first through the ordinary public Google Drive
download endpoint. If it is unavailable, two independent public transcriptions
are fetched with robots.txt checks and a minimum two-second delay.
No publication or deployment is performed by this script.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

OUT = Path("private-prc-extraction")
EXPECTED = 6337
OFFICIAL_PDF_ID = "1sHNKcBlioPYXyH0o9vbDwyfSrLd4X8yd"
OFFICIAL_ANNOUNCEMENT = "https://www.prc.gov.ph/node/9410"
MOCK_RELEASE_TIME = "2026-11-03T03:35:00+03:00"
USER_AGENT = "PH-EXAM-RESULTS-MockResearch/1.0 (public examination result verification)"
MAX_HTML_BYTES = 15 * 1024 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024

SOURCES = {
    "boardexams_ph": [
        "https://boardexams.ph/list-of-passers/september-2026-civil-engineers-licensure-exam-cele/a-f-passers/",
        "https://boardexams.ph/list-of-passers/september-2026-civil-engineers-licensure-exam-cele/g-l-passers/",
        "https://boardexams.ph/list-of-passers/september-2026-civil-engineers-licensure-exam-cele/m-r-passers/",
        "https://boardexams.ph/list-of-passers/september-2026-civil-engineers-licensure-exam-cele/s-z-passers/",
    ],
    "prcboard_com": [
        "https://www.prcboard.com/a-c-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/d-f-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/g-i-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/j-l-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/m-o-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/p-r-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/s-u-passers-september-2026-civil-engineer-licensure-exam-cele-results",
        "https://www.prcboard.com/v-z-passers-september-2026-civil-engineer-licensure-exam-cele-results",
    ],
}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def stamp() -> str:
    return now_utc().isoformat()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fetch_bytes(url: str, limit: int) -> tuple[int, bytes, str, str]:
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,application/octet-stream,*/*",
    })
    with urlopen(req, timeout=40) as response:
        final_url = response.geturl()
        if urlparse(final_url).hostname != urlparse(url).hostname:
            raise RuntimeError("Cross-host redirect rejected for public source page")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("Response exceeded configured size limit")
        return response.status, data, response.headers.get_content_type(), final_url

def robots_policy(url: str, cache: dict) -> tuple[bool, float, str]:
    host = urlparse(url).hostname
    if host not in cache:
        robots_url = f"https://{host}/robots.txt"
        try:
            status, raw, ctype, _ = fetch_bytes(robots_url, 512 * 1024)
            if status != 200 or ctype not in {"text/plain", "text/html"}:
                raise RuntimeError(f"Unexpected robots response: HTTP {status}, {ctype}")
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(raw.decode("utf-8", "replace").splitlines())
            delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 2.0
            cache[host] = (parser, max(2.0, float(delay)), "robots.txt retrieved")
        except HTTPError as exc:
            if exc.code == 404:
                cache[host] = (None, 2.0, "robots.txt returned 404; no published rules")
            else:
                raise RuntimeError(f"Cannot verify robots policy for {host}: HTTP {exc.code}") from exc
    parser, delay, note = cache[host]
    allowed = True if parser is None else parser.can_fetch(USER_AGENT, url)
    return allowed, delay, note

class VisibleText(HTMLParser):
    BLOCKS = {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if self.skip_depth == 0 and tag in self.BLOCKS:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if self.skip_depth == 0 and tag in self.BLOCKS:
            self.parts.append("\n")
    def handle_data(self, data):
        if self.skip_depth == 0:
            self.parts.append(data)
    def text(self) -> str:
        return "\n".join(
            re.sub(r"\s+", " ", line).strip()
            for line in "".join(self.parts).replace("\xa0", " ").splitlines()
            if line.strip()
        )

def parse_records(text: str, source_url: str) -> list[dict]:
    records = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        match = re.match(r"^(\d{1,5})\s+(.+?)\s*$", line)
        if not match:
            continue
        sequence = int(match.group(1))
        name = match.group(2).strip()
        if not name or len(name) > 180:
            continue
        if re.match(r"^(page\b|roll of\b|held on\b|released on\b|seq\.?\s|n\s*a\s*m\s*e\b)", name, re.I):
            continue
        if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", name):
            continue
        if re.search(r"\b(civil engineer|licensure examination|examination results)\b", name, re.I):
            continue
        records.append({
            "sequence_number": sequence,
            "passer_name": name,
            "source_url": source_url,
        })
    return records

def validate_source(rows: list[dict]) -> dict:
    seqs = [row["sequence_number"] for row in rows]
    counts = Counter(seqs)
    duplicates = sorted(seq for seq, count in counts.items() if count > 1)
    byseq = {}
    for row in rows:
        byseq.setdefault(row["sequence_number"], row["passer_name"])
    missing = sorted(set(range(1, EXPECTED + 1)) - set(byseq))
    extra = sorted(seq for seq in byseq if seq < 1 or seq > EXPECTED)
    blanks = sum(not row["passer_name"].strip() for row in rows)
    return {
        "records": len(rows),
        "unique_sequences": len(byseq),
        "missing_sequences": missing,
        "extra_sequences": extra,
        "duplicate_sequences": duplicates,
        "blank_names": blanks,
        "sequence_coverage_exact": not missing and not extra and not duplicates and len(byseq) == EXPECTED,
        "by_sequence": byseq,
    }

def try_official_pdf() -> dict:
    url = f"https://drive.google.com/uc?export=download&id={OFFICIAL_PDF_ID}"
    started = time.monotonic()
    result = {
        "source": "official_prc_google_drive",
        "url": f"https://drive.google.com/file/d/{OFFICIAL_PDF_ID}/view",
        "attempt_started_at": stamp(),
        "downloaded": False,
    }
    try:
        status, data, ctype, final_url = fetch_bytes(url, MAX_PDF_BYTES)
        final = urlparse(final_url)
        if final.scheme != "https" or final.hostname not in {"drive.google.com", "drive.usercontent.google.com"}:
            raise RuntimeError("Official PDF redirect host was not on the Google Drive allowlist")
        final_ids = parse_qs(final.query).get("id")
        if final_ids and final_ids != [OFFICIAL_PDF_ID]:
            raise RuntimeError("Official PDF redirect did not retain the exact approved file ID")
        if b"%PDF-" not in data[:1024]:
            diagnostic = OUT / "official-drive-response-diagnostic.html"
            diagnostic.write_bytes(data[:min(len(data), 1024 * 1024)])
            raise RuntimeError(f"Google Drive returned {ctype}, not PDF bytes; diagnostic saved")
        if len(data) > MAX_PDF_BYTES:
            raise RuntimeError("Official PDF exceeded the 50 MiB limit")
        pdf_path = OUT / "CE0926-alpha.pdf"
        pdf_path.write_bytes(data)
        result.update({
            "downloaded": True,
            "http_status": status,
            "content_type": ctype,
            "bytes": len(data),
            "sha256": sha256(data),
            "final_host": final.hostname,
            "saved_path": str(pdf_path),
        })
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=30, check=True)
            page_match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.M)
            result["page_count"] = int(page_match.group(1)) if page_match else None
        if shutil.which("pdftotext"):
            text_result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                capture_output=True, text=True, timeout=120, check=True,
            )
            pdf_rows = parse_records(text_result.stdout, result["url"])
            pdf_validation = validate_source(pdf_rows)
            result["text_extracted_records"] = len(pdf_rows)
            result["text_extraction_complete"] = (
                len(pdf_rows) == EXPECTED and pdf_validation["sequence_coverage_exact"]
            )
            result["text_pair_validation"] = {
                key: value for key, value in pdf_validation.items() if key != "by_sequence"
            }
            result["parsed_rows"] = pdf_rows if result["text_extraction_complete"] else []
        else:
            result["text_extraction_complete"] = False
            result["text_extraction_note"] = "Poppler pdftotext unavailable"
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    result["attempt_finished_at"] = stamp()
    return result

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    run_started_at = stamp()
    stage_times = {}
    pdf_result = try_official_pdf()
    stage_times["official_pdf_attempt_seconds"] = pdf_result["duration_seconds"]

    robots_cache = {}
    datasets = {}
    robots_audit = []
    fetch_audit = []
    for source_name, urls in SOURCES.items():
        source_started = time.monotonic()
        rows = []
        for url in urls:
            allowed, delay, robots_note = robots_policy(url, robots_cache)
            robots_audit.append({
                "source": source_name, "url": url,
                "robots_allowed": allowed, "delay_seconds": delay,
                "note": robots_note,
            })
            if not allowed:
                raise RuntimeError(f"robots.txt disallows required source page: {url}")
            time.sleep(delay)
            page_started = time.monotonic()
            status, raw, ctype, final_url = fetch_bytes(url, MAX_HTML_BYTES)
            if status != 200 or ctype != "text/html":
                raise RuntimeError(f"Unexpected source response: {url}: HTTP {status}, {ctype}")
            if urlparse(final_url).hostname != urlparse(url).hostname:
                raise RuntimeError(f"Unexpected cross-host redirect: {url}")
            filename = f"{source_name}-{len(fetch_audit)+1:02d}.html"
            (OUT / filename).write_bytes(raw)
            parser = VisibleText()
            parser.feed(raw.decode("utf-8", "replace"))
            page_rows = parse_records(parser.text(), url)
            rows.extend(page_rows)
            fetch_audit.append({
                "source": source_name, "url": url, "http_status": status,
                "content_type": ctype, "bytes": len(raw), "sha256": sha256(raw),
                "records_parsed": len(page_rows),
                "duration_seconds": round(time.monotonic() - page_started, 3),
                "evidence_file": filename,
            })
        validation = validate_source(rows)
        datasets[source_name] = {"rows": rows, "validation": validation}
        (OUT / f"{source_name}-records.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        stage_times[f"{source_name}_fetch_parse_seconds"] = round(time.monotonic() - source_started, 3)

    first = datasets["boardexams_ph"]["validation"]["by_sequence"]
    second = datasets["prcboard_com"]["validation"]["by_sequence"]
    all_sequences = sorted(set(first) | set(second))
    mismatches = []
    matched = []
    for seq in all_sequences:
        name_a, name_b = first.get(seq), second.get(seq)
        if name_a is None or name_b is None or name_a != name_b:
            mismatches.append({
                "sequence_number": seq,
                "boardexams_ph": name_a,
                "prcboard_com": name_b,
            })
        else:
            matched.append({
                "sequence_number": seq,
                "passer_name": name_a,
                "source_1": "Board Exams PH",
                "source_2": "PRC Board",
                "independent_match": True,
            })

    csv_path = OUT / "PRC_CELE_2026_September_Sequence_Name.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "sequence_number", "name", "seq", "source_1", "source_2", "independent_match"
        ])
        writer.writeheader()
        for row in matched:
            writer.writerow({
                "sequence_number": row["sequence_number"],
                "name": row["passer_name"],
                "seq": row["sequence_number"],
                "source_1": row["source_1"],
                "source_2": row["source_2"],
                "independent_match": row["independent_match"],
            })
    (OUT / "PRC_CELE_2026_September_Sequence_Name.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in matched),
        encoding="utf-8",
    )

    a = datasets["boardexams_ph"]["validation"]
    b = datasets["prcboard_com"]["validation"]
    mirrors_valid = (
        a["records"] == EXPECTED and b["records"] == EXPECTED
        and a["sequence_coverage_exact"] and b["sequence_coverage_exact"]
        and not mismatches and len(matched) == EXPECTED
    )
    if pdf_result["downloaded"]:
        official_source_valid = pdf_result.get("text_extraction_complete", False)
        pdf_rows = pdf_result.get("parsed_rows", [])
        pdf_byseq = {row["sequence_number"]: row["passer_name"] for row in pdf_rows}
        pdf_mismatches = [
            seq for seq in range(1, EXPECTED + 1)
            if pdf_byseq.get(seq) != first.get(seq) or pdf_byseq.get(seq) != second.get(seq)
        ] if official_source_valid else []
    else:
        official_source_valid = None
        pdf_mismatches = []

    if pdf_result["downloaded"]:
        greenlight = mirrors_valid and official_source_valid and not pdf_mismatches
        mode = "official_pdf_plus_dual_source_crosscheck"
    else:
        greenlight = mirrors_valid
        mode = "dual_source_fallback_after_official_pdf_download_failure"

    release_time = datetime.fromisoformat(MOCK_RELEASE_TIME)
    finished = now_utc()
    elapsed_since_release = (finished - release_time.astimezone(timezone.utc)).total_seconds()
    stage_times["mirror_crosscheck_and_output_seconds"] = round(time.monotonic() - started - sum(
        value for key, value in stage_times.items() if key.endswith("_seconds")
    ), 3)
    report = {
        "mock": True,
        "mock_release_time": MOCK_RELEASE_TIME,
        "mock_run_started_at": run_started_at,
        "mock_run_finished_at": finished.isoformat(),
        "elapsed_since_assumed_release_seconds": round(elapsed_since_release, 3),
        "elapsed_since_assumed_release_human": f"{int(elapsed_since_release // 3600)}h {int((elapsed_since_release % 3600) // 60)}m {int(elapsed_since_release % 60)}s",
        "pipeline_runtime_seconds": round(time.monotonic() - started, 3),
        "timings": stage_times,
        "authority": "PRC",
        "examination": "CELE",
        "exam_period": "September 2026",
        "official_announcement_url": OFFICIAL_ANNOUNCEMENT,
        "official_expected_passers": EXPECTED,
        "official_pdf_attempt": {key: value for key, value in pdf_result.items() if key != "parsed_rows"},
        "source_mode": mode,
        "sources": {
            name: {key: value for key, value in dataset["validation"].items() if key != "by_sequence"}
            for name, dataset in datasets.items()
        },
        "cross_source_matches": len(matched),
        "cross_source_mismatches": len(mismatches),
        "mismatch_examples": mismatches[:100],
        "official_pdf_mismatches_against_both_mirrors": len(pdf_mismatches),
        "greenlight": greenlight,
        "published": False,
        "deployed": False,
        "website_dataset_changed": False,
        "robots_audit": robots_audit,
        "fetch_audit": fetch_audit,
        "output_files": [
            str(csv_path),
            str(OUT / "PRC_CELE_2026_September_Sequence_Name.jsonl"),
        ],
    }
    (OUT / "PRC_CELE_2026_September_Mock_Validation_Report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "source_mode": mode,
        "official_pdf_downloaded": pdf_result["downloaded"],
        "boardexams_records": a["records"],
        "prcboard_records": b["records"],
        "cross_source_matches": len(matched),
        "cross_source_mismatches": len(mismatches),
        "greenlight": greenlight,
        "pipeline_runtime_seconds": report["pipeline_runtime_seconds"],
        "elapsed_since_assumed_release": report["elapsed_since_assumed_release_human"],
        "csv": str(csv_path),
    }, ensure_ascii=False, indent=2))
    return 0 if greenlight else 1

if __name__ == "__main__":
    raise SystemExit(main())
