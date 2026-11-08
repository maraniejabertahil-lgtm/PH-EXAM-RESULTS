"""Read-only merge-compatibility audit against every remote repository branch."""
from __future__ import annotations

import json
import os
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], text=True, capture_output=True, check=False)


def merge_conflicts(left: str, right: str):
    result = git("merge-tree", "--write-tree", left, right)
    if result.returncode == 0:
        return False, []
    paths = []
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "CONFLICT" in line and " in " in line:
            paths.append(line.rsplit(" in ", 1)[-1].strip())
    return True, sorted(set(paths))


def merged_pull_request_branch(ref: str) -> bool:
    """Return True only when GitHub confirms this exact head branch was merged."""
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY", "maraniejabertahil-lgtm/PH-EXAM-RESULTS")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for merged-PR branch classification.")
    owner = repository.split("/", 1)[0]
    branch = ref.removeprefix("origin/")
    url = (
        "https://api.github.com/repos/"
        + quote(repository, safe="/")
        + "/pulls?state=closed&per_page=100&head="
        + quote(owner + ":" + branch, safe="")
    )
    request = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("Could not verify merged-PR status for " + ref) from exc
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected GitHub PR response while checking " + ref)
    return any(isinstance(pr, dict) and pr.get("merged_at") for pr in payload)


def main() -> int:
    feature = os.getenv("FEATURE_BRANCH", "feature/private-activity-monitor-rebased-20261107")
    feature_ref = "origin/" + feature
    refs_result = git("for-each-ref", "refs/remotes/origin", "--format=%(refname:short)")
    if refs_result.returncode:
        print(refs_result.stderr)
        return 2
    if git("rev-parse", "--verify", feature_ref).returncode != 0:
        feature_ref = "origin/main"
    refs = [ref for ref in refs_result.stdout.splitlines()
            if ref not in {"origin/HEAD", "origin/main", feature_ref}]

    included = []
    clean = []
    preexisting = []
    introduced = []
    unrelated = []
    squash_merged = []
    for ref in refs:
        # A squash merge does not preserve source-branch ancestry. Exclude only
        # branches whose exact head PR GitHub confirms was merged; API errors fail closed.
        try:
            if merged_pull_request_branch(ref):
                squash_merged.append(ref)
                continue
        except RuntimeError as exc:
            print(str(exc))
            return 2
        # Squash-merged branches are not necessarily ancestors of main. If their
        # complete tree is identical to main or the feature tree, their content
        # is already represented and should not be reported as a merge conflict.
        if git("diff", "--quiet", "origin/main", ref).returncode == 0:
            included.append(ref)
            continue
        if git("diff", "--quiet", feature_ref, ref).returncode == 0:
            included.append(ref)
            continue
        if git("merge-base", "--is-ancestor", ref, feature_ref).returncode == 0:
            included.append(ref)
            continue
        if git("merge-base", "--is-ancestor", feature_ref, ref).returncode == 0:
            included.append(ref)
            continue
        base = git("merge-base", "origin/main", ref)
        if base.returncode or not base.stdout.strip():
            unrelated.append(ref)
            continue
        base_conflict, base_paths = merge_conflicts("origin/main", ref)
        feature_conflict, feature_paths = merge_conflicts(feature_ref, ref)
        if not feature_conflict:
            clean.append(ref)
        elif base_conflict:
            preexisting.append((ref, sorted(set(base_paths + feature_paths))))
        else:
            introduced.append((ref, feature_paths))

    branch_count = len(refs) + len({"origin/main", feature_ref})
    print("ALL-BRANCH COMPATIBILITY AUDIT")
    print("Remote branches examined: " + str(branch_count))
    print("Confirmed merged-PR branches skipped: " + str(len(squash_merged)))
    print("Already includes feature / feature includes branch: " + str(len(included)))
    print("Clean merge compatibility: " + str(len(clean)))
    print("Pre-existing conflicts against main: " + str(len(preexisting)))
    print("Conflicts introduced by this feature: " + str(len(introduced)))
    print("No common merge base: " + str(len(unrelated)))
    for ref, paths in preexisting:
        print("PRE_EXISTING " + ref + (": " + ", ".join(paths) if paths else " (inspect merge-tree output)"))
    for ref, paths in introduced:
        print("INTRODUCED " + ref + (": " + ", ".join(paths) if paths else " (inspect merge-tree output)"))
    for ref in unrelated:
        print("NO_COMMON_BASE " + ref)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## All-branch compatibility audit\n\n")
            summary.write(f"- Remote branches examined: {branch_count}\n")
            summary.write(f"- Confirmed merged-PR branches skipped: {len(squash_merged)}\n")
            summary.write(f"- Already included/contains feature: {len(included)}\n")
            summary.write(f"- Clean merge compatibility: {len(clean)}\n")
            summary.write(f"- Pre-existing conflicts against main: {len(preexisting)}\n")
            summary.write(f"- Conflicts introduced by this feature: {len(introduced)}\n")
            summary.write(f"- No common merge base: {len(unrelated)}\n")
            for ref, paths in preexisting:
                summary.write("- **Pre-existing conflict:** " + ref + (": " + ", ".join(paths) if paths else "") + "\n")
            for ref, paths in introduced:
                summary.write("- **Introduced conflict:** " + ref + (": " + ", ".join(paths) if paths else "") + "\n")
            for ref in unrelated:
                summary.write("- **No common base:** " + ref + "\n")

    if os.getenv("BRANCH_COMPATIBILITY_STRICT") == "1" and introduced:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
