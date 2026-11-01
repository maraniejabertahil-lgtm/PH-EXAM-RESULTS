import json
import re
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


class GitOpsError(Exception):
    """Raised when a data publication Pull Request cannot be prepared."""


def _safe_inline_code(value, limit: int = 120) -> str:
    """Render untrusted source text safely inside a Markdown inline-code span."""
    cleaned = str(value).replace("\r", " ").replace("\n", " ").replace("`", "'")
    return "`" + cleaned[:limit] + "`"


def _find_open_publication_pr(repository: str, token: str, branch_prefix: str) -> dict | None:
    """Prevent multiple pending imports for the same authority/exam/year."""
    api_url = f"https://api.github.com/repos/{repository}/pulls?state=open&base=main&per_page=100"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            pull_requests = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GitOpsError(f"Could not check for an existing publication Pull Request: {exc}") from exc
    if not isinstance(pull_requests, list):
        raise GitOpsError("GitHub returned an invalid open Pull Request list.")
    for pull_request in pull_requests:
        head = pull_request.get("head") or {}
        if str(head.get("ref", "")).startswith(branch_prefix):
            return pull_request
    return None


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
    # Monitoring can prepare more than one import in a single Actions run.
    # Always start each publication from a clean copy of approved main so a
    # later PR cannot accidentally include an earlier source's unmerged files.
    _git(root, "fetch", "origin", "main")
    _git(root, "switch", "main")
    _git(root, "reset", "--hard", "origin/main")
    if report.get("authority") not in {"PRC", "CSC"}:
        raise GitOpsError("Authority must be PRC or CSC.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", str(report.get("examination", ""))):
        raise GitOpsError("Examination identifier contains unsupported characters.")
    authority = report["authority"].lower()
    exam = report["examination"].lower()
    year = int(report["year"])
    branch_prefix = f"data-import/{authority}-{exam}-{year}-"
    pending_pr = _find_open_publication_pr(repository, token, branch_prefix)
    if pending_pr:
        raise GitOpsError(
            "An owner-review publication Pull Request is already open for "
            f"{report['authority']} {report['examination']} {year}: "
            f"{pending_pr.get('html_url', 'URL unavailable')}. "
            "Review or close it before creating another import for this examination/year."
        )
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

    batch_metadata_path = None
    d1_batch_id = report.get("d1_batch_id")
    if d1_batch_id:
        batch_metadata_path = root / ".internal" / "import-batches" / f"{d1_batch_id}.json"
        batch_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        batch_metadata_path.write_text(
            json.dumps({
                "batch_id": d1_batch_id,
                "authority": report.get("authority"),
                "exam": report.get("examination"),
                "year": year,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    _git(root, "config", "user.name", "github-actions[bot]")
    _git(root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    if batch_metadata_path is not None:
        _git(root, "add", "--", "public/data", ".internal/import-batches")
    else:
        _git(root, "add", "--", "public/data")
    _git(root, "commit", "-m", f"Prepare {report['authority']} {report['examination']} {year} results")
    _git(root, "push", "origin", branch_name)

    validation = report.get("validation", {})
    duplicates = report.get("duplicates", {})
    exact_count = len(duplicates.get("exact_duplicates", []))
    fuzzy_candidates = duplicates.get("fuzzy_candidates", [])
    fuzzy_count = len(fuzzy_candidates)
    records = report.get("records", [])
    fuzzy_review_lines = []
    for candidate in fuzzy_candidates[:20]:
        first_index = candidate.get("first_index")
        other_index = candidate.get("candidate_index")
        if (
            isinstance(first_index, int) and isinstance(other_index, int)
            and 0 <= first_index < len(records)
            and 0 <= other_index < len(records)
        ):
            first_name = _safe_inline_code(records[first_index].get("name", ""))
            other_name = _safe_inline_code(records[other_index].get("name", ""))
            similarity = candidate.get("similarity", "not supplied")
            fuzzy_review_lines.append(
                f"- {first_name} ↔ {other_name} (similarity: {similarity})"
            )
    fuzzy_review_section = (
        "\n".join(fuzzy_review_lines)
        if fuzzy_review_lines
        else "No fuzzy duplicate candidates were identified."
    )
    if fuzzy_count > len(fuzzy_review_lines):
        fuzzy_review_section += (
            f"\n- Showing first {len(fuzzy_review_lines)} of {fuzzy_count} candidates."
        )
    source_line = _safe_inline_code(source_reference or "Not supplied", limit=500)
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

### Fuzzy duplicate review
{fuzzy_review_section}

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

    publication_commit_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "main")

    return {
        "branch": branch_name,
        "pull_request_number": result.get("number"),
        "pull_request_url": result.get("html_url"),
        "commit_sha": publication_commit_sha,
        "dataset_shards": entries,
    }
