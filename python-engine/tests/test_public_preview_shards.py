import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

EXTRACTOR_DIR = Path(__file__).resolve().parents[1] / "extractor"
sys.path.insert(0, str(EXTRACTOR_DIR))

from public_preview_shards import (  # noqa: E402
    AccessChallengeError,
    _challenge_present,
    _capture_stable_page,
    _has_document_content,
    _normalized_content_hash,
    _capture_unique_page,
    merge_shards,
    partition_page_ranges,
    validate_shard_metadata,
)


class PartitionTests(unittest.TestCase):
    def test_901_pages_matches_proven_16_shard_partition(self):
        ranges = partition_page_ranges(901, 16)
        self.assertEqual(ranges[0], (0, 1, 57))
        self.assertEqual(ranges[14], (14, 799, 855))
        self.assertEqual(ranges[15], (15, 856, 901))
        self.assertEqual(sum(end - start + 1 for _, start, end in ranges), 901)

    def test_small_uneven_partition_is_contiguous(self):
        self.assertEqual(
            partition_page_ranges(10, 3),
            [(0, 1, 4), (1, 5, 8), (2, 9, 10)],
        )

    def test_invalid_partition_inputs_fail_closed(self):
        for pages, shards in ((0, 1), (-1, 1), (4, 0), (4, 17), (2, 3), (True, 1)):
            with self.subTest(pages=pages, shards=shards):
                with self.assertRaises(ValueError):
                    partition_page_ranges(pages, shards)

    def test_access_challenge_terms_are_detected(self):
        self.assertTrue(_challenge_present("Please verify you are human"))
        self.assertTrue(_challenge_present("Request access"))
        self.assertFalse(_challenge_present("Page 1 of 901"))



class DocumentContentTests(unittest.TestCase):
    def test_navigation_only_text_is_rejected(self):
        for text in ("Page 115 of 901", "115 / 901", "Page 115"):
            with self.subTest(text=text):
                self.assertFalse(_has_document_content(text))

    def test_navigation_marker_with_document_text_is_accepted(self):
        self.assertTrue(_has_document_content("Page 115 of 901\nPASSERS\nJUAN DELA CRUZ"))

    def test_split_google_drive_navigation_only_text_is_rejected(self):
        self.assertFalse(_has_document_content("Page\n/\n901\nPage 457 of 901"))

    def test_split_google_drive_navigation_plus_document_text_is_accepted(self):
        self.assertTrue(_has_document_content(
            "Page\n/\n901\nPage 457 of 901\nActual document text"
        ))

    def test_empty_text_is_rejected(self):
        self.assertFalse(_has_document_content("  \n  "))


