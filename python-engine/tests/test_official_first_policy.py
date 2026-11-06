from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from acquisition.official_first_policy import (
    create_attempt_log,
    record_attempt,
    third_party_fallback_gate,
    write_attempt_log,
)


class OfficialFirstPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.log_path = self.root / "official-attempt.json"
        self.log = create_attempt_log(
            source_id="PRC-EXAM-RESULTS-HOMEPAGE",
            authority="PRC",
            exam="LICENSURE-EXAM-RESULTS",
            official_source_url="https://www.prc.gov.ph/articles/exam-results",
            official_document_url="https://www.prc.gov.ph/files/result.pdf?access_token=do-not-log&download=1",
        )

    def add_failed_official_attempts(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        record_attempt(
            self.log, method="GET_RANGE", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"<html>Access denied</html>",
        )
        record_attempt(
            self.log, method="GET", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"<html>Access denied</html>",
        )

    def test_fallback_is_denied_until_official_attempt_log_is_persisted(self) -> None:
        self.add_failed_official_attempts()
        self.assertEqual(
            third_party_fallback_gate(self.log_path),
            {"allowed": False, "reason": "official_attempt_log_not_persisted"},
        )

    def test_fallback_requires_head_and_get_attempts(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        write_attempt_log(self.log, self.log_path)
        self.assertEqual(
            third_party_fallback_gate(self.log_path)["reason"],
            "insufficient_official_retrieval_attempts",
        )

    def test_fallback_is_allowed_only_after_persisted_official_failures(self) -> None:
        self.add_failed_official_attempts()
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["provenance"], "third_party_fallback_pending_validation")

    def test_human_verification_barrier_requires_manual_drop(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"captcha: verify you are human",
        )
        record_attempt(
            self.log, method="GET", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "manual_drop_required_access_barrier")

    def test_login_interstitial_allows_only_public_third_party_fallback(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=200,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"Sign in - authentication required",
        )
        record_attempt(
            self.log, method="GET", status_code=200,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertTrue(result["allowed"])
        self.assertEqual(
            result["reason"],
            "official_authentication_required_public_fallback_allowed",
        )

    def test_authentication_barrier_never_permits_human_verification_bypass(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=200,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"Sign in - authentication required",
        )
        record_attempt(
            self.log, method="GET", status_code=403,
            content_type="text/html", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"CAPTCHA: verify you are human",
        )
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "manual_drop_required_access_barrier")


    def test_partial_range_pdf_does_not_count_as_complete_official_acquisition(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=200,
            content_type="application/pdf", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        record_attempt(
            self.log, method="GET_RANGE", status_code=206,
            content_type="application/pdf", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"%PDF-1.7\\npartial",
        )
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "official_attempts_lack_head_and_full_get_methods")

    def test_verified_full_official_pdf_blocks_fallback(self) -> None:
        record_attempt(
            self.log, method="HEAD", status_code=200,
            content_type="application/pdf", final_url="https://www.prc.gov.ph/files/result.pdf",
        )
        record_attempt(
            self.log, method="GET", status_code=200,
            content_type="application/pdf", final_url="https://www.prc.gov.ph/files/result.pdf",
            body_prefix=b"%PDF-1.7\nverified",
        )
        write_attempt_log(self.log, self.log_path)
        result = third_party_fallback_gate(self.log_path)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "official_pdf_available_use_official_direct")

    def test_sensitive_query_values_are_redacted_in_log(self) -> None:
        self.assertIn("access_token=%5BREDACTED%5D", self.log["official_document_url"])
        self.assertNotIn("do-not-log", json.dumps(self.log))

    def test_rejects_non_https_official_urls(self) -> None:
        with self.assertRaises(ValueError):
            create_attempt_log(
                source_id="X", authority="PRC", exam="Y",
                official_source_url="http://example.com", official_document_url="https://example.com/a.pdf",
            )


if __name__ == "__main__":
    unittest.main()
