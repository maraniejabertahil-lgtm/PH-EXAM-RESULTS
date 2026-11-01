import unittest

from main import build_parser


class CliTests(unittest.TestCase):
    def test_expected_commands_are_registered(self):
        parser = build_parser()
        for command in ("monitor", "process", "extract-pdf", "publish", "predict"):
            with self.subTest(command=command):
                parsed = parser.parse_args([command, "--help"]) if False else None
                self.assertIn(command, parser._subparsers._group_actions[0].choices)

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
