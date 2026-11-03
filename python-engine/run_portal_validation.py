import argparse
import json
import sys
from pathlib import Path

from portal_batch_validate import PortalBatchError, validate_portal_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a reviewed CSC official portal batch.")
    parser.add_argument("batch", help="Repository-relative batch JSON path.")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    batch_path = (root / args.batch).resolve()
    try:
        batch_path.relative_to(root)
    except ValueError:
        print("VALIDATION STOPPED: batch path must remain inside the repository.", file=sys.stderr)
        return 1
    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        result = validate_portal_batch(batch, repository_root=root)
    except (OSError, json.JSONDecodeError, PortalBatchError, ValueError, TypeError) as exc:
        print(f"VALIDATION STOPPED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "greenlight_score": result["report"]["greenlight_score"],
        "publication_allowed": result["report"]["publication_allowed"],
        "report_path": str(result["report_path"]),
        "manifest": result["manifest"],
        "evidence": result["evidence"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
