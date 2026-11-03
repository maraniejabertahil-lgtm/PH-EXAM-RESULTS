"""GitHub GitOps publishing with a fail-closed Greenlight gate.

This module creates a data-only pull request and merges it only after the
Greenlight report is valid AND GitHub reports every check run and commit
status as successful. It never stores credentials or edits the default branch
directly.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import PurePosixPath
from typing import Mapping


API = "https://api.github.com"
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")


class GitOpsError(RuntimeError):
    """Raised when a safe GitOps operation cannot be completed."""


def validate_greenlight(report: dict) -> None:
    """Reject anything other than a complete, explicit 100-point pass."""
    if not isinstance(report, dict):
        raise GitOpsError("A Greenlight report is required.")
    checks = report.get("checks")
    if (
        report.get("status") != "GREENLIGHT"
        or report.get("greenlight_score") != 100
        or report.get("publication_allowed") is not True
        or not isinstance(checks, dict)
        or not checks
        or any(value is not True for value in checks.values())
        or report.get("record_count") != report.get("announced_count")
        or not isinstance(report.get("records_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", report["records_sha256"])
        or report.get("provenance") not in {"official_direct", "third_party_fallback"}
    ):
        raise GitOpsError("Auto-publication denied: Greenlight is not a complete 100-point pass.")
    if report["provenance"] == "third_party_fallback":
        if not report.get("source_a_id") or not report.get("source_b_id"):
            raise GitOpsError("Fallback provenance requires both independent source IDs.")
        if report["source_a_id"] == report["source_b_id"]:
            raise GitOpsError("Fallback source IDs must be independent.")


def validate_artifacts(artifacts: Mapping[str, bytes]) -> dict[str, bytes]:
    """Allow only non-empty files below public/data; reject traversal and secrets."""
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise GitOpsError("At least one dataset artifact is required.")
    safe: dict[str, bytes] = {}
    for name, content in artifacts.items():
        path = PurePosixPath(name) if isinstance(name, str) else None
        if (
            path is None or path.is_absolute() or ".." in path.parts
            or not name.startswith("public/data/")
            or name.endswith("/")
            or any(part.startswith(".") for part in path.parts)
        ):
            raise GitOpsError(f"Artifact path is not allowed: {name!r}")
        if not isinstance(content, bytes) or not content:
            raise GitOpsError(f"Artifact {name!r} must contain non-empty bytes.")
        safe[name] = content
    return safe


class GitHubGitOps:
    """Small GitHub REST client; token is read only from the environment."""

    def __init__(self, repository: str, token: str | None = None, timeout: int = 20):
        if not isinstance(repository, str) or not _REPO.fullmatch(repository):
            raise GitOpsError("repository must use owner/name format.")
        self.repository = repository
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise GitOpsError("GITHUB_TOKEN is missing; provide it as a GitHub Actions secret.")
        self.timeout = timeout
        self.root = f"{API}/repos/{repository}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.root + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "PH-EXAM-RESULTS-GitOps",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise GitOpsError(f"GitHub API {method} {path} failed ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GitOpsError(f"GitHub API request failed: {exc}") from exc

    def open_dataset_pr(
        self,
        *,
        artifacts: Mapping[str, bytes],
        greenlight_report: dict,
        title: str,
        base_branch: str = "main",
        branch_name: str | None = None,
    ) -> dict:
        """Create a branch and PR. The PR is not merged until checks pass."""
        validate_greenlight(greenlight_report)
        safe_artifacts = validate_artifacts(artifacts)
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise GitOpsError("A valid pull-request title is required.")
        if not _BRANCH.fullmatch(base_branch):
            raise GitOpsError("Invalid base branch.")
        branch_name = branch_name or f"data/greenlight-{greenlight_report['records_sha256'][:12]}"
        if not _BRANCH.fullmatch(branch_name) or branch_name == base_branch:
            raise GitOpsError("Invalid publication branch name.")

        base_ref = self._request("GET", f"/git/ref/heads/{base_branch}")
        base_sha = base_ref["object"]["sha"]
        base_commit = self._request("GET", f"/git/commits/{base_sha}")
        base_tree = base_commit["tree"]["sha"]

        self._request("POST", "/git/refs", {
            "ref": f"refs/heads/{branch_name}", "sha": base_sha,
        })

        tree_entries = []
        for path, content in sorted(safe_artifacts.items()):
            blob = self._request("POST", "/git/blobs", {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            })
            tree_entries.append({
                "path": path, "mode": "100644", "type": "blob", "sha": blob["sha"],
            })
        tree = self._request("POST", "/git/trees", {
            "base_tree": base_tree, "tree": tree_entries,
        })
        commit = self._request("POST", "/git/commits", {
            "message": f"data: publish Greenlight-verified dataset {greenlight_report['records_sha256'][:12]}",
            "tree": tree["sha"], "parents": [base_sha],
        })
        self._request("PATCH", f"/git/refs/heads/{branch_name}", {
            "sha": commit["sha"], "force": False,
        })

        body = (
            "## Automated dataset publication\n\n"
            f"- Greenlight score: **{greenlight_report['greenlight_score']} / 100**\n"
            f"- Provenance: `{greenlight_report['provenance']}`\n"
            f"- Records: {greenlight_report['record_count']} / {greenlight_report['announced_count']} announced\n"
            f"- Records SHA-256: `{greenlight_report['records_sha256']}`\n"
            "- Artifacts are restricted to `public/data/`.\n"
            "- Auto-merge is deferred until all GitHub checks and commit statuses succeed.\n"
        )
        pr = self._request("POST", "/pulls", {
            "title": title.strip(), "head": branch_name, "base": base_branch,
            "body": body, "draft": False,
        })
        return {
            "status": "awaiting_checks",
            "pull_request_number": pr["number"],
            "pull_request_url": pr["html_url"],
            "head_sha": commit["sha"],
            "branch": branch_name,
            "greenlight_score": 100,
            "auto_merge_ready": False,
        }

    def merge_when_checks_pass(self, *, pull_request_number: int, greenlight_report: dict) -> dict:
        """Merge only when the same validated report and all GitHub checks pass."""
        validate_greenlight(greenlight_report)
        if isinstance(pull_request_number, bool) or not isinstance(pull_request_number, int) or pull_request_number < 1:
            raise GitOpsError("A valid pull request number is required.")
        pr = self._request("GET", f"/pulls/{pull_request_number}")
        if pr.get("state") != "open" or pr.get("merged") is True:
            raise GitOpsError("Pull request must be open and not already merged.")
        head_sha = pr.get("head", {}).get("sha")
        if not head_sha:
            raise GitOpsError("Pull request head SHA is missing.")

        checks = self._request("GET", f"/commits/{head_sha}/check-runs")
        runs = checks.get("check_runs", [])
        if not runs or any(
            run.get("status") != "completed" or run.get("conclusion") != "success"
            for run in runs
        ):
            return {"status": "awaiting_checks", "merged": False, "check_runs": len(runs)}

        statuses = self._request("GET", f"/commits/{head_sha}/status")
        if statuses.get("state") != "success":
            return {"status": "awaiting_checks", "merged": False, "commit_status": statuses.get("state")}

        result = self._request("PUT", f"/pulls/{pull_request_number}/merge", {
            "merge_method": "squash",
            "sha": head_sha,
        })
        if result.get("merged") is not True:
            raise GitOpsError("GitHub did not confirm the pull request merge.")
        return {"status": "merged", "merged": True, "merge_sha": result.get("sha")}


def open_dataset_pr(**kwargs) -> dict:
    """Convenience entry point using GITHUB_REPOSITORY and GITHUB_TOKEN."""
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        raise GitOpsError("GITHUB_REPOSITORY is missing.")
    return GitHubGitOps(repository).open_dataset_pr(**kwargs)
