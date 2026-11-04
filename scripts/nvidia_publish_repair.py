#!/usr/bin/env python3
"""Publish a previously isolated-tested patch; never execute candidate source."""
import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO = os.environ["GITHUB_REPOSITORY"]
RUN_ID = os.environ["FAILED_RUN_ID"]
FAILED_SHA = os.environ["FAILED_SHA"]
PATCH = Path("repair-input/patch.diff").read_text()
ALLOWED = ("python-engine/", "watcher-bot/", "website/", "frontend/")
EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx")
BRANCH = "nvidia/repair-run-" + RUN_ID

def run(args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def validate():
    if not PATCH or len(PATCH.encode()) > 1_000_000:
        raise SystemExit("Empty or oversized patch.")
    if "GIT binary patch" in PATCH or "Binary files " in PATCH:
        raise SystemExit("Binary patch rejected.")
    if re.search(r"^(?:old mode|new mode|deleted file mode|new file mode|rename from|rename to|copy from|copy to) ", PATCH, re.M):
        raise SystemExit("Mode changes, renames, and copies are forbidden.")
    headers = re.findall(r"^diff --git a/(.*?) b/(.*?)$", PATCH, re.M)
    unified = re.findall(r"^(---|\\+\\+\\+) (.*?)$", PATCH, re.M)
    if not headers or len(unified) != 2 * len(headers):
        raise SystemExit("Patch must contain exactly two unified path headers per file.")
    seen = set()
    for index, (old, new) in enumerate(headers):
        for path in (old, new):
            p = Path(path)
            if (not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or p.is_absolute()
                or "\\\\" in path or ".." in p.parts or not path.startswith(ALLOWED)
                or not path.endswith(EXTENSIONS)):
                raise SystemExit("Unsafe or out-of-scope path: " + path)
        if old != new or new in seen:
            raise SystemExit("Renames and duplicate file headers are forbidden.")
        seen.add(new)
        old_kind, old_path = unified[index * 2]
        new_kind, new_path = unified[index * 2 + 1]
        old_path = old_path.split("\\t", 1)[0]
        new_path = new_path.split("\\t", 1)[0]
        if old_kind != "---" or new_kind != "+++":
            raise SystemExit("Malformed unified diff headers.")
        if old_path not in ("/dev/null", "a/" + old) or new_path != "b/" + new:
            raise SystemExit("Unified paths do not match validated diff paths.")

validate()
patch_path = Path(tempfile.gettempdir()) / ("nvidia-" + RUN_ID + ".patch")
patch_path.write_text(PATCH)
run(["git", "fetch", "--no-tags", "origin", FAILED_SHA])
worktree = Path(tempfile.mkdtemp(prefix="ph-repair-publish-")) / "source"
run(["git", "worktree", "add", "-b", BRANCH, str(worktree), FAILED_SHA])
run(["git", "apply", "--check", str(patch_path)], cwd=worktree)
run(["git", "apply", str(patch_path)], cwd=worktree)
status = run(["git", "status", "--porcelain", "-uall"], cwd=worktree, capture=True).stdout.splitlines()
if not status:
    raise SystemExit("No changes; no repair PR created.")
for entry in status:
    path = entry[3:].strip().split(" -> ")[-1]
    if not path.startswith(ALLOWED) or path.startswith("python-engine/tests/"):
        raise SystemExit("Changed path outside approved application scope: " + path)
run(["git", "config", "user.name", "github-actions[bot]"], cwd=worktree)
run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=worktree)
run(["git", "add", "-A"], cwd=worktree)
staged = run(["git", "diff", "--cached", "--name-only"], cwd=worktree, capture=True).stdout.splitlines()
if not staged or any(not p.startswith(ALLOWED) or p.startswith("python-engine/tests/") for p in staged):
    raise SystemExit("Staged paths failed final scope validation.")
run(["git", "commit", "-m", "fix: NVIDIA isolated-tested repair for run " + RUN_ID], cwd=worktree)
run(["gh", "auth", "setup-git"])
run(["git", "push", "-u", "origin", BRANCH], cwd=worktree)
body = ("Automated isolated repair for failed run https://github.com/" + REPO +
    "/actions/runs/" + RUN_ID + "\\n\\nSource SHA: " + FAILED_SHA +
    "\\nModel: " + os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free") +
    "\\n\\nThe candidate patch passed the isolated Python Engine test job with no repository permissions or API secrets. " +
    "This publisher job did not execute candidate source. Human review required. " +
    "No merge, publication, or deployment is performed.")
run(["gh", "pr", "create", "--repo", REPO, "--base", "Winner-Candidate",
     "--head", BRANCH, "--title", "NVIDIA isolated-tested repair for run " + RUN_ID,
     "--body", body])
print("REPAIR_PR_CREATED=1")
