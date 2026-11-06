"""Read-only merge-compatibility audit against every remote repository branch."""
from __future__ import annotations

import os
import subprocess
import sys


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], text=True, capture_output=True, check=False)


def main() -> int:
    feature = os.getenv("FEATURE_BRANCH", "feature/private-activity-monitor-rebased-20261107")
    feature_ref = "origin/" + feature
    refs_result = git("for-each-ref", "refs/remotes/origin", "--format=%(refname:short)")
    if refs_result.returncode:
        print(refs_result.stderr)
        return 2
    refs = [ref for ref in refs_result.stdout.splitlines()
            if ref not in {"origin/HEAD", "origin/main", feature_ref}]
    if git("rev-parse", "--verify", feature_ref).returncode != 0:
        feature_ref = "origin/main"
    included = []
    clean = []
    conflicts = []
    unrelated = []
    for ref in refs:
        if git("merge-base", "--is-ancestor", ref, feature_ref).returncode == 0:
            included.append(ref)
            continue
        if git("merge-base", "--is-ancestor", feature_ref, ref).returncode == 0:
            included.append(ref)
            continue
        base = git("merge-base", feature_ref, ref)
        if base.returncode or not base.stdout.strip():
            unrelated.append(ref)
            continue
        result = git("merge-tree", "--write-tree", feature_ref, ref)
        if result.returncode == 0:
            clean.append(ref)
        else:
            paths = []
            for line in (result.stdout + "\n" + result.stderr).splitlines():
                if "CONFLICT" in line and " in " in line:
                    paths.append(line.rsplit(" in ", 1)[-1].strip())
            conflicts.append((ref, sorted(set(paths))))

    print("ALL-BRANCH COMPATIBILITY AUDIT")
    branch_count = len(refs) + len({"origin/main", feature_ref})
    print("Remote branches examined: " + str(branch_count))
    print("Already includes feature / feature includes branch: " + str(len(included)))
    print("Clean merge compatibility: " + str(len(clean)))
    print("Merge conflicts: " + str(len(conflicts)))
    print("No common merge base: " + str(len(unrelated)))
    for ref, paths in conflicts:
        print("CONFLICT " + ref + (": " + ", ".join(paths) if paths else " (inspect merge-tree output)"))
    for ref in unrelated:
        print("NO_COMMON_BASE " + ref)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## All-branch compatibility audit\n\n")
            summary.write(f"- Remote branches examined: {branch_count}\n")
            summary.write(f"- Already included/contains feature: {len(included)}\n")
            summary.write(f"- Clean merge compatibility: {len(clean)}\n")
            summary.write(f"- Merge conflicts: {len(conflicts)}\n")
            summary.write(f"- No common merge base: {len(unrelated)}\n")
            for ref, paths in conflicts:
                summary.write("- **Conflict:** " + ref + (": " + ", ".join(paths) if paths else "") + "\n")
            for ref in unrelated:
                summary.write("- **No common base:** " + ref + "\n")

    if os.getenv("BRANCH_COMPATIBILITY_STRICT") == "1" and (conflicts or unrelated):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
