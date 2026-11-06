"""Fail when common credential formats appear in published static assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("Telegram bot token", re.compile(rb"\b[0-9]{8,}:[A-Za-z0-9_-]{30,}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Facebook access token", re.compile(rb"\bEA[A-Za-z0-9]{40,}\b")),
    ("Bearer credential", re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{24,}")),
    ("literal secret assignment", re.compile(
        rb"(?i)(?:api[_-]?token|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][A-Za-z0-9._~+/-]{20,}['\"]"
    )),
)


def scan_public_assets(public_root: str | Path) -> list[tuple[str, str]]:
    root = Path(public_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Public asset directory does not exist: {root}")
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Public asset symlink escapes the scan directory: {path}") from exc
        contents = path.read_bytes()
        for label, pattern in PATTERNS:
            if pattern.search(contents):
                findings.append((relative.as_posix(), label))
    return findings


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    findings = scan_public_assets(repository_root / "public")
    if findings:
        for path, label in findings:
            print(f"Potential {label} in public/{path}", file=sys.stderr)
        return 1
    print("No common credential formats found in public assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
