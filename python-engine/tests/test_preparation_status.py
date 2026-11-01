import tempfile
import unittest
from pathlib import Path

from preparation.status_builder import build_status, write_status


class PreparationStatusTests(unittest.TestCase):
    def test_search_status_has_no_preparation_data(self):
        self.assertEqual(build_status("search"), {
            "schema_version": 1,
            "mode": "search",
            "preparation": None,
        })

    def test_preparing_progress_comes_from_fixed_stage(self):
        status = build_status(
            "preparing",
            authority="PRC",
            exam="LET",
            year=2026,
            examination_name="PRC – LET Examination",
            stage="validating",
        )
        self.assertEqual(status["preparation"]["percentage"], 70)
        self.assertEqual(status["preparation"]["status"], "Validating examination records")

    def test_rejects_arbitrary_stage(self):
        with self.assertRaises(ValueError):
            build_status(
                "preparing",
                authority="PRC",
                exam="LET",
                year=2026,
                examination_name="PRC – LET Examination",
                stage="75_percent",
            )

    def test_preparing_rejects_unsafe_exam_identifiers(self):
        with self.assertRaises(ValueError):
            build_status(
                mode="preparing",
                authority="PRC",
                exam="LET/2026",
                year=2026,
                examination_name="PRC – LET Examination",
                stage="monitoring",
            )

    def test_writes_status_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "site-status.json"
            write_status(path, mode="search")
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
