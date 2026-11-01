import unittest
from urllib.request import Request

from scraper.safe_http import SameOriginRedirectHandler, UnsafeRedirectError


class SameOriginRedirectTests(unittest.TestCase):
    def setUp(self):
        self.handler = SameOriginRedirectHandler("https://official.example/results")
        self.request = Request("https://official.example/results")

    def test_allows_redirect_on_same_https_host_and_port(self):
        redirected = self.handler.redirect_request(
            self.request, None, 302, "Found", {}, "https://official.example/archive/results"
        )
        self.assertEqual(redirected.full_url, "https://official.example/archive/results")

    def test_rejects_cross_host_redirect_before_following(self):
        with self.assertRaises(UnsafeRedirectError):
            self.handler.redirect_request(
                self.request, None, 302, "Found", {}, "https://attacker.example/collect"
            )

    def test_rejects_same_host_redirect_to_another_port(self):
        with self.assertRaises(UnsafeRedirectError):
            self.handler.redirect_request(
                self.request, None, 302, "Found", {}, "https://official.example:8443/private"
            )

    def test_rejects_redirect_with_embedded_credentials(self):
        with self.assertRaises(UnsafeRedirectError):
            self.handler.redirect_request(
                self.request, None, 302, "Found", {}, "https://user:pass@official.example/private"
            )


if __name__ == "__main__":
    unittest.main()
