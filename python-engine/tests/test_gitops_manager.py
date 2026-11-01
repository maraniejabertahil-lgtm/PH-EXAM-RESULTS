import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from processor.normalizer import normalize_record
from publisher.gitops_manager import create_publication_pull_request


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class GitOpsIsolationTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(
            ["git", *args], cwd=root, check=True, text=True,
            capture_output=True
        ).stdout.strip()

    def test_each_publication_branch_starts_from_approved_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            remote = Path(temporary) / "remote.git"
            root.mkdir()
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
            self.git(root, "config", "user.name", "Test Owner")
            self.git(root, "config", "user.email", "owner@example.invalid")
            (root / "public" / "data").mkdir(parents=True)
            (root / "public" / "data" / "manifest.json").write_text(
                json.dumps({"schema_version": 2, "authorities": {}}),
                encoding="utf-8",
            )
            self.git(root, "add", ".")
            self.git(root, "commit", "-m", "Initial approved public state")
            self.git(root, "remote", "add", "origin", str(remote))
            self.git(root, "push", "-u", "origin", "main")

            reports = [
                {
                    "authority": "PRC",
                    "examination": "LET",
                    "year": 2026,
                    "records": [normalize_record({"name": "ALPHA PASSER"}, "PRC", "LET", 2026)],
                    "validation": {"total_records": 1, "valid_records": 1, "invalid_records": []},
                    "duplicates": {"exact_duplicates": [], "fuzzy_candidates": []},
                },
                {
                    "authority": "PRC",
                    "examination": "NLE",
                    "year": 2026,
                    "records": [normalize_record({"name": "BETA PASSER"}, "PRC", "NLE", 2026)],
                    "validation": {"total_records": 1, "valid_records": 1, "invalid_records": []},
                    "duplicates": {"exact_duplicates": [], "fuzzy_candidates": []},
                },
            ]

            with patch(
                "publisher.gitops_manager.urllib.request.urlopen",
                side_effect=[
                    FakeResponse({"number": 101, "html_url": "https://github.com/example/repo/pull/101"}),
                    FakeResponse({"number": 102, "html_url": "https://github.com/example/repo/pull/102"}),
                ],
            ):
                first = create_publication_pull_request(
                    root, reports[0], "example/repo", "test-token"
                )
                second = create_publication_pull_request(
                    root, reports[1], "example/repo", "test-token"
                )

            self.assertEqual(self.git(root, "branch", "--show-current"), "main")
            second_files = self.git(root, "ls-tree", "-r", "--name-only", second["commit_sha"])
            self.assertIn("public/data/prc/nle/2026-A-M.json", second_files)
            self.assertNotIn("public/data/prc/let/2026-A-M.json", second_files)
            self.assertNotEqual(first["branch"], second["branch"])


if __name__ == "__main__":
    unittest.main()
