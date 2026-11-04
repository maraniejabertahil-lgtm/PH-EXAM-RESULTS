#!/usr/bin/env python3
import json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

repo = os.environ["GITHUB_REPOSITORY"]
run_id = os.environ["FAILED_RUN_ID"]
failed_sha = os.environ["FAILED_SHA"]
api_key = os.environ["OPENROUTER_API_KEY"]
model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
allowed = ("python-engine/", "watcher-bot/", "website/", "frontend/")
forbidden = ("python-engine/tests/",)

def cmd(args, cwd=None, check=True, capture=False, env=None):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(
        list(map(str, args)), cwd=cwd, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None, env=env
    )

# This script is checked out from the trusted default branch, not the failed SHA.
logs = cmd(["gh", "run", "view", run_id, "--repo", repo, "--log-failed"],
           check=False, capture=True).stdout[-40000:]
cmd(["git", "fetch", "origin", failed_sha])
worktree = Path(tempfile.mkdtemp(prefix="ph-result-repair-")) / "source"
branch = "nvidia/repair-run-" + run_id
cmd(["git", "worktree", "add", "-b", branch, worktree, failed_sha])

tracked = cmd(["git", "ls-files"], cwd=worktree, capture=True).stdout.splitlines()
source_files = [
    p for p in tracked if p.startswith(allowed) and not p.startswith(forbidden)
    and p.endswith((".py", ".js", ".ts", ".tsx", ".jsx"))
]
mentioned = [p for p in source_files if p in logs or Path(p).name in logs]
files = list(dict.fromkeys(mentioned + source_files))[:18]
context = "\n\n".join(
    "FILE " + p + "\n" + (worktree / p).read_text(errors="replace")[:9000]
    for p in files
)
previous = []

# The test process receives no API key, GitHub token, or Actions credentials.
safe_env = {
    k: v for k, v in os.environ.items()
    if k in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR",
             "TEMP", "TMP", "CI", "PYTHONIOENCODING"}
}
safe_env["PYTHONPATH"] = "python-engine/retrieval"

for attempt in range(1, 4):
    prompt = f"""Fix the PH-EXAM-RESULTS CI failure. Attempt {attempt}/3.
Return ONLY JSON with keys patch and reason. patch must be a unified git diff.
Make a minimal root-cause fix. Never weaken Greenlight, sequence/name integrity,
official-source compliance, privacy, or no-publish rules. Only change application
source under python-engine/, watcher-bot/, website/, frontend/. Do not modify
tests, workflows, secrets, credentials, deployment configuration, or branch
protection. Do not invent paths or APIs.
LOGS:
{logs}
SOURCE:
{context}
PREVIOUS:
{previous}
"""
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": model, "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }).encode(),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.loads(response.read())["choices"][0]["message"]["content"]
    result = json.loads(answer)
    patch = result.get("patch", "")
    previous.append("Attempt " + str(attempt) + ": " + result.get("reason", ""))
    pairs = re.findall(r"^diff --git a/(.*?) b/(.*?)$", patch, re.M)
    paths = [p for pair in pairs for p in pair]
    if not paths or any(
        Path(p).is_absolute() or ".." in Path(p).parts
        or not p.startswith(allowed) or p.startswith(forbidden)
        for p in paths
    ):
        continue
    patch_file = Path(tempfile.gettempdir()) / ("repair-" + run_id + ".patch")
    patch_file.write_text(patch)
    if cmd(["git", "apply", "--check", patch_file], cwd=worktree,
           check=False).returncode:
        continue
    cmd(["git", "apply", patch_file], cwd=worktree)
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "python-engine/tests", "-q"],
        cwd=worktree, env=safe_env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    print(test.stdout[-25000:], flush=True)
    if test.returncode == 0:
        break
    context += "\nCURRENT DIFF:\n" + cmd(
        ["git", "diff"], cwd=worktree, capture=True
    ).stdout[-20000:]
else:
    raise SystemExit("Three repair attempts failed; no PR opened.")

status = cmd(["git", "status", "--porcelain", "-uall"],
             cwd=worktree, capture=True).stdout.splitlines()
if not status:
    raise SystemExit("No source changes; no PR opened.")
for entry in status:
    path = entry[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    if (Path(path).is_absolute() or ".." in Path(path).parts
        or not path.startswith(allowed) or path.startswith(forbidden)):
        raise SystemExit("Out-of-scope path; refusing to commit: " + path)

cmd(["git", "config", "user.name", "github-actions[bot]"], cwd=worktree)
cmd(["git", "config", "user.email",
     "41898282+github-actions[bot]@users.noreply.github.com"], cwd=worktree)
cmd(["git", "add", "-A"], cwd=worktree)
staged = cmd(["git", "diff", "--cached", "--name-only"],
             cwd=worktree, capture=True).stdout.splitlines()
if not staged or any(not p.startswith(allowed) or p.startswith(forbidden)
                     for p in staged):
    raise SystemExit("Staged paths failed scope validation.")
cmd(["git", "commit", "-m", "fix: NVIDIA autonomous repair for run " + run_id],
    cwd=worktree)

# GitHub credentials are used only after tests have finished.
cmd(["gh", "auth", "setup-git"])
cmd(["git", "push", "-u", "origin", branch], cwd=worktree)
body = (
    "Automated isolated repair for failed run https://github.com/" + repo
    + "/actions/runs/" + run_id + "\n\nSource SHA: " + failed_sha
    + "\nModel: " + model + "\nFull Python Engine tests: PASS"
    + "\n\nTests ran without GitHub/OpenRouter credentials. Human review required."
    + "\nNo merge, publication, or deployment is performed.\n\n"
    + "\n".join(previous)
)
cmd(["gh", "pr", "create", "--repo", repo, "--base", "Winner-Candidate",
     "--head", branch, "--title",
     "NVIDIA autonomous repair for run " + run_id, "--body", body])
print("REPAIR_PR_CREATED=1", flush=True)
