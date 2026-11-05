#!/usr/bin/env python3
"""Regression tests for NVIDIA model patch-format normalization."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair_patch_utils import normalize_patch

class PatchNormalizationTests(unittest.TestCase):
    def test_standard_unified_diff_gets_git_header(self):
        raw = "--- a/watcher-bot/src/example.js\n+++ b/watcher-bot/src/example.js\n@@ -1 +1 @@\n-old\n+new\n"
        result = normalize_patch(raw)
        self.assertTrue(result.startswith("diff --git a/watcher-bot/src/example.js b/watcher-bot/src/example.js\n"))
        self.assertIn("@@ -1 +1 @@", result)

    def test_markdown_fence_is_removed(self):
        fence = chr(96) * 3
        raw = fence + "diff\n--- a/watcher-bot/src/example.js\n+++ b/watcher-bot/src/example.js\n@@ -1 +1 @@\n-old\n+new\n" + fence
        self.assertTrue(normalize_patch(raw).startswith("diff --git "))

    def test_added_markdown_fence_content_is_preserved(self):
        raw = "--- a/watcher-bot/src/example.js\\n+++ b/watcher-bot/src/example.js\\n@@ -1 +1 @@\\n-old\\n+```markdown\\n"
        self.assertIn("+```markdown", normalize_patch(raw))

    def test_existing_git_diff_is_preserved(self):
        raw = "diff --git a/watcher-bot/src/example.js b/watcher-bot/src/example.js\n--- a/watcher-bot/src/example.js\n+++ b/watcher-bot/src/example.js\n@@ -1 +1 @@\n-old\n+new\n"
        self.assertEqual(normalize_patch(raw), raw)

    def test_rejects_missing_headers(self):
        with self.assertRaises(ValueError):
            normalize_patch("Here is the fix: just replace the function")

    def test_rejects_path_mismatch(self):
        raw = "--- a/watcher-bot/src/a.js\n+++ b/watcher-bot/src/b.js\n@@ -1 +1 @@\n-a\n+b\n"
        with self.assertRaises(ValueError):
            normalize_patch(raw)

if __name__ == "__main__":
    unittest.main(verbosity=2)
