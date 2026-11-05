import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extractor"))
from public_preview_shards import _capture_stable_page


class StalePageTests(unittest.TestCase):
    def test_updated_counter_does_not_accept_previous_page_body(self):
        class Control:
            def __init__(self, page):
                self.page = page
            def count(self): return 1
            def click(self): pass
            def fill(self, value): self.page.target = value
            def press(self, key):
                self.page.selected = self.page.target
                self.page.press_count += 1
            def input_value(self, timeout=None): return self.page.selected

        class Body:
            def inner_text(self, timeout=None):
                return "Page 2 of 2\\nSame stale page text"

        class Page:
            def __init__(self):
                self.selected = "1"
                self.target = "1"
                self.press_count = 0
                self.url = "https://drive.google.com/file/d/example/preview"
            def locator(self, selector): return Control(self)
            def wait_for_selector(self, selector, state=None, timeout=None): pass
            def wait_for_timeout(self, milliseconds): pass
            def screenshot(self, path, full_page=True): Path(path).write_bytes(b"fixture")

        with tempfile.TemporaryDirectory() as temp:
            page = Page()
            with self.assertRaisesRegex(RuntimeError, "did not stabilize"):
                _capture_stable_page(
                    page=page, body=Body(),
                    page_control_selector='input[aria-label^="Page is"]',
                    page_number=2, page_count=2,
                    page_marker_template="Page {page} of {count}",
                    shard=0, output_dir=Path(temp),
                    per_page_deadline=1, poll_ms=10,
                    previous_page_text="Page 1 of 2\\nSame stale page text",
                )
            self.assertEqual(page.press_count, 3)


if __name__ == "__main__":
    unittest.main()
