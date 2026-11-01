import tempfile
import unittest
from pathlib import Path

from extractor.pdf_parser import PDFExtractionError, extract_pdf_lines
from extractor.text_cleaner import clean_text, nonempty_lines


class TextCleaningTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace(self):
        self.assertEqual(clean_text("  MARIA\u00a0  SANTOS  "), "MARIA SANTOS")

    def test_nonempty_lines(self):
        self.assertEqual(nonempty_lines("A\n\n B \n"), ["A", "B"])


class PDFParserTests(unittest.TestCase):
    def test_missing_pdf_is_rejected(self):
        with self.assertRaises(PDFExtractionError):
            extract_pdf_lines("does-not-exist.pdf")

    def test_non_pdf_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_text("sample", encoding="utf-8")
            with self.assertRaises(PDFExtractionError):
                extract_pdf_lines(path)


if __name__ == "__main__":
    unittest.main()