class DuplicateContentGuardTests(unittest.TestCase):
    def test_viewer_chrome_does_not_change_document_content_signature(self):
        first = "Page\\n/\\n901\\nPage 457 of 901\\nPASSERS\\nJUAN DELA CRUZ"
        second = "Page\\n/\\n901\\nPage 458 of 901\\nPASSERS\\nJUAN DELA CRUZ"
        self.assertEqual(_normalized_content_hash(first), _normalized_content_hash(second))

    def test_different_document_content_has_different_signature(self):
        self.assertNotEqual(
            _normalized_content_hash("Page 10 of 901\\nJUAN DELA CRUZ"),
            _normalized_content_hash("Page 11 of 901\\nMARIA SANTOS"),
        )

    def test_short_legitimate_page_content_is_kept_distinct(self):
        self.assertNotEqual(
            _normalized_content_hash("Page 10 of 901\\nAPPENDIX"),
            _normalized_content_hash("Page 11 of 901\\nINDEX"),
        )

    def test_duplicate_content_retries_then_fails_closed_with_diagnostic(self):
        from unittest.mock import patch

        class FakeControl:
            def __init__(self, page):
                self.page = page
            def count(self):
                return 1
            def click(self):
                pass
            def fill(self, value):
                self.page.target = value
            def press(self, key):
                self.page.press_count += 1
            def input_value(self, timeout=None):
                return self.page.target

        class FakePage:
            url = "https://drive.google.com/file/d/example/preview"
            def __init__(self):
                self.press_count = 0
                self.target = "2"
            def locator(self, selector):
                return FakeControl(self)
            def wait_for_timeout(self, milliseconds):
                pass
            def screenshot(self, path, full_page=True):
                Path(path).write_bytes(b"diagnostic screenshot placeholder")

        with tempfile.TemporaryDirectory() as temp:
            page = FakePage()
            seen = {_normalized_content_hash("Page 1 of 3\\nRepeated stale text")}
            repeated = "Page 2 of 3\\nRepeated stale text"
            with patch("public_preview_shards._capture_stable_page", return_value=repeated) as capture:
                with self.assertRaisesRegex(RuntimeError, "duplicate content after 3 retries"):
                    _capture_unique_page(
                        page=page, seen_content_hashes=seen,
                        page_control_selector='input[aria-label^="Page is"]',
                        page_number=2, page_count=3,
                        page_marker_template="Page {page} of {count}",
                        shard=0, output_dir=Path(temp),
                        per_page_deadline=1, poll_ms=10,
                    )
            self.assertEqual(capture.call_count, 3)
            self.assertTrue((Path(temp) / "duplicate-content-shard-0-page-2.json").is_file())
            self.assertTrue((Path(temp) / "duplicate-content-shard-0-page-2.png").is_file())

    def test_unique_content_is_accepted_and_recorded_once(self):
        from unittest.mock import patch

        class FakePage:
            url = "https://drive.google.com/file/d/example/preview"

        with tempfile.TemporaryDirectory() as temp:
            page = FakePage()
            seen = {_normalized_content_hash("Page 1 of 3\\nEarlier page")}
            visible = "Page 2 of 3\\nCurrent page"
            with patch("public_preview_shards._capture_stable_page", return_value=visible):
                result, raw_hash, content_hash = _capture_unique_page(
                    page=page, seen_content_hashes=seen,
                    page_control_selector='input[aria-label^="Page is"]',
                    page_number=2, page_count=3,
                    page_marker_template="Page {page} of {count}",
                    shard=0, output_dir=Path(temp),
                    per_page_deadline=1, poll_ms=10,
                )
            self.assertEqual(result, visible)
            self.assertEqual(raw_hash, hashlib.sha256(visible.encode()).hexdigest())
            self.assertIn(content_hash, seen)


