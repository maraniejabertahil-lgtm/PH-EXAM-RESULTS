from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from extractor.pdf_parser import (
    InvalidPDFError,
    PDFExtractionError,
    extract_pdf,
    tables_to_dataframes,
)


def build_minimal_pdf(text: str = "001 JOHN DOE") -> bytes:
    """Build a tiny one-page PDF fixture without adding another dependency."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


class PDFParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_extracts_page_text_and_fingerprints_source(self) -> None:
        pdf = self.root / "sample.pdf"
        pdf.write_bytes(build_minimal_pdf())

        result = extract_pdf(pdf)

        self.assertEqual(result["extraction_status"], "raw_extraction_complete")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["pages"][0]["page_number"], 1)
        self.assertIn("001 JOHN DOE", result["pages"][0]["text"])
        self.assertEqual(len(result["source_file_sha256"]), 64)
        self.assertEqual(result["source_file_size_bytes"], pdf.stat().st_size)
        self.assertEqual(tables_to_dataframes(result), [])

    def test_rejects_html_or_non_pdf_input(self) -> None:
        invalid = self.root / "login.html"
        invalid.write_text("<html>Sign in</html>", encoding="utf-8")
        with self.assertRaises(InvalidPDFError):
            extract_pdf(invalid)

    def test_rejects_missing_input(self) -> None:
        with self.assertRaises(PDFExtractionError):
            extract_pdf(self.root / "missing.pdf")

    def test_rejects_pdf_signature_with_unparseable_content(self) -> None:
        invalid = self.root / "broken.pdf"
        invalid.write_bytes(b"%PDF-1.7\nnot a real PDF document")
        with self.assertRaises(PDFExtractionError):
            extract_pdf(invalid)

    def test_table_conversion_preserves_sequence_values_as_strings(self) -> None:
        extraction = {
            "pages": [
                {
                    "tables": [
                        [["SEQ", "NAME"], ["001", "DOE, JOHN A"], ["002", "SMITH, JANE B"]]
                    ]
                }
            ]
        }
        frames = tables_to_dataframes(extraction)
        self.assertEqual(len(frames), 1)
        self.assertEqual(list(frames[0].columns), ["column_1", "column_2"])
        self.assertEqual(frames[0].iloc[1, 0], "001")
        self.assertEqual(frames[0].iloc[1, 1], "DOE, JOHN A")


if __name__ == "__main__":
    unittest.main()
