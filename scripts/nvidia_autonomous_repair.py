#!/usr/bin/env python3
"""Create a repair proposal without executing source from the failed revision."""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

REPO = os.environ["GITHUB_REPOSITORY"]
RUN_ID = os.environ["FAILED_RUN_ID"]
FAILED_SHA = os.environ["FAILED_SHA"]
API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
ALLOWED = ("python-engine/", "watcher-bot/", "website/", "frontend/")
EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx")
OUT = Path("repair-output")
OUT.mkdir(exist_ok=True)

def run(args, capture=False, check=True):
    return subprocess.run(args, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def validate_patch(patch):
    if not patch or len(patch.encode()) > 1_000_000:
        raise ValueError("Patch is empty or exceeds 1 MB.")
    if "GIT binary patch" in patch or "Binary files " in patch:
        raise ValueError("Binary patches are not allowed.")
    if re.search(r"^(?:old mode|new mode|deleted file mode|new file mode|rename from|rename to|copy from|copy to) ", patch, re.M):
        raise ValueError("Mode changes, renames, copies, and symlink changes are not allowed.")
    headers = re.findall(r"^diff --git a/(.*?) b/(.*?)$", patch, re.M)
    unified = re.findall(r"^(---|\+\+\+) (.*?)$", patch, re.M)
    if not headers or len(unified) != 2 * len(headers):
        raise ValueError("Patch must have exactly two unified path headers per file.")
    seen = set()
    for index, (old, new) in enumerate(headers):
        for path in (old, new):
            p = Path(path)
            if (not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or p.is_absolute()
                or ".." in p.parts or not path.startswith(ALLOWED)
                or not path.endswith(EXTENSIONS)):
                raise ValueError("Out-of-scope or unsafe path: " + path)
        if old != new or new in seen:
            raise ValueError("Renames and duplicate file headers are not allowed.")
        seen.add(new)
        old_kind, old_path = unified[index * 2]
        new_kind, new_path = unified[index * 2 + 1]
        old_path = old_path.split("\t", 1)[0]
        new_path = new_path.split("\t", 1)[0]
        if old_kind != "---" or new_kind != "+++":
            raise ValueError("Malformed unified diff headers.")
        if old_path not in ("/dev/null", "a/" + old) or new_path != "b/" + new:
            raise ValueError("Unified paths do not match the validated diff paths.")
failed_logs = run(["gh", "run", "view", RUN_ID, "--repo", REPO, "--log-failed"],
                 capture=True, check=False).stdout[-30000:]
run(["git", "fetch", "--no-tags", "origin", FAILED_SHA])
files = run(["git", "ls-tree", "-r", "--name-only", FAILED_SHA], capture=True).stdout.splitlines()
selected = [p for p in files if p.startswith(ALLOWED) and p.endswith(EXTENSIONS)]
mentioned = [p for p in selected if p in failed_logs or Path(p).name in failed_logs]
selected = list(dict.fromkeys(mentioned + selected))[:18]
context = []
for path in selected:
    result = run(["git", "show", f"{FAILED_SHA}:{path}"], capture=True, check=False)
    if result.returncode == 0:
        context.append("FILE " + path + "\n" + result.stdout[:8000])

run(["git", "archive", "--format=tar.gz", "-o", str(OUT / "source.tar.gz"), FAILED_SHA])
prompt = f"""Diagnose this PH-EXAM-RESULTS failure and propose the smallest root-cause code fix.
Return ONLY JSON with keys patch and reason. patch must be a unified git diff.
Never weaken Greenlight, sequence/name integrity, official-source compliance,
privacy, or no-publish rules. Only change existing application source files under
python-engine/, watcher-bot/, website/, frontend/. Do not modify tests, workflows,
secrets, credentials, deployment configuration, or branch protection.
Do not invent paths or APIs.
FAILED LOGS:
{failed_logs}
SOURCE CONTEXT:
{''.join(context)}
"""
request = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps({"model": MODEL, "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}}).encode(),
    headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=120) as response:
    content = json.loads(response.read())["choices"][0]["message"]["content"]
answer = json.loads(content)
patch = answer.get("patch", "")
validate_patch(patch)
(OUT / "patch.diff").write_text(patch)
print("PROPOSAL_CREATED=1")
print("MODEL_REASON=" + str(answer.get("reason", ""))[:1000])
