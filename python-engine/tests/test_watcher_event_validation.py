import unittest
from urllib.parse import urlsplit

from watcher_event_validation import is_approved_drive_event


class WatcherEventValidationTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "url": "https://www.prc.gov.ph/node/9450",
            "allow_linked_drive_documents": True,
            "drive_file_ids": ["1OwnerApprovedDriveFileId_123"],
        }
        self.payload = {
            "detected_url": "https://drive.google.com/uc?export=download&id=1NewlyPublishedOfficialDriveFile_2026",
            "source_page_url": self.source["url"],
            "detection_method": "official_page_drive_link",
        }

    def accepted(self, payload=None, source=None):
        event = payload or self.payload
        registry_source = source or self.source
        return is_approved_drive_event(
            event, registry_source, urlsplit(event["detected_url"])
        )

    def test_accepts_new_id_only_with_exact_owner_enabled_official_page_provenance(self):
        self.assertTrue(self.accepted())

    def test_accepts_exact_static_allowlisted_id_without_dynamic_discovery(self):
        payload = {
            "detected_url": "https://drive.google.com/uc?export=download&id=1OwnerApprovedDriveFileId_123"
        }
        source = {**self.source, "allow_linked_drive_documents": False}
        self.assertTrue(self.accepted(payload, source))

    def test_rejects_new_id_when_opt_in_is_disabled(self):
        self.assertFalse(self.accepted(source={**self.source, "allow_linked_drive_documents": False}))

    def test_rejects_wrong_source_page(self):
        self.assertFalse(self.accepted(payload={**self.payload, "source_page_url": "https://evil.example/page"}))

    def test_rejects_wrong_detection_method(self):
        self.assertFalse(self.accepted(payload={**self.payload, "detection_method": "approved_drive_fallback"}))

    def test_rejects_drive_lookalike_host(self):
        payload = {**self.payload, "detected_url": self.payload["detected_url"].replace(
            "drive.google.com", "drive.google.com.evil.example"
        )}
        self.assertFalse(self.accepted(payload))

    def test_rejects_noncanonical_download_path(self):
        payload = {**self.payload, "detected_url": self.payload["detected_url"].replace(
            "/uc?", "/open?"
        )}
        self.assertFalse(self.accepted(payload))

    def test_rejects_duplicate_file_id_parameters(self):
        payload = {**self.payload, "detected_url": self.payload["detected_url"] + "&id=anotherFileId_123"}
        self.assertFalse(self.accepted(payload))

    def test_rejects_unusual_port(self):
        payload = {**self.payload, "detected_url": self.payload["detected_url"].replace(
            "drive.google.com/", "drive.google.com:444/"
        )}
        self.assertFalse(self.accepted(payload))


    def test_rejects_malformed_port(self):
        payload = {**self.payload, "detected_url": self.payload["detected_url"].replace(
            "drive.google.com/", "drive.google.com:bad/"
        )}
        self.assertFalse(self.accepted(payload))

    def test_rejects_malformed_file_id(self):
        payload = {**self.payload, "detected_url": "https://drive.google.com/uc?export=download&id=short"}
        self.assertFalse(self.accepted(payload))


    def test_accepts_same_origin_official_result_article_provenance(self):
        source = {
            **self.source,
            "discover_official_result_articles": True,
        }
        payload = {
            **self.payload,
            "source_page_url": source["url"],
            "source_article_url": "https://www.prc.gov.ph/node/9450",
        }
        self.assertTrue(self.accepted(payload, source))

    def test_rejects_missing_article_provenance_when_article_discovery_is_enabled(self):
        source = {**self.source, "discover_official_result_articles": True}
        payload = {**self.payload, "source_page_url": source["url"]}
        self.assertFalse(self.accepted(payload, source))

    def test_rejects_cross_origin_article_provenance(self):
        source = {**self.source, "discover_official_result_articles": True}
        payload = {
            **self.payload,
            "source_page_url": source["url"],
            "source_article_url": "https://evil.example/node/9450",
        }
        self.assertFalse(self.accepted(payload, source))

    def test_rejects_article_url_outside_official_result_path(self):
        source = {**self.source, "discover_official_result_articles": True}
        payload = {
            **self.payload,
            "source_page_url": source["url"],
            "source_article_url": "https://www.prc.gov.ph/downloads/passers.pdf",
        }
        self.assertFalse(self.accepted(payload, source))

    def test_rejects_article_url_with_query_or_fragment(self):
        source = {**self.source, "discover_official_result_articles": True}
        payload = {
            **self.payload,
            "source_page_url": source["url"],
            "source_article_url": "https://www.prc.gov.ph/node/9450?next=evil",
        }
        self.assertFalse(self.accepted(payload, source))

    def test_rejects_article_provenance_when_source_did_not_enable_article_discovery(self):
        payload = {
            **self.payload,
            "source_page_url": self.source["url"],
            "source_article_url": "https://www.prc.gov.ph/node/9450",
        }
        self.assertFalse(self.accepted(payload, self.source))


if __name__ == "__main__":
    unittest.main()
