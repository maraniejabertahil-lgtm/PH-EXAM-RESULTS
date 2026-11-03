import unittest

from processor.normalizer import NormalizationError, normalize_extracted_tables


class PDFTableNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.extraction = {
            "pages": [
                {"page_number": 1, "tables": [[
                    ["NAME", "SEQ", "RATING", "REGION"],
                    ["DOE, JANE A", "001", "88.5", "NCR"],
                    ["SMITH, JOHN B", "002", None, "REGION III"],
                ]]},
                {"page_number": 2, "tables": [[
                    ["NAME", "SEQ", "RATING", "REGION"],
                    ["GARCIA, ANA C", "003", "91", "NCR"],
                ]]},
            ]
        }
        self.mapping = {
            "table_indexes": [0],
            "header_rows": 1,
            "name_column": 0,
            "sequence_column": 1,
            "rating_column": 2,
            "region_column": 3,
        }

    def test_normalizes_explicit_columns_across_pages(self):
        rows = normalize_extracted_tables(self.extraction, self.mapping)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sequence_number"], "001")
        self.assertEqual(rows[1]["rating"], None)
        self.assertEqual(rows[2]["name"], "GARCIA, ANA C")

    def test_rejects_missing_name(self):
        bad = {"pages": [{"tables": [[["N", "S"], ["", "001"]]]}]}
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(bad, {
                "table_indexes": [0], "name_column": 0, "sequence_column": 1,
            })

    def test_rejects_missing_sequence_in_nonempty_row(self):
        bad = {"pages": [{"tables": [[["DOE, JANE", ""]]]}]}
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(bad, {
                "table_indexes": [0], "name_column": 0, "sequence_column": 1,
            })

    def test_rejects_short_rows_instead_of_guessing(self):
        bad = {"pages": [{"tables": [[["DOE, JANE"]]]}]}
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(bad, {
                "table_indexes": [0], "name_column": 0, "sequence_column": 1,
            })

    def test_rejects_invalid_or_duplicate_column_mappings(self):
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(self.extraction, {
                "table_indexes": [0], "name_column": 0, "sequence_column": 0,
            })
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(self.extraction, {
                "table_indexes": [0, 0], "name_column": 0, "sequence_column": 1,
            })

    def test_does_not_invent_sequence_numbers(self):
        bad = {"pages": [{"tables": [[["DOE, JANE"]]]}]}
        with self.assertRaises(NormalizationError):
            normalize_extracted_tables(bad, {
                "table_indexes": [0], "name_column": 0,
            })


if __name__ == "__main__":
    unittest.main()
