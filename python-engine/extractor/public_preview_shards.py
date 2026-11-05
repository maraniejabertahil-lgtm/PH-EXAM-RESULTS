#!/usr/bin/env python3
"""Bounded parallel capture of a publicly accessible, page-based document preview.

Reads only text rendered by the ordinary public viewer UI. It does not use
download endpoints, private APIs, authentication workarounds, or OCR. If an
access challenge appears, capture stops for an authorized human handoff.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_USER_AGENT = "PH-EXAM-RESULTS-public-preview-research/1.0 (GitHub Actions)"
CHALLENGE_TERMS = (
    "request access", "sign in to continue", "verify you are human",
    "captcha", "access denied", "unusual traffic",
)
MAX_SHARDS = 16
MAX_PAGES = 2000


class AccessChallengeError(RuntimeError):
    """The ordinary public viewer presented an access barrier."""


def partition_page_ranges(page_count: int, shard_count: int) -> list[tuple[int, int, int]]:
    """Return balanced, contiguous, 1-based page ranges using ceil division."""
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        raise ValueError("page_count must be a positive integer")
    if isinstance(shard_count, bool) or not isinstance(shard_count, int):
        raise ValueError("shard_count must be an integer")
    if not 1 <= shard_count <= MAX_SHARDS:
        raise ValueError(f"shard_count must be between 1 and {MAX_SHARDS}")
    if shard_count > page_count:
        raise ValueError("shard_count cannot exceed page_count")
    per_shard = math.ceil(page_count / shard_count)
    ranges = []
    for shard in range(shard_count):
        start = shard * per_shard + 1
        end = min((shard + 1) * per_shard, page_count)
        if start > end:
            raise ValueError("shard partition produced an empty range")
        ranges.append((shard, start, end))
    return ranges


def validate_shard_metadata(metadata: list[dict], shard_count: int) -> int:
    """Fail closed unless shard metadata describes exact, contiguous coverage."""
    if len(metadata) != shard_count:
        raise ValueError(f"expected {shard_count} shard metadata files, found {len(metadata)}")
    ordered = sorted(metadata, key=lambda item: item.get("shard", -1))
    page_counts = {item.get("page_count") for item in ordered}
    if len(page_counts) != 1 or not isinstance(next(iter(page_counts)), int):
        raise ValueError("shards disagree on page_count")
    page_count = next(iter(page_counts))
    expected_ranges = partition_page_ranges(page_count, shard_count)
    for item, (shard, start, end) in zip(ordered, expected_ranges):
        if item.get("shard") != shard or item.get("shards") != shard_count:
            raise ValueError(f"unexpected shard identity for shard {shard}")
        if item.get("page_start") != start or item.get("page_end") != end:
            raise ValueError(f"shard {shard} has a gap, overlap, or incorrect page range")
        if item.get("pages_captured") != end - start + 1:
            raise ValueError(f"shard {shard} captured an unexpected number of pages")
    return page_count


def _validate_url(preview_url: str, allowed_hosts: set[str]) -> None:
    parts = urlsplit(preview_url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("preview_url must be an absolute HTTPS URL")
    if parts.hostname.lower() not in allowed_hosts:
        raise ValueError("preview_url host is not in allowed_hosts")


def _challenge_present(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in CHALLENGE_TERMS)


# Navigation-only patterns that indicate document content has NOT rendered.
NAVIGATION_ONLY_PATTERNS = [
    r"^Page\s+\d+\s+of\s+\d+\s*$",
    r"^\d+\s*/\s*\d+\s*$",
    r"^Page\s+\d+\s*$",
]


def _has_document_content(text: str) -> bool:
    """Return True only when visible text contains content beyond viewer chrome."""
    text = text.strip()
    if not text:
        return False

    # Google Drive's visible page control can be split across four text lines:
    # "Page", "/", total-pages, and "Page N of M". Remove that exact leading
    # chrome block before checking the remaining visible text.
    text = re.sub(
        r"^Page[ \t]*\n[ \t]*/[ \t]*\n[ \t]*\d+[ \t]*\n"
        r"[ \t]*Page[ \t]+\d+[ \t]+of[ \t]+\d+[ \t]*(?:\n|$)",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    document_lines = [
        line for line in lines
        if not any(
            re.fullmatch(pattern, line, re.IGNORECASE)
            for pattern in NAVIGATION_ONLY_PATTERNS
        )
    ]
    return bool(document_lines)



def _capture_page_count_diagnostics(
    *, page, shard: int, attempt: int, output_dir: Path,
    response, last_body_text: str, console_events: list[dict],
) -> Path:
    """Persist bounded browser evidence when visible page-count detection fails."""
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostic = {
        "shard": shard, "attempt": attempt,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": "", "http_status": getattr(response, "status", None) if response else None,
        "main_frame_body_text": (last_body_text or "")[:5000],
        "frames": [], "console_logs": console_events[-50:], "screenshot_path": None,
    }
    try:
        diagnostic["url"] = page.url
    except Exception as exc:
        diagnostic["url_error"] = str(exc)[:500]
    try:
        diagnostic["main_frame_body_text"] = page.locator("body").inner_text(timeout=5000)[:5000]
    except Exception as exc:
        diagnostic["main_frame_body_error"] = str(exc)[:500]
    try:
        frames = page.frames
    except Exception as exc:
        frames = []
        diagnostic["frames_error"] = str(exc)[:500]
    for index, frame in enumerate(frames[:20]):
        item = {"index": index, "url": "", "name": "", "body_text": ""}
        try:
            item["url"], item["name"] = frame.url, frame.name
            item["body_text"] = frame.locator("body").inner_text(timeout=2500)[:5000]
        except Exception as exc:
            item["body_text_error"] = str(exc)[:500]
        diagnostic["frames"].append(item)
    screenshot = output_dir / f"diag_shard{shard}_attempt{attempt}.png"
    try:
        page.screenshot(path=str(screenshot), full_page=True, timeout=10000)
        diagnostic["screenshot_path"] = str(screenshot)
    except Exception as exc:
        diagnostic["screenshot_error"] = str(exc)[:500]
    path = output_dir / f"diag_shard{shard}_attempt{attempt}.json"
    path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[DIAG] shard={shard} attempt={attempt} url={diagnostic.get('url')} "
        f"http_status={diagnostic.get('http_status')} frames={len(diagnostic['frames'])} "
        f"json={path} screenshot={diagnostic.get('screenshot_path')}", flush=True,
    )
    for frame in diagnostic["frames"]:
        preview = frame.get("body_text", "")[:200].replace("\n", " ")
        print(f"[DIAG] frame[{frame['index']}] url={frame.get('url')} text={preview}", flush=True)
    return path

def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(channel="chrome", headless=True)
    except Exception:
        return playwright.chromium.launch(headless=True)


def _capture_stable_page(
    *, page, body, page_control_selector: str, page_number: int, page_count: int, page_marker_template: str,
    shard: int, output_dir: Path, per_page_deadline: int, poll_ms: int,
) -> str:
    """Read one visible page, retrying that page in place before restarting a shard."""
    marker = page_marker_template.format(page=page_number, count=page_count)
    diagnostic = {}
    for attempt in range(1, 4):
        control = page.locator(page_control_selector)
        if control.count() != 1:
            raise RuntimeError("public-preview page navigation control was not found uniquely")
        if page_number > 1:
            page.wait_for_selector(page_control_selector, state="visible", timeout=15000)
            control.click()
            control.fill(str(page_number))
            control.press("Enter")

        deadline = time.monotonic() + per_page_deadline
        stable_samples, previous_text, visible = 0, None, ""
        while time.monotonic() < deadline:
            visible = body.inner_text(timeout=10000)
            selected_page = control.input_value(timeout=3000).strip()
            if marker in visible and selected_page == str(page_number):
                if visible == previous_text:
                    stable_samples += 1
                else:
                    stable_samples = 0
                previous_text = visible
                # Accept only stable text that includes document content,
                # not a settled viewer-navigation placeholder.
                if stable_samples >= 2 and _has_document_content(visible):
                    return visible
            else:
                stable_samples, previous_text = 0, visible
            if _challenge_present(visible):
                raise AccessChallengeError("access challenge appeared during public-preview navigation")
            page.wait_for_timeout(poll_ms)

        diagnostic = {
            "shard": shard, "requested_page": page_number,
            "selected_page": control.input_value(timeout=3000),
            "visible_text_excerpt": visible[:1600], "url": page.url,
            "navigation_attempt": attempt,
        }
        if attempt < 3:
            print(
                f"[shard {shard}] page {page_number}/{page_count} did not stabilize "
                f"(attempt {attempt}/3); retrying this page only",
                flush=True,
            )
            page.wait_for_timeout(1000 * attempt)

    (output_dir / f"navigation-failure-shard-{shard}.json").write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    page.screenshot(
        path=str(output_dir / f"navigation-failure-shard-{shard}.png"),
        full_page=True,
    )
    raise RuntimeError("viewer page did not stabilize after 3 page-level attempts: " + json.dumps(diagnostic, ensure_ascii=False))


def capture_shard(
    *, preview_url: str, shard: int, shard_count: int, output_dir: Path,
    allowed_hosts: set[str], user_agent: str = DEFAULT_USER_AGENT,
    page_control_selector: str = 'input[aria-label^="Page is"]',
    page_count_regex: str = r"Page 1 of\s+(\d+)",
    page_marker_template: str = "Page {page} of {count}",
    per_page_deadline: int = 15, poll_ms: int = 50,
) -> dict:
    """Capture one contiguous shard using the viewer's visible page controls."""
    _validate_url(preview_url, allowed_hosts)
    if not 0 <= shard < shard_count <= MAX_SHARDS:
        raise ValueError(f"shard must be in [0, {shard_count}); shard_count <= {MAX_SHARDS}")
    if per_page_deadline < 1 or poll_ms < 10:
        raise ValueError("per_page_deadline must be positive and poll_ms at least 10")

    # Lazy import keeps partition/merge tests independent of Playwright.
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots = []
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        context = browser.new_context(
            user_agent=user_agent, locale="en-US",
            viewport={"width": 1600, "height": 1200},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        try:
            page = context.new_page()
            console_events: list[dict] = []
            page.on("console", lambda message: console_events.append({
                "type": message.type, "text": message.text[:1000],
                "timestamp": time.time(),
            }) if len(console_events) < 100 else None)
            body = page.locator("body")
            response = page.goto(preview_url, wait_until="domcontentloaded", timeout=60000)
            capture_attempt = max(1, int(os.environ.get("PH_CAPTURE_ATTEMPT", "1")))
            final_url = page.url
            final_host = (urlsplit(final_url).hostname or "").lower()
            if final_host not in allowed_hosts:
                raise RuntimeError(f"viewer redirected to an unapproved host: {final_host}")
            http_status = response.status if response else None
            if http_status is not None and http_status >= 400:
                raise RuntimeError(f"public preview returned HTTP {http_status}")

            count_match = None
            initial = ""
            ready_deadline = time.monotonic() + 25
            while time.monotonic() < ready_deadline:
                initial = body.inner_text(timeout=10000)
                count_match = re.search(page_count_regex, initial)
                if count_match:
                    break
                if _challenge_present(initial + page.content()[:100000]):
                    raise AccessChallengeError("public preview requires permission or human verification")
                page.wait_for_timeout(250)
            if not count_match:
                diagnostic_path = _capture_page_count_diagnostics(
                    page=page, shard=shard, attempt=capture_attempt,
                    output_dir=output_dir, response=response,
                    last_body_text=initial, console_events=console_events,
                )
                raise RuntimeError(
                    "could not read the public viewer page count "
                    f"(shard={shard}, attempt={capture_attempt}); diagnostics={diagnostic_path}"
                )
            page_count = int(count_match.group(1))
            if not 1 <= page_count <= MAX_PAGES:
                raise RuntimeError(f"viewer page count is outside the safe bound 1-{MAX_PAGES}")
            if _challenge_present(initial + page.content()[:100000]):
                raise AccessChallengeError("public preview requires permission or human verification")

            control = page.locator(page_control_selector)
            if control.count() != 1:
                raise RuntimeError("public-preview page navigation control was not found uniquely")
            _, start, end = partition_page_ranges(page_count, shard_count)[shard]
            loop_started = time.monotonic()

            for page_number in range(start, end + 1):
                visible = _capture_stable_page(
                    page=page, body=body, page_control_selector=page_control_selector,
                    page_number=page_number, page_count=page_count,
                    page_marker_template=page_marker_template, shard=shard,
                    output_dir=output_dir, per_page_deadline=per_page_deadline,
                    poll_ms=poll_ms,
                )

                if page_number % 100 == 0 and _challenge_present(page.content()[:100000]):
                    raise AccessChallengeError("access challenge appeared in viewer page content")
                snapshots.append({
                    "viewer_page": page_number, "text": visible,
                    "sha256": hashlib.sha256(visible.encode("utf-8")).hexdigest(),
                    "characters": len(visible),
                })
                if page_number == 1 or page_number == page_count:
                    page.screenshot(
                        path=str(output_dir / f"shard-{shard}-page-{page_number}.png"),
                        full_page=True,
                    )
                completed = page_number - start + 1
                if completed % 25 == 0 or page_number == end:
                    print(f"[shard {shard}] page {page_number}/{end}; {time.monotonic() - loop_started:.1f}s", flush=True)

            loop_seconds = round(time.monotonic() - loop_started, 1)
        finally:
            context.close()
            browser.close()

    snapshot_path = output_dir / f"shard-{shard}-snapshots.jsonl.gz"
    with gzip.open(snapshot_path, "wt", encoding="utf-8", compresslevel=3) as stream:
        for snapshot in snapshots:
            stream.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    metadata = {
        "shard": shard, "shards": shard_count, "page_start": start, "page_end": end,
        "page_count": page_count, "pages_captured": len(snapshots),
        "final_url": final_url, "http_status": http_status, "loop_seconds": loop_seconds,
        "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / f"shard-{shard}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def merge_shards(*, shard_count: int, output_dir: Path) -> dict:
    """Verify every page and hash, then write ordered visible-text evidence."""
    metadata = []
    for shard in range(shard_count):
        path = output_dir / f"shard-{shard}.json"
        if not path.is_file():
            raise RuntimeError(f"missing metadata for shard {shard}")
        metadata.append(json.loads(path.read_text(encoding="utf-8")))
    page_count = validate_shard_metadata(metadata, shard_count)

    all_snapshots = []
    for shard in range(shard_count):
        archive = output_dir / f"shard-{shard}-snapshots.jsonl.gz"
        if not archive.is_file():
            raise RuntimeError(f"missing snapshot archive for shard {shard}")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata[shard].get("snapshot_sha256"):
            raise RuntimeError(f"shard {shard} snapshot archive hash mismatch")
        shard_snapshots = []
        with gzip.open(archive, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    shard_snapshots.append(json.loads(line))
        item = metadata[shard]
        expected = list(range(item["page_start"], item["page_end"] + 1))
        if [snapshot.get("viewer_page") for snapshot in shard_snapshots] != expected:
            raise RuntimeError(f"shard {shard} snapshots do not cover assigned pages exactly")
        for snapshot in shard_snapshots:
            text_value = snapshot.get("text")
            if not isinstance(text_value, str) or not text_value.strip():
                raise RuntimeError(f"shard {shard} contains a blank page snapshot")
            if snapshot.get("sha256") != hashlib.sha256(text_value.encode("utf-8")).hexdigest():
                raise RuntimeError(f"shard {shard} page {snapshot.get('viewer_page')} hash mismatch")
        all_snapshots.extend(shard_snapshots)

    if [item["viewer_page"] for item in all_snapshots] != list(range(1, page_count + 1)):
        raise RuntimeError("merged snapshots contain a page gap, overlap, or ordering error")

    index = [{key: value for key, value in item.items() if key != "text"} for item in all_snapshots]
    index_path = output_dir / "page-capture-index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshots_path = output_dir / "page-text-snapshots.jsonl"
    snapshots_path.write_text("".join(
        json.dumps({"viewer_page": item["viewer_page"], "text": item["text"]}, ensure_ascii=False) + "\n"
        for item in all_snapshots
    ), encoding="utf-8")
    manifest = {
        "schema_version": 1, "capture_method": "ordinary_public_preview_ui",
        "shards": shard_count, "viewer_pages_expected": page_count,
        "viewer_pages_captured": len(all_snapshots), "page_coverage_complete": True,
        "pdf_downloaded": False, "access_controls_bypassed": False,
        "human_visual_review": "NOT_ASSESSED_BY_AUTOMATION",
        "files": {
            "page_capture_index": {
                "path": index_path.name,
                "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
            },
            "page_text_snapshots": {
                "path": snapshots_path.name,
                "sha256": hashlib.sha256(snapshots_path.read_bytes()).hexdigest(),
            },
        },
        "shard_metadata": metadata,
    }
    (output_dir / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-url", help="HTTPS URL of the ordinary public preview UI")
    parser.add_argument("--allowed-hosts", default="", help="Comma-separated exact preview/redirect hostnames")
    parser.add_argument("--shard", type=int)
    parser.add_argument("--shards", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=Path("public-preview-capture"))
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--page-control-selector", default='input[aria-label^="Page is"]')
    parser.add_argument("--page-count-regex", default=r"Page 1 of\s+(\d+)")
    parser.add_argument("--page-marker-template", default="Page {page} of {count}")
    parser.add_argument("--per-page-deadline", type=int, default=15)
    parser.add_argument("--poll-ms", type=int, default=50)
    args = parser.parse_args()
    if args.merge:
        print(json.dumps(merge_shards(shard_count=args.shards, output_dir=args.output_dir), indent=2))
        return 0
    if args.preview_url is None or args.shard is None:
        parser.error("--preview-url and --shard are required unless --merge is used")
    allowed_hosts = {host.strip().lower() for host in args.allowed_hosts.split(",") if host.strip()}
    if not allowed_hosts:
        allowed_hosts = {(urlsplit(args.preview_url).hostname or "").lower()}
    result = capture_shard(
        preview_url=args.preview_url, shard=args.shard, shard_count=args.shards,
        output_dir=args.output_dir, allowed_hosts=allowed_hosts,
        page_control_selector=args.page_control_selector,
        page_count_regex=args.page_count_regex,
        page_marker_template=args.page_marker_template,
        per_page_deadline=args.per_page_deadline, poll_ms=args.poll_ms,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AccessChallengeError as exc:
        stop_dir = Path("public-preview-capture")
        stop_dir.mkdir(parents=True, exist_ok=True)
        (stop_dir / "ACCESS_CHALLENGE_STOP.json").write_text(
            json.dumps({"status": "STOPPED_FOR_HUMAN_HANDOFF", "reason": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"PUBLIC PREVIEW ACCESS CHALLENGE — STOP; do not retry or bypass: {exc}", file=sys.stderr)
        raise SystemExit(20)
    except Exception as exc:
        print(f"PUBLIC PREVIEW CAPTURE STOPPED: {exc}", file=sys.stderr)
        raise