class NavigationRetryTests(unittest.TestCase):
    def test_navigation_retries_the_stuck_page_without_restarting_shard(self):
        class FakeControl:
            def __init__(self, page):
                self.page = page
            def count(self):
                return 1
            def click(self):
                pass
            def fill(self, value):
                self.page.target = value
            def press(self, key):
                self.page.press_count += 1
                if self.page.press_count >= 2:
                    self.page.selected = self.page.target
            def input_value(self, timeout=None):
                return self.page.selected

        class FakeBody:
            def __init__(self, page):
                self.page = page
            def inner_text(self, timeout=None):
                return f"Page {self.page.selected} of 2\nVisible records"

        class FakePage:
            def __init__(self):
                self.selected = "1"
                self.target = "1"
                self.press_count = 0
                self.url = "https://drive.google.com/file/d/example/preview"
                self.body = FakeBody(self)
            def locator(self, selector):
                return FakeControl(self)
            def wait_for_selector(self, selector, state=None, timeout=None):
                return None
            def wait_for_timeout(self, milliseconds):
                return None

        with tempfile.TemporaryDirectory() as temp:
            page = FakePage()
            result = _capture_stable_page(
                page=page, body=page.body,
                page_control_selector='input[aria-label^="Page is"]',
                page_number=2, page_count=2,
                page_marker_template="Page {page} of {count}", shard=0,
                output_dir=Path(temp), per_page_deadline=1, poll_ms=10,
            )
            self.assertIn("Page 2 of 2", result)
            self.assertEqual(page.press_count, 2)



    def test_access_challenge_stops_page_retry_immediately(self):
        class FakeControl:
            def __init__(self, page):
                self.page = page
            def count(self):
                return 1
            def click(self):
                pass
            def fill(self, value):
                self.page.target = value
            def press(self, key):
                self.page.press_count += 1
                self.page.selected = self.page.target
            def input_value(self, timeout=None):
                return self.page.selected

        class FakeBody:
            def inner_text(self, timeout=None):
                return "Please verify you are human"

        class FakePage:
            def __init__(self):
                self.selected = "1"
                self.target = "1"
                self.press_count = 0
                self.url = "https://drive.google.com/file/d/example/preview"
            def locator(self, selector):
                return FakeControl(self)
            def wait_for_selector(self, selector, state=None, timeout=None):
                return None
            def wait_for_timeout(self, milliseconds):
                return None

        with tempfile.TemporaryDirectory() as temp:
            page = FakePage()
            with self.assertRaises(AccessChallengeError):
                _capture_stable_page(
                    page=page, body=FakeBody(),
                    page_control_selector='input[aria-label^="Page is"]',
                    page_number=2, page_count=2,
                    page_marker_template="Page {page} of {count}",
                    shard=0, output_dir=Path(temp),
                    per_page_deadline=1, poll_ms=10,
                )
            self.assertEqual(page.press_count, 1)


class MergeValidationTests(unittest.TestCase):
    def _metadata(self):
        return [
            {"shard": 0, "shards": 2, "page_start": 1, "page_end": 2, "page_count": 3, "pages_captured": 2},
            {"shard": 1, "shards": 2, "page_start": 3, "page_end": 3, "page_count": 3, "pages_captured": 1},
        ]

    def test_metadata_requires_complete_ranges(self):
        self.assertEqual(validate_shard_metadata(self._metadata(), 2), 3)

    def test_metadata_rejects_gap_or_overlap(self):
        broken = self._metadata()
        broken[1]["page_start"] = 2
        with self.assertRaises(ValueError):
            validate_shard_metadata(broken, 2)

    def test_merge_writes_manifest_and_exact_page_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for item in self._metadata():
                snapshots = []
                for page in range(item["page_start"], item["page_end"] + 1):
                    text = f"Page {page} of 3\nRecord {page}"
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    })
                archive = root / f"shard-{item['shard']}-snapshots.jsonl.gz"
                with gzip.open(archive, "wt", encoding="utf-8") as stream:
                    for snapshot in snapshots:
                        stream.write(json.dumps(snapshot) + "\n")
                item["snapshot_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                (root / f"shard-{item['shard']}.json").write_text(json.dumps(item), encoding="utf-8")

            manifest = merge_shards(shard_count=2, output_dir=root)
            self.assertTrue(manifest["page_coverage_complete"])
            self.assertEqual(manifest["viewer_pages_captured"], 3)
            lines = (root / "page-text-snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["viewer_page"] for line in lines], [1, 2, 3])

    def test_merge_rejects_snapshot_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for item in self._metadata():
                snapshots = []
                for page in range(item["page_start"], item["page_end"] + 1):
                    text = f"Page {page} of 3"
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": "wrong" if page == 2 else hashlib.sha256(text.encode()).hexdigest(),
                    })
                archive = root / f"shard-{item['shard']}-snapshots.jsonl.gz"
                with gzip.open(archive, "wt", encoding="utf-8") as stream:
                    for snapshot in snapshots:
                        stream.write(json.dumps(snapshot) + "\n")
                item["snapshot_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                (root / f"shard-{item['shard']}.json").write_text(json.dumps(item), encoding="utf-8")

            with self.assertRaises(RuntimeError):
                merge_shards(shard_count=2, output_dir=root)


if __name__ == "__main__":
    unittest.main()
