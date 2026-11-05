import json
import unittest
from urllib.parse import parse_qs

from publisher.broadcaster import BroadcastError, Settings, broadcast, result_routes, send_facebook, send_telegram


class Response:
    status = 200
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.body).encode()


class Opener:
    def __init__(self, bodies): self.bodies, self.requests = list(bodies), []
    def __call__(self, request, timeout=15):
        self.requests.append(request)
        return Response(self.bodies.pop(0))


class Ledger:
    def __init__(self): self.data = {}
    def status(self, key): return self.data.get(key)
    def set_status(self, key, value): self.data[key] = value


class BroadcasterTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            "12345", "page-secret", "v24.0", "1234567890:abcdefghijklmnopqrstuvwxyz",
            "-1001234567890", "https://results.example", "deploy-1001",
            "owner/repo", "github-token",
        )
        self.ledger = Ledger()
        self.paths = ["public/data/PRC/LEPT-ELEMENTARY/2026/manifest.json"]

    def test_only_changed_result_manifests_are_routes(self):
        routes = result_routes(self.paths + ["public/index.html", "public/data/PRC/LEPT-ELEMENTARY/2026/data.json"])
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["exam"], "LEPT-ELEMENTARY")

    def test_broadcast_blocked_before_deployment_success(self):
        with self.assertRaisesRegex(BroadcastError, "has not succeeded"):
            broadcast(self.paths, self.settings, deployment_succeeded=False, ledger=self.ledger)

    def test_non_result_deploy_is_skipped(self):
        result = broadcast(["public/index.html"], self.settings, deployment_succeeded=True, ledger=self.ledger)
        self.assertEqual(result["status"], "skipped")

    def test_dry_run_never_calls_external_provider(self):
        def forbidden(*args, **kwargs): raise AssertionError("must not send")
        result = broadcast(self.paths, self.settings, deployment_succeeded=True, dry_run=True,
                           opener=forbidden, ledger=self.ledger)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("https://results.example/?authority=PRC", result["outcomes"][0]["message"])

    def test_facebook_post_token_is_not_in_url(self):
        fake = Opener([{"id": "12345_67890"}])
        result = send_facebook("new results", self.settings, fake)
        self.assertEqual(result["post_id"], "12345_67890")
        self.assertNotIn("page-secret", fake.requests[0].full_url)
        self.assertEqual(parse_qs(fake.requests[0].data.decode())["access_token"], ["page-secret"])

    def test_telegram_requires_provider_confirmation(self):
        fake = Opener([{"ok": True, "result": {"message_id": 77}}])
        self.assertEqual(send_telegram("new results", self.settings, fake)["message_id"], 77)

    def test_successful_channels_are_not_sent_twice(self):
        fake = Opener([{"id": "post-1"}, {"ok": True, "result": {"message_id": 2}}])
        first = broadcast(self.paths, self.settings, deployment_succeeded=True, opener=fake, ledger=self.ledger)
        second = broadcast(self.paths, self.settings, deployment_succeeded=True, opener=fake, ledger=self.ledger)
        self.assertEqual(first["status"], "sent")
        self.assertTrue(all(item["status"] == "already_sent" for item in second["outcomes"]))
        self.assertEqual(len(fake.requests), 2)

    def test_uncertain_delivery_is_not_retried(self):
        key = "deploy-1001:PRC/LEPT-ELEMENTARY/2026:facebook"
        self.ledger.set_status(key, "pending")
        fake = Opener([])
        with self.assertRaisesRegex(BroadcastError, "reconciliation"):
            broadcast(self.paths, self.settings, deployment_succeeded=True, opener=fake, ledger=self.ledger)
        self.assertEqual(len(fake.requests), 0)

    def test_incomplete_facebook_credentials_fail_closed(self):
        bad = Settings("123", None, "v24.0", None, None, "https://results.example",
                       "deploy-1001", "owner/repo", "github-token")
        with self.assertRaisesRegex(BroadcastError, "Facebook requires"):
            send_facebook("hello", bad)

    def test_non_https_site_url_is_rejected(self):
        bad = Settings("123", "token", "v24.0", None, None, "http://results.example",
                       "deploy-1001", "owner/repo", "github-token")
        with self.assertRaisesRegex(BroadcastError, "HTTPS"):
            broadcast(self.paths, bad, deployment_succeeded=True, ledger=self.ledger)


if __name__ == "__main__":
    unittest.main()
