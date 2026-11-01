import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


class GitOpsError(Exception):
    """Raised when a data publication Pull Request cannot be prepared."""


def _git(repo_root: Path, *arguments: str):
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitOpsError(result.stderr.strip() or result.stdout.strip() or "Git command failed.")
    return result.stdout.strip()


def create_publication_pull_request(
    repo_root: str | Path,
    report: dict,
    repository: str,
    token: str,
    source_reference: str = "",
    replace_existing: bool = False,
) -> dict:
    root = Path(repo_root).resolve()
    authority = report["authority"].lower()
    exam = report["examination"].lower().replace(" ", "-")
    year = int(report["year"])
    target_dir = root / "public" / "data" / authority / exam
    existing = list(target_dir.glob(f"{year}-*.json")) if target_dir.exists() else []
    if existing and not replace_existing:
        raise GitOpsError(
            "A dataset already exists for this examination and year. "
            "Re-run with explicit replace-existing approval to prepare a replacement PR."
        )

    batch_id = uuid4().hex[:8]
    branch_name = f"data-import/{authority}-{exam}-{year}-{batch_id}"
    _git(root, "switch", "-c", branch_name)

    from publisher.json_builder import build_public_datasets
    from publisher.manifest import build_manifest

    entries = build_public_datasets(
        report["records"],
        root / "public" / "data",
        report["authority"],
        report["examination"],
        year,
        replace_existing=replace_existing,
    )
    manifest = build_manifest(
        root / "public" / "data",
        root / "public" / "data" / "manifest.json",
    )

    status_path = root / "public" / "data" / "site-status.json"
    status_reset = False
    if status_path.is_file():
        current_status = json.loads(status_path.read_text(encoding="utf-8"))
        active = current_status.get("preparation") or {}
        if (
            current_status.get("mode") == "preparing"
            and active.get("authority") == report.get("authority")
            and active.get("exam") == report.get("examination")
            and active.get("year") == year
        ):
            status_path.write_text(
                json.dumps(
                    {"schema_version": 1, "mode": "search", "preparation": None},
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            status_reset = True

    _git(root, "config", "user.name", "github-actions[bot]")
    _git(root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    _git(root, "add", "--", "public/data")
    _git(root, "commit", "-m", f"Prepare {report['authority']} {report['examination']} {year} results")
    _git(root, "push", "origin", branch_name)

    validation = report.get("validation", {})
    duplicates = report.get("duplicates", {})
    exact_count = len(duplicates.get("exact_duplicates", []))
    fuzzy_count = len(duplicates.get("fuzzy_candidates", []))
    source_line = source_reference or "Not supplied"
    body = f"""## Examination result import review

**Authority:** {report['authority']}
**Examination:** {report['examination']}
**Year:** {year}
**Source reference:** {source_line}
**Source file:** {report.get('source_file', 'Not supplied')}  
**Source SHA-256:** `{report.get('source_file_sha256', 'Not recorded')}`
**Internal batch ID:** {report.get('d1_batch_id', 'D1 not configured')}

### Validation report
- Total records: {validation.get('total_records', 0)}
- Valid records: {validation.get('valid_records', 0)}
- Invalid records: {len(validation.get('invalid_records', []))}
- Exact duplicate candidates: {exact_count}
- Fuzzy duplicate candidates: {fuzzy_count}
- Generated dataset shards: {len(entries)}
- Manifest schema: {manifest.get('schema_version')}

### Owner review required
This Pull Request is the publication approval gate. Review the official source and all validation/duplicate findings before merging. No data in this branch is public until this Pull Request is merged and the production deployment completes.

Exact or fuzzy duplicate candidates have not been automatically deleted. Confirm whether they are legitimate separate people or extraction duplicates.

### Preparing Mode
- Matching active Preparing Mode reset in this PR: {status_reset}

### Replacement notice
{"This PR replaces an existing dataset for the same examination and year." if existing else "This is a new examination/year dataset."}

### Safety
- Generated only from the supplied processing report.
- Public output contains only the configured public columns.
- Source files and internal processing reports are not included in the public directory.
"""
    api_url = f"https://api.github.com/repos/{repository}/pulls"
    payload = json.dumps({
        "title": f"Publish {report['authority']} {report['examination']} {year} examination results",
        "head": branch_name,
        "base": "main",
        "body": body,
    }).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GitOpsError(f"Could not create GitHub Pull Request: {exc}") from exc

    return {
        "branch": branch_name,
        "pull_request_number": result.get("number"),
        "pull_request_url": result.get("html_url"),
        "commit_sha": _git(root, "rev-parse", "HEAD"),
        "dataset_shards": entries,
    }
