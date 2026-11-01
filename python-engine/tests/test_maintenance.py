import json
import tempfile
import unittest
from pathlib import Path

from maintenance import validate_public_directory


class MaintenanceValidationTests(unittest.TestCase):
    def write_public(self, folder, manifest, status=None):
        root = Path(folder)
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        if status is not None:
            (data / "site-status.json").write_text(
                json.dumps(status), encoding="utf-8"
            )
        return root

    def test_accepts_empty_valid_public_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_public(
                folder,
                {"schema_version": 2, "authorities": {}},
                {"schema_version": 1, "mode": "search", "preparation": None},
            )
            self.assertEqual(validate_public_directory(root), [])

    def test_rejects_non_object_manifest_without_crashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_public(folder, [])
            errors = validate_public_directory(root)
        self.assertIn("Manifest must be a JSON object.", errors)

    def test_rejects_malformed_nested_manifest_without_crashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_public(
                folder,
                {"schema_version": 2, "authorities": {"PRC": []}},
                {"schema_version": 1, "mode": "search", "preparation": None},
            )
            errors = validate_public_directory(root)
        self.assertTrue(any("Invalid examination catalogue" in error for error in errors))

    def test_rejects_non_object_site_status_without_crashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_public(
                folder,
                {"schema_version": 2, "authorities": {}},
                [],
            )
            errors = validate_public_directory(root)
        self.assertIn("Site status must be a JSON object.", errors)

    def test_rejects_non_object_preparation_status_without_crashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_public(
                folder,
                {"schema_version": 2, "authorities": {}},
                {"schema_version": 1, "mode": "preparing", "preparation": []},
            )
            errors = validate_public_directory(root)
        self.assertIn("Preparing mode requires a preparation object.", errors)


if __name__ == "__main__":
    unittest.main()
