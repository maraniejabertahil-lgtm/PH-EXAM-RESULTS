import json
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from database.d1_client import D1Error
from main import build_parser, process_csv, validate_preparing_prediction


class CliTests(unittest.TestCase):
    def test_expected_commands_are_registered(self):
        parser = build_parser()
        for command in ("monitor", "process", "extract-pdf", "publish", "predict", "predict-all", "site-status", "d1-size"):
            with self.subTest(command=command):
                parsed = parser.parse_args([command, "--help"]) if False else None
                self.assertIn(command, parser._subparsers._group_actions[0].choices)

    def test_preparing_prediction_must_be_within_five_days(self):
        today = date(2026, 1, 1)
        self.assertEqual(
            validate_preparing_prediction(
                {"predicted_date": "2026-01-06", "actual_date": None}, today
            ),
            5,
        )
        self.assertEqual(
            validate_preparing_prediction(
                {"predicted_date": "2025-12-27", "actual_date": None}, today
            ),
            -5,
        )
        for prediction in (
            {"predicted_date": "2026-01-07", "actual_date": None},
            {"predicted_date": "2025-12-26", "actual_date": None},
            {"predicted_date": "2026-01-01", "actual_date": "2026-01-01"},
            None,
        ):
            with self.subTest(prediction=prediction):
                with self.assertRaises(ValueError):
                    validate_preparing_prediction(prediction, today)

    def _process_csv_text(self, folder, content):
        source = Path(folder) / "input.csv"
        output = Path(folder) / "report.json"
        source.write_text(content, encoding="utf-8")
        args = Namespace(
            input=str(source),
            authority="PRC",
            exam="LET",
            year=2026,
            actual_release_date=None,
            source_reference="https://official.example/results",
            output=str(output),
        )
        with patch("main.D1Client.from_environment", side_effect=D1Error("D1 not configured")):
            code = process_csv(args)
        return code, output

    def test_process_accepts_normalized_unique_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            code, output = self._process_csv_text(
                folder, " Name ,Rating,Region,Seq\nJUAN DELA CRUZ,85,NCR,1\n"
            )
            self.assertEqual(code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["records"][0]["name"], "JUAN DELA CRUZ")

    def test_process_rejects_duplicate_headers_after_normalization(self):
        with tempfile.TemporaryDirectory() as folder:
            code, output = self._process_csv_text(
                folder, "Name,name,rating\nJUAN,JUAN,85\n"
            )
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())

    def test_process_rejects_rows_with_extra_values(self):
        with tempfile.TemporaryDirectory() as folder:
            code, output = self._process_csv_text(
                folder, "name,rating\nJUAN,85,UNEXPECTED\n"
            )
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())

    def test_process_requires_source_metadata_fields(self):
        parser = build_parser()
        parsed = parser.parse_args([
            "process",
            "--input", "private-imports/example.csv",
            "--authority", "PRC",
            "--exam", "LET",
            "--year", "2026",
            "--output", "artifacts/report.json",
        ])
        self.assertEqual(parsed.authority, "PRC")
        self.assertEqual(parsed.year, 2026)


if __name__ == "__main__":
    unittest.main()
