import gzip
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

EXTRACTOR_DIR = Path(__file__).resolve().parents[1] / "extractor"
sys.path.insert(0, str(EXTRACTOR_DIR))

from public_preview_shards import (  # noqa: E402
    _challenge_present,
    _wait_for_page_stability,
    AccessChallengeError,
    DEFAULT_PAGE_COUNT_REGEX,
    merge_shards,
    partition_page_ranges,
    validate_shard_metadata,
)



class NavigationRetryTests(unittest.TestCase):
    class FakePage:
        url = "https://drive.google.com/file/d/example/preview"

        def wait_for_timeout(self, milliseconds):
            time.sleep(min(milliseconds / 1000, 0.002))

    class FakeControl:
        def __init__(self):
            self.current_page = "1"
            self.target_page = "1"
            self.submissions = 0

        def click(self):
            return None

        def fill(self, value):
            self.target_page = value

        def press(self, key):
            if key != "Enter":
                raise AssertionError("expected Enter")
            self.submissions += 1
            # Simulate a viewer that ignores its first page-change request.
            if self.submissions >= 2:
                self.current_page = self.target_page

        def input_value(self, timeout=None):
            return self.current_page

    class FakeHeading:
        def __init__(self, control):
            self.control = control

        def count(self):
            return 1

        def inner_text(self, timeout=None):
            return f"Page {self.control.current_page} of 5"

    class FakeContent:
        def __init__(self, control, text_factory=None):
            self.control = control
            self.text_factory = text_factory

        def count(self):
            return 1

        def get_attribute(self, name):
            return "ndfHFb-c4YZDc-cYSp0e-DARUcf-Df1ZY-bN97Pc-haAclf"

        def inner_text(self, timeout=None):
            if self.text_factory:
                return self.text_factory(self.control.current_page)
            return f"{self.control.current_page} TEST, PERSON"

    class FakeBody:
        def inner_text(self, timeout=None):
            return "Public Google Drive preview"

    def _run(self, control, content=None, body=None, previous_last_sequence=None):
        return _wait_for_page_stability(
            page=self.FakePage(),
            body=body or self.FakeBody(),
            heading=self.FakeHeading(control),
            content=content or self.FakeContent(control),
            control=control,
            page_number=2,
            marker="Page 2 of 5",
            per_page_deadline=0.005,
            poll_ms=10,
            previous_last_sequence=previous_last_sequence,
        )

    def test_retries_a_stale_page_and_accepts_only_the_requested_page(self):
        control = self.FakeControl()
        visible, attempts, sequences = self._run(control)
        self.assertEqual(attempts, 2)
        self.assertIn("2 TEST, PERSON", visible)
        self.assertEqual(sequences, [2])
        self.assertEqual(control.current_page, "2")

    def test_blank_page_is_never_accepted_even_when_page_number_matches(self):
        control = self.FakeControl()
        control.current_page = "2"
        content = self.FakeContent(control, lambda _page: "")
        with self.assertRaisesRegex(RuntimeError, "page_sequence_count"):
            self._run(control, content=content)
        self.assertEqual(control.submissions, 3)

    def test_noncontiguous_page_records_are_rejected(self):
        control = self.FakeControl()
        control.current_page = "2"
        content = self.FakeContent(
            control,
            lambda _page: "2 TEST, PERSON\\n4 TEST, PERSON",
        )
        with self.assertRaisesRegex(RuntimeError, "page_sequence_count"):
            self._run(control, content=content)

    def test_page_must_continue_from_previous_sequence(self):
        control = self.FakeControl()
        control.current_page = "2"
        content = self.FakeContent(control, lambda _page: "2 TEST, PERSON")
        with self.assertRaisesRegex(RuntimeError, "previous_last_sequence"):
            self._run(control, content=content, previous_last_sequence=10)

    def test_access_challenge_is_not_retried_or_treated_as_a_pass(self):
        control = self.FakeControl()

        class ChallengeBody:
            def inner_text(self, timeout=None):
                return "Please verify you are human"

        with self.assertRaises(AccessChallengeError):
            self._run(control, body=ChallengeBody())
        self.assertEqual(control.submissions, 1)


class PartitionTests(unittest.TestCase):
    def test_901_pages_matches_proven_16_shard_partition(self):
        ranges = partition_page_ranges(901, 16)
        self.assertEqual(ranges[0], (0, 1, 57))
        self.assertEqual(ranges[14], (14, 799, 855))
        self.assertEqual(ranges[15], (15, 856, 901))
        self.assertEqual(sum(end - start + 1 for _, start, end in ranges), 901)

    def test_page_count_parser_accepts_a_viewer_that_opens_on_page_two(self):
        import re
        match = re.search(DEFAULT_PAGE_COUNT_REGEX, "Page 2 of 368")
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), 368)

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
                    screenshot_name = f"shard-{item['shard']}-page-{page:04d}.png"
                    screenshot_path = root / screenshot_name
                    screenshot_path.write_bytes(f"fake-png-{page}".encode())
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "screenshot": screenshot_name,
                        "screenshot_sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
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
                    screenshot_name = f"shard-{item['shard']}-page-{page:04d}.png"
                    screenshot_path = root / screenshot_name
                    screenshot_path.write_bytes(f"fake-png-{page}".encode())
                    snapshots.append({
                        "viewer_page": page, "text": text,
                        "sha256": "wrong" if page == 2 else hashlib.sha256(text.encode()).hexdigest(),
                        "screenshot": screenshot_name,
                        "screenshot_sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
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
