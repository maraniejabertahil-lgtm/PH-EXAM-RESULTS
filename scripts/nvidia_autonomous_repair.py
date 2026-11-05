#!/usr/bin/env python3
import json,os,re,subprocess,sys,urllib.request
from pathlib import Path
repo=os.environ["GITHUB_REPOSITORY"]; runid=os.environ["FAILED_RUN_ID"]; sha=os.environ["FAILED_SHA"]; key=os.environ["OPENROUTER_API_KEY"]
model=os.getenv("OPENROUTER_MODEL","nvidia/nemotron-3-ultra-550b-a55b:free")
allowed=("python-engine/","watcher-bot/","website/","frontend/")
def cmd(a,check=True,capture=False):
 print("+"," ".join(a),flush=True)
 return subprocess.run(a,check=check,text=True,stdout=subprocess.PIPE if capture else None,stderr=subprocess.STDOUT if capture else None)
logs=cmd(["gh","run","view",runid,"--repo",repo,"--log-failed"],False,True).stdout[-40000:]
tracked=cmd(["git","ls-files"],capture=True).stdout.splitlines()
files=[p for p in tracked if p.startswith(allowed) and p.endswith((".py",".js",".ts",".tsx",".jsx"))][:12]
context="\n\n".join("FILE "+p+"\n"+Path(p).read_text(errors="replace")[:9000] for p in files)
prior=[]
for attempt in range(1,4):
 prompt=f"""Fix the PH-EXAM-RESULTS CI failure. Attempt {attempt}/3. Return ONLY JSON with keys patch and reason. patch must be a standard unified git diff. Read logs and source; make a minimal root-cause fix. Never weaken Greenlight, exact sequence/name integrity, official-source compliance, privacy or no-publish rules. Only change files under python-engine/, watcher-bot/, website/, frontend/. Never edit workflows, secrets, credentials, deployment config or branch protection. Do not invent paths/APIs.
LOGS:\n{logs}\nSOURCE:\n{context}\nPREVIOUS ATTEMPTS:\n{prior}"""
 req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps({"model":model,"temperature":0.1,"messages":[{"role":"user","content":prompt}],"response_format":{"type":"json_object"}}).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=120) as r: obj=json.loads(json.loads(r.read())["choices"][0]["message"]["content"])
 patch=obj.get("patch",""); prior.append("Attempt "+str(attempt)+": "+obj.get("reason",""))
 paths=re.findall(r"^diff --git a/(.*?) b/(.*?)$",patch,re.M)
 if not paths or any(not p.startswith(allowed) or ".." in Path(p).parts for pair in paths for p in pair): continue
 Path("/tmp/repair.patch").write_text(patch)
 if cmd(["git","apply","--check","/tmp/repair.patch"],False).returncode: continue
 cmd(["git","apply","/tmp/repair.patch"])
 env=os.environ.copy(); env["PYTHONPATH"]="python-engine/retrieval"
 test=subprocess.run([sys.executable,"-m","pytest","python-engine/tests","-q"],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 print(test.stdout[-25000:],flush=True)
 if test.returncode==0: break
 context+="\nCURRENT DIFF:\n"+cmd(["git","diff"],capture=True).stdout[-20000:]
else: raise SystemExit("Three autonomous repair attempts failed; no PR opened.")
if not cmd(["git","status","--porcelain"],capture=True).stdout.strip(): raise SystemExit("No source changes.")
branch="nvidia/repair-run-"+runid
cmd(["git","config","user.name","github-actions[bot]"]); cmd(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"])
cmd(["git","checkout","-b",branch]); cmd(["git","add","--",*allowed]); cmd(["git","commit","-m","fix: NVIDIA autonomous repair for run "+runid]); cmd(["git","push","origin",branch])
body="Automated isolated repair for failed run https://github.com/"+repo+"/actions/runs/"+runid+"\n\nSource SHA: "+sha+"\nModel: "+model+"\nFull Python test suite: PASS\n\nNo merge, publication, or deployment is performed by this workflow.\n\n"+ "\n".join(prior)
cmd(["gh","pr","create","--repo",repo,"--base","Winner-Candidate","--head",branch,"--title","NVIDIA autonomous repair for run "+runid,"--body",body])
print("REPAIR_PR_CREATED=1")
