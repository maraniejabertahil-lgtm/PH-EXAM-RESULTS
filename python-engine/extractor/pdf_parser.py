from pathlib import Path

from extractor.text_cleaner import nonempty_lines


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be read safely."""


def extract_pdf_lines(path: str | Path) -> list[str]:
    """
    Extract text lines from a text-based PDF.

    This does not perform OCR and does not convert lines into passer records.
    Scanned PDFs or uncertain layouts must go to manual review.
    """
    source = Path(path)
    if not source.is_file():
        raise PDFExtractionError(f"PDF file does not exist: {source}")
    if source.suffix.lower() != ".pdf":
        raise PDFExtractionError("Input file must have a .pdf extension")

    try:
        import pdfplumber
    except ImportError as exc:
        raise PDFExtractionError(
            "pdfplumber is not installed; install python-engine/requirements.txt"
        ) from exc

    try:
        pages = []
        with pdfplumber.open(source) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return nonempty_lines("\n".join(pages))
    except Exception as exc:
        raise PDFExtractionError(f"Could not extract PDF text: {exc}") from exc
