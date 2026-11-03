#!/usr/bin/env python3
"""Private fallback: compare publicly published PRC NLE transcription mirrors."""
import hashlib, json, pathlib, re, sys, time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EXPECTED = 28652
OUT = pathlib.Path("private-prc-extraction")
UA = "PH-EXAM-RESULTS-PRC-Research/1.0"
SITES = {
 "boardexams": [
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/a-c-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/d-f-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/g-i-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/j-l-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/m-o-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/p-r-passers/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/s-u-passer/",
  "https://boardexams.ph/list-of-passers/august-2026-nurses-licensure-exam-nle/v-z-passers/"
 ],
 "prcboard": [
  "https://www.prcboard.com/a--c-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/d-f-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/g-i-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/j-l-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/m-o-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/p-r-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/s-u-passers-august-september-2026-pnle-nurse-licensure-exam-results",
  "https://www.prcboard.com/v-z-passers-august-september-2026-pnle-nurse-licensure-exam-results"
 ]
}

class Text(HTMLParser):
 def __init__(self):
  super().__init__(); self.parts=[]; self.skip=0
 def handle_starttag(self, tag, attrs):
  if tag in ("script","style"): self.skip += 1
  if not self.skip and tag in ("br","p","div","li","tr","h1","h2","h3"): self.parts.append("\n")
 def handle_endtag(self, tag):
  if tag in ("script","style") and self.skip: self.skip -= 1
  if not self.skip and tag in ("p","div","li","tr","h1","h2","h3"): self.parts.append("\n")
 def handle_data(self, data):
  if not self.skip: self.parts.append(data)
 def result(self): return "\n".join(x.strip() for x in "".join(self.parts).replace("\xa0"," ").splitlines() if x.strip())

def fetch(url, limit=12*1024*1024):
 req=Request(url, headers={"User-Agent":UA,"Accept":"text/plain,text/html,*/*"})
 with urlopen(req, timeout=35) as r:
  host=urlparse(r.geturl()).hostname
  if host != urlparse(url).hostname: raise RuntimeError("Unexpected cross-host redirect")
  data=r.read(limit+1)
  if len(data)>limit: raise RuntimeError("Response exceeded size limit")
  return r.status, data, r.headers.get_content_type()

def robots_allows(url):
 host=urlparse(url).hostname
 robots_url="https://"+host+"/robots.txt"
 try: status, raw, _=fetch(robots_url, 512*1024)
 except HTTPError as e:
  if 400 <= e.code < 500 and e.code != 429: return True, 2.0, f"robots HTTP {e.code}: no published rule file"
  raise RuntimeError(f"Cannot verify robots policy for {host}: HTTP {e.code}")
 lines=raw.decode("utf-8","replace").splitlines()
 groups=[]; agents=[]; rules=[]; delay=0.0
 for line in lines:
  line=line.split("#",1)[0].strip()
  if not line or ":" not in line: continue
  k,v=[x.strip() for x in line.split(":",1)]
  if k.lower()=="user-agent":
   if rules: groups.append((agents,rules)); agents=[]; rules=[]
   agents.append(v.lower())
  elif k.lower() in ("allow","disallow") and agents:
   rules.append((k.lower(),v))
  elif k.lower()=="crawl-delay" and agents and v:
   try: delay=max(delay,float(v))
   except ValueError: pass
 if agents: groups.append((agents,rules))
 applicable=[]
 for a,rs in groups:
  if "*" in a or any("ph-exam-results-prc-research" in x for x in a): applicable += rs
 path=urlparse(url).path
 matches=[]
 for kind,rule in applicable:
  if not rule: continue
  prefix=rule.rstrip("*")
  if path.startswith(prefix): matches.append((len(prefix),kind))
 if matches:
  n=max(x[0] for x in matches)
  winners=[k for size,k in matches if size==n]
  if "allow" not in winners: return False,max(delay,2.0),f"robots disallows {path}"
 return True,max(delay,2.0),"robots allows or has no matching disallow"

def parse_records(url, raw):
 p=Text(); p.feed(raw.decode("utf-8","replace")); text=p.result()
 page=None; records=[]
 for line in text.splitlines():
  pm=re.search(r"Page\s*:?\s*(\d+)\s+of\s+\d+",line,re.I)
  if pm: page=int(pm.group(1))
  m=re.match(r"^\s*(\d{1,5})\s+(.+?,\s*.+?)\s*$",line)
  if not m: continue
  seq=m.group(1); name=re.sub(r"\s+"," ",m.group(2)).strip()
  if not name or len(name)>180: continue
  records.append({"sequence":seq,"name":name,"source_url":url,"mirror_page":page})
 return records

def main():
 OUT.mkdir(exist_ok=True)
 all_data={}
 audit=[]
 for site,urls in SITES.items():
  rows=[]
  for url in urls:
   allowed,delay,reason=robots_allows(url)
   audit.append({"site":site,"url":url,"robots_allowed":allowed,"robots_note":reason,"delay_seconds":delay})
   if not allowed: raise RuntimeError(f"Robots policy blocks {url}")
   time.sleep(delay)
   status,raw,ctype=fetch(url)
   if status!=200 or ctype!="text/html": raise RuntimeError(f"Unexpected response for {url}: {status} {ctype}")
   (OUT/(site+"-"+str(len(rows)+1)+".html")).write_bytes(raw)
   got=parse_records(url,raw)
   rows.extend(got)
   audit[-1]["bytes"]=len(raw); audit[-1]["records"]=len(got); audit[-1]["sha256"]=hashlib.sha256(raw).hexdigest()
  seqs=[r["sequence"] for r in rows]
  dup=sorted({x for x in seqs if seqs.count(x)>1})
  byseq={r["sequence"]:r for r in rows}
  missing=[str(n) for n in range(1,EXPECTED+1) if str(n) not in byseq]
  extra=[s for s in byseq if not s.isdigit() or int(s)<1 or int(s)>EXPECTED]
  all_data[site]={"rows":rows,"byseq":byseq,"count":len(rows),"unique_sequences":len(byseq),"duplicates":dup,"missing":missing,"extra":extra}
  (OUT/(site+"-records.jsonl")).write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
 a=all_data["boardexams"]; b=all_data["prcboard"]
 keys=sorted(set(a["byseq"])|set(b["byseq"]),key=lambda x:int(x) if x.isdigit() else 10**9)
 disagreements=[]
 for k in keys:
  x=a["byseq"].get(k); y=b["byseq"].get(k)
  if not x or not y or x["name"]!=y["name"]:
   disagreements.append({"sequence":k,"boardexams":x["name"] if x else None,"prcboard":y["name"] if y else None})
 report={
  "source_mode":"third_party_transcription_crosscheck_only",
  "official_pdf_downloaded":False,"official_pdf_access_note":"Google Drive says only owner and editors can download",
  "expected_passers":EXPECTED,
  "sources":{k:{x:v for x,v in d.items() if x not in ("rows","byseq")} for k,d in all_data.items()},
  "cross_source_disagreements":len(disagreements),
  "disagreement_examples":disagreements[:100],
  "layout_preserved_from_official_pdf":False,
  "physical_column_positions_verified":False,
  "greenlight":False,"published":False,
  "robots_audit":audit
 }
 (OUT/"mirror-validation-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({k:v for k,v in report.items() if k!="robots_audit"},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
