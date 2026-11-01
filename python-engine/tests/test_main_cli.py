import unittest
from datetime import date

from main import build_parser, validate_preparing_prediction


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
