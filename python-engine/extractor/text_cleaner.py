import re
import unicodedata


def clean_text(value: str) -> str:
    """Normalize Unicode and whitespace without changing the source file."""
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def nonempty_lines(value: str) -> list[str]:
    """Return cleaned non-empty lines in their original order."""
    return [clean_text(line) for line in (value or "").splitlines() if clean_text(line)]
