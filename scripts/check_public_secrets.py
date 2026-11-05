"""Fail-closed scan of browser-served files for accidental credentials."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{24,}"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
)


def scan(root: Path) -> list[str]:
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                findings.append(str(path))
                break
    return findings


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "public")
    matches = scan(target)
    if matches:
        print("Potential credential material found in browser-served files:")
        print("\n".join(matches))
        raise SystemExit(1)
    print("Public asset credential scan passed.")
