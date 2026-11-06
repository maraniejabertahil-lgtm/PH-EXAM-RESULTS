"""Read-only merge-compatibility audit against every remote repository branch."""
from __future__ import annotations

import os
import subprocess


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
