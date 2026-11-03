import tempfile
import unittest
from pathlib import Path

from acquisition.official_portal_handoff import (
    OfficialPortalHandoffError,
    verify_official_portal_handoff,
)


class OfficialPortalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "CSC-CSE-PORTAL",
            "authority": "CSC",
            "exam": "CSE-PPT-2026-03",
            "source_type": "official",
            "authorized": True,
            "enabled": True,
            "url": "https://exam.csc.gov.ph/list_passers?type_id=1",
            "content_access_mode": "owner_reviewed_portal_handoff",
        }

    def test_records_owner_reviewed_portal_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            result = verify_official_portal_handoff(
                source=self.source,
                portal_url="https://exam.csc.gov.ph/list_passers?type_id=1",
                evidence_path=Path(directory) / "evidence.json",
            )
        self.assertEqual(result["provenance"], "official_direct")
        self.assertFalse(result["automated_portal_access_attempted"])

    def test_rejects_unapproved_host(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OfficialPortalHandoffError):
                verify_official_portal_handoff(
                    source=self.source,
                    portal_url="https://example.org/list_passers",
                    evidence_path=Path(directory) / "evidence.json",
                )


if __name__ == "__main__":
    unittest.main()
