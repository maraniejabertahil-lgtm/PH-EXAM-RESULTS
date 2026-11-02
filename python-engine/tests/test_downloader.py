import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper.downloader import DownloadError, download_approved_file


class FakeRedirectResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://example.com:8443/file.csv"


class DownloaderSafetyTests(unittest.TestCase):
    def test_rejects_redirect_to_different_https_port(self):
        source = {
            "id": "official-port-redirect",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://example.com/file.csv",
        }
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "file.csv"
            with patch("scraper.downloader.open_same_origin", return_value=FakeRedirectResponse()):
                with self.assertRaises(DownloadError):
                    download_approved_file(source, target)
            self.assertFalse(target.exists())

    def test_rejects_non_https_url_from_approved_source(self):
        source = {
            "id": "official-test",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "http://example.com/file.csv",
        }
        with self.assertRaises(DownloadError):
            download_approved_file(source, "/tmp/should-not-exist.csv")

    def test_rejects_credentials_embedded_in_source_url(self):
        source = {
            "id": "official-credentials",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://user:password@example.com/file.csv",
        }
        with self.assertRaises(DownloadError):
            download_approved_file(source, "/tmp/should-not-exist.csv")

    def test_rejects_non_text_source_url(self):
        source = {
            "id": "official-invalid-url",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": 12345,
        }
        with self.assertRaises(DownloadError):
            download_approved_file(source, "/tmp/should-not-exist.csv")

    def test_rejects_google_drive_file_id_not_in_allowlist_before_network(self):
        source = {
            "id": "csc-drive",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "drive_file_ids": ["approved-file-id-123456"],
            "url": "https://drive.google.com/uc?export=download&id=other-file-id-123456",
        }
        with patch("scraper.downloader.build_opener") as opener:
            with self.assertRaisesRegex(DownloadError, "exact approved file ID"):
                download_approved_file(source, "/tmp/not-downloaded.pdf")
        opener.assert_not_called()

    def test_google_drive_redirect_allowlist_rejects_non_google_hosts(self):
        from scraper.downloader import GoogleDriveRedirectHandler
        self.assertTrue(GoogleDriveRedirectHandler._allowed(
            "https://drive.usercontent.google.com/download?id=approved"
        ))
        self.assertFalse(GoogleDriveRedirectHandler._allowed(
            "https://malicious.example/download"
        ))
        self.assertFalse(GoogleDriveRedirectHandler._allowed(
            "http://drive.google.com/download"
        ))

    def test_rejects_unverified_third_party_source(self):
        source = {
            "id": "third-party-test",
            "source_type": "verified_third_party",
            "verified_by_owner": False,
            "enabled": True,
            "url": "https://example.com/file.csv",
        }
        with self.assertRaises(DownloadError):
            download_approved_file(source, "/tmp/should-not-exist.csv")


if __name__ == "__main__":
    unittest.main()
