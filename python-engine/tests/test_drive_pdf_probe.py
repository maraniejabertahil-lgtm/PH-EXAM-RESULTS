import json
import tempfile
import unittest
from pathlib import Path

from drive_pdf_probe import (
    RetrievalError,
    load_approved_ids,
    validate_pdf_bytes,
    validate_redirect_url,
)


class DrivePdfProbeTests(unittest.TestCase):
    def make_registry(self, source_overrides=None):
        source = {
            "id": "CSC-CSE-PPT-2026-08-09-REGION-V",
            "authority": "CSC",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "direct_drive_fallback": True,
            "drive_file_ids": [
                "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l",
                "1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf",
            ],
        }
        source.update(source_overrides or {})
        temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        json.dump({"sources": [source]}, temp)
        temp.close()
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        return Path(temp.name)

    def test_loads_only_owner_approved_enabled_csc_ids(self):
        registry = self.make_registry()
        ids = load_approved_ids(registry, "CSC-CSE-PPT-2026-08-09-REGION-V")
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l")

    def test_rejects_source_without_explicit_fallback_approval(self):
        registry = self.make_registry({"direct_drive_fallback": False})
        with self.assertRaisesRegex(RetrievalError, "not enabled"):
            load_approved_ids(registry, "CSC-CSE-PPT-2026-08-09-REGION-V")

    def test_rejects_unapproved_or_malformed_drive_ids(self):
        registry = self.make_registry({"drive_file_ids": ["not a valid id"]})
        with self.assertRaisesRegex(RetrievalError, "invalid Drive file ID"):
            load_approved_ids(registry, "CSC-CSE-PPT-2026-08-09-REGION-V")

    def test_accepts_real_pdf_signature(self):
        validate_pdf_bytes(b"%PDF-1.7\n" + b"x" * 100)

    def test_rejects_html_interstitial_as_not_pdf(self):
        with self.assertRaisesRegex(RetrievalError, "not a verified PDF"):
            validate_pdf_bytes(b"<html>Access denied</html>")

    def test_allows_exact_googleusercontent_redirect(self):
        validate_redirect_url(
            "https://drive.usercontent.google.com/download?id=approvedFileId123&export=download",
            "approvedFileId123",
        )

    def test_rejects_redirect_to_unapproved_host(self):
        with self.assertRaisesRegex(RetrievalError, "Blocked Google Drive redirect"):
            validate_redirect_url(
                "https://attacker.example/download?id=approvedFileId123",
                "approvedFileId123",
            )

    def test_rejects_redirect_with_different_file_id(self):
        with self.assertRaisesRegex(RetrievalError, "Blocked Google Drive redirect"):
            validate_redirect_url(
                "https://drive.usercontent.google.com/download?id=otherFileId123",
                "approvedFileId123",
            )

    def test_rejects_non_https_redirect(self):
        with self.assertRaisesRegex(RetrievalError, "Blocked Google Drive redirect"):
            validate_redirect_url(
                "http://drive.google.com/uc?id=approvedFileId123",
                "approvedFileId123",
            )


if __name__ == "__main__":
    unittest.main()
