import unittest

from scraper.downloader import DownloadError, download_approved_file


class DownloaderSafetyTests(unittest.TestCase):
    def test_rejects_non_https_url(self):
        with self.assertRaises(DownloadError):
            download_approved_file("http://example.com/file.csv", "/tmp/should-not-exist.csv")


if __name__ == "__main__":
    unittest.main()
