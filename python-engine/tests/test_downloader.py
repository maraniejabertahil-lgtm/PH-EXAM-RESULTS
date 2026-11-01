import unittest

from scraper.downloader import DownloadError, download_approved_file


class DownloaderSafetyTests(unittest.TestCase):
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
