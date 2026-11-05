#!/usr/bin/env python3
"""Generate one safe, bounded NVIDIA patch proposal; never execute failed source."""
import json, os, re, subprocess, urllib.request
from pathlib import Path
def need(k):
    v=os.getenv(k)
    if not v: raise SystemExit("PREFLIGHT ERROR: missing "+k)
    return v
repo=need("GITHUB_REPOSITORY"); run_id=need("FAILED_RUN_ID"); sha=need("FAILED_SHA"); key=need("OPENROUTER_API_KEY")
strike=int(os.getenv("REPAIR_STRIKE","1"))
if strike not in (1,2,3): raise SystemExit("REPAIR_STRIKE must be 1..3")
model=os.getenv("OPENROUTER_MODEL","nvidia/nemotron-3-ultra-550b-a55b:free")
allowed=("python-engine/","watcher-bot/","website/","frontend/")
exts=(".py",".js",".ts",".tsx",".jsx")
out=Path("repair-output"); out.mkdir(exist_ok=True)
def run(a,cap=False,check=True):
    return subprocess.run(a,check=check,text=True,stdout=subprocess.PIPE if cap else None,stderr=subprocess.STDOUT if cap else None)
def validate(patch):
    if not patch or len(patch.encode())>1_000_000 or "GIT binary patch" in patch or "Binary files " in patch: raise ValueError("Empty, oversized, or binary patch")
    if re.search(r"^(?:old mode|new mode|deleted file mode|new file mode|rename from|rename to|copy from|copy to) ",patch,re.M): raise ValueError("Mode changes, renames, copies, and deletions forbidden")
    hs=re.findall(r"^diff --git a/(.*?) b/(.*?)$",patch,re.M); us=re.findall(r"^(---|\\+\\+\\+) (.*?)$",patch,re.M)
    if not hs or len(us)!=2*len(hs): raise ValueError("Malformed patch headers")
    seen=set()
    for i,(a,b) in enumerate(hs):
        for p in (a,b):
            q=Path(p)
            if not re.fullmatch(r"[A-Za-z0-9_./-]+",p) or q.is_absolute() or ".." in q.parts or "\\\\" in p or not p.startswith(allowed) or not p.endswith(exts) or p.startswith("python-engine/tests/"): raise ValueError("Unsafe path: "+p)
        if a!=b or b in seen: raise ValueError("Renames or duplicate paths forbidden")
        seen.add(b); ak,ap=us[2*i]; bk,bp=us[2*i+1]; ap=ap.split("\\t",1)[0]; bp=bp.split("\\t",1)[0]
        if ak!="---" or bk!="+++" or ap!="a/"+a or bp!="b/"+b: raise ValueError("Unified path mismatch")
logs=run(["gh","run","view",run_id,"--repo",repo,"--log-failed"],True,False).stdout[-30000:]
run(["git","fetch","--no-tags","origin",sha])
files=run(["git","ls-tree","-r","--name-only",sha],True).stdout.splitlines()
chosen=[p for p in files if p.startswith(allowed) and p.endswith(exts) and not p.startswith("python-engine/tests/")]
mentioned=[p for p in chosen if p in logs or Path(p).name in logs]
context=[]
for p in list(dict.fromkeys(mentioned+chosen))[:18]:
    r=run(["git","show",f"{sha}:{p}"],True,False)
    if r.returncode==0: context.append("\\nFILE "+p+"\\n"+r.stdout[:8000])
run(["git","archive","--format=tar.gz","-o",str(out/"source.tar.gz"),sha])
feedback=""
if strike>1:
    f=os.getenv("PREVIOUS_FEEDBACK_FILE")
    if not f or not Path(f).is_file(): raise SystemExit("PREFLIGHT ERROR: previous isolated test feedback missing")
    feedback=Path(f).read_text(errors="replace")[-20000:]
prompt=f"""Repair PH-EXAM-RESULTS. Attempt {strike} of 3. Return ONLY JSON keys patch and reason; patch is a unified git diff.
Modify only existing application source files under python-engine/, watcher-bot/, website/, frontend/. Do not alter tests, workflows, datasets, credentials, deployment config, or add/remove/rename files. Never weaken Greenlight, sequence/name integrity, official PRC source compliance, or no-publish rules. Smallest root-cause fix only.
Original failed logs:\n{logs}\nPrevious isolated verification feedback:\n{feedback}\nSource context:\n{''.join(context)}"""
req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps({"model":model,"temperature":0.1,"messages":[{"role":"user","content":prompt}],"response_format":{"type":"json_object"}}).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
try:
    with urllib.request.urlopen(req,timeout=120) as r: answer=json.loads(json.loads(r.read())["choices"][0]["message"]["content"])
except Exception as e: raise SystemExit("NVIDIA proposal failed: "+type(e).__name__+": "+str(e))
patch=answer.get("patch",""); validate(patch); (out/"patch.diff").write_text(patch); (out/"reason.txt").write_text(str(answer.get("reason",""))[:4000])
print("PROPOSAL_CREATED strike="+str(strike))
