#!/usr/bin/env python3
"""PRC March 2026 LEPT Elementary two-source extraction proof.

Official PRC announcement and linked Drive file are attempted first. If the
official list contents cannot be accessed without authentication, the script
uses two separately hosted public transcriptions, checks robots.txt, extracts
sequence/name pairs, and requires exact 1..18,376 coverage and pair agreement.
No data is published by this workflow.
"""
from __future__ import annotations
import hashlib, json, re, time
from collections import defaultdict
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen
from pathlib import Path

EXPECTED = 18376
OUT = Path("elementary-evidence")
UA = "PH-EXAM-RESULTS-Research/1.0 (+public result validation)"
OFFICIAL = "https://www.prc.gov.ph/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39"
DRIVE_ID = "1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE"
LANDINGS = {
 "boardexams": ("https://boardexams.ph/list-of-passers/march-2026-licensure-exam-for-teachers-let-elementary-level/","boardexams.ph"),
 "prcboard": ("https://www.prcboard.com/a-b-passers-march-2026-lept-results-elementary-level","www.prcboard.com"),
}
class Page(HTMLParser):
 def __init__(self):
  super().__init__(); self.parts=[]; self.links=[]; self.anchor=[]; self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","noscript"): self.skip+=1
  if tag=="a": self.anchor=[dict(attrs).get("href",""),""]
  if not self.skip and tag in ("br","p","div","li","tr","h1","h2","h3"): self.parts.append("\n")
 def handle_data(self,data):
  if not self.skip: self.parts.append(data)
  if self.anchor is not None: self.anchor[1]+=data
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript") and self.skip: self.skip-=1
  if tag=="a" and self.anchor is not None:
   self.links.append(tuple(self.anchor)); self.anchor=None
  if not self.skip and tag in ("p","div","li","tr","h1","h2","h3"): self.parts.append("\n")
 def text(self): return "\n".join(x.strip() for x in "".join(self.parts).replace("\xa0"," ").splitlines() if x.strip())
def fetch(url,limit=12*1024*1024):
 req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/pdf,*/*"})
 with urlopen(req,timeout=30) as r:
  final=r.geturl(); host=urlparse(final).hostname
  if host and host.lower()!=urlparse(url).hostname.lower() and "google.com" not in host:
   raise RuntimeError("Unexpected cross-host redirect")
  data=r.read(limit+1)
  if len(data)>limit: raise RuntimeError("Response exceeds 12 MiB")
  return r.status,data,r.headers.get_content_type(),final
def robots_allowed(url):
 host=urlparse(url).hostname
 try:
  status,raw,_,_=fetch("https://"+host+"/robots.txt",512*1024)
 except HTTPError as e:
  if 400<=e.code<500 and e.code!=429: return True,"robots.txt HTTP "+str(e.code)+" (no published rules)"
  raise RuntimeError("Cannot verify robots.txt for "+host+": "+str(e.code))
 lines=raw.decode("utf-8","replace").splitlines(); groups=[]; agents=[]; rules=[]
 for line in lines:
  line=line.split("#",1)[0].strip()
  if not line or ":" not in line: continue
  k,v=map(str.strip,line.split(":",1))
  if k.lower()=="user-agent":
   if agents: groups.append((agents,rules)); agents=[]; rules=[]
   agents.append(v.lower())
  elif k.lower() in ("allow","disallow") and agents: rules.append((k.lower(),v))
 if agents: groups.append((agents,rules))
 selected=[]
 for ag,rs in groups:
  if "*" in ag or any("ph-exam-results-research" in x for x in ag): selected.extend(rs)
 path=urlparse(url).path; matches=[]
 for kind,rule in selected:
  if rule and path.startswith(rule.rstrip("*")): matches.append((len(rule.rstrip("*")),kind))
 if matches:
  n=max(x[0] for x in matches)
  if "allow" not in [k for size,k in matches if size==n]: return False,"robots.txt disallows "+path
 return True,"robots.txt permits or has no matching disallow"
def links_for(page,url,domain):
 out=[]
 for href,label in page.links:
  if not href: continue
  absolute=urljoin(url,href); p=urlparse(absolute)
  if p.scheme!="https" or p.hostname!=domain: continue
  low=(absolute+" "+label).lower()
  if "elementary" in low and ("passer" in low or "pass" in low or "let" in low):
   out.append(absolute.split("#")[0])
 return out
def crawl(site,landing,domain):
 seen=set(); queue=[landing]; allrows={}; audit=[]
 while queue and len(seen)<60:
  url=queue.pop(0)
  if url in seen: continue
  seen.add(url)
  allowed,why=robots_allowed(url); audit.append({"url":url,"robots_allowed":allowed,"robots_note":why})
  if not allowed: raise RuntimeError("Robots policy blocks "+url)
  time.sleep(2)
  status,raw,ctype,final=fetch(url)
  if status!=200 or ctype not in ("text/html","application/xhtml+xml"): raise RuntimeError(f"Unexpected page response {status} {ctype}: {url}")
  page=Page(); page.feed(raw.decode("utf-8","replace")); body=page.text()
  # Only parse pages explicitly identifying this exact examination and Elementary.
  if "elementary" in body.lower() and ("march 15, 2026" in body.lower() or "march 2026" in body.lower()):
   for line in body.splitlines():
    m=re.match(r"^\s*(\d{1,5})\s+(.+?,\s*.+?)\s*$",line)
    if m:
     seq=m.group(1); name=re.sub(r"\s+"," ",m.group(2)).strip()
     if name and len(name)<=180:
      allrows.setdefault(seq,[]).append(name)
  for link in links_for(page,final,domain):
   if link not in seen and link not in queue: queue.append(link)
  audit[-1].update({"http_status":status,"content_type":ctype,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"links_queued":len(queue)})
  if len(seen)%10==0: print(f"{site}: inspected {len(seen)} pages; queued {len(queue)}",flush=True)
 # A sequence repeated with different spellings is not silently resolved.
 dup={k:sorted(set(v)) for k,v in allrows.items() if len(set(v))>1}
 rows={k:v[0] for k,v in allrows.items() if len(set(v))==1}
 missing=[str(n) for n in range(1,EXPECTED+1) if str(n) not in rows]
 extra=[k for k in rows if not k.isdigit() or not 1<=int(k)<=EXPECTED]
 report={"page_count":len(seen),"record_rows_observed":sum(len(v) for v in allrows.values()),"unique_sequences":len(rows),"duplicates_conflicting":dup,"missing_sequences":missing[:100],"missing_count":len(missing),"extra_sequences":extra[:100],"extra_count":len(extra),"records":rows,"audit":audit}
 (OUT/(site+"-records.json")).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 return report
def main():
 OUT.mkdir(exist_ok=True)
 official={"announcement_url":OFFICIAL,"announcement_attempt":None,"linked_drive_url":"https://drive.google.com/file/d/"+DRIVE_ID+"/view","drive_attempt":None,"official_content_obtained":False}
 try:
  status,raw,ctype,final=fetch(OFFICIAL)
  official["announcement_attempt"]={"status":status,"content_type":ctype,"final_url":final,"bytes":len(raw)}
  text=raw.decode("utf-8","replace")
  if DRIVE_ID not in text: raise RuntimeError("Official article response did not expose the configured Drive ID")
  # Bounded public download attempt only; no sign-in or access-control bypass.
  try:
   ds,db,dt,df=fetch("https://drive.google.com/uc?export=download&id="+DRIVE_ID,50*1024*1024)
   official["drive_attempt"]={"status":ds,"content_type":dt,"final_url":df,"bytes":len(db),"pdf_signature":db[:1024].find(b"%PDF-")>=0}
   if official["drive_attempt"]["pdf_signature"]:
    (OUT/"official-elementary.pdf").write_bytes(db); official["official_content_obtained"]=True
  except Exception as e: official["drive_attempt"]={"error":str(e)}
 except Exception as e: official["announcement_attempt"]={"error":str(e)}
 (OUT/"official-attempt-evidence.json").write_text(json.dumps(official,indent=2)+"\n",encoding="utf-8")
 if official["official_content_obtained"]:
  print("Official PDF bytes acquired; this fallback-only proof will not substitute mirrors.",flush=True)
  raise SystemExit("Official bytes acquired; use the official-content extraction path.")
 results={}
 for site,(landing,domain) in LANDINGS.items():
  results[site]=crawl(site,landing,domain)
 a,b=results["boardexams"],results["prcboard"]
 disagreements=[]
 for n in range(1,EXPECTED+1):
  k=str(n); x=a["records"].get(k); y=b["records"].get(k)
  if x is None or y is None or x!=y: disagreements.append({"sequence":k,"boardexams":x,"prcboard":y})
 passed=all(results[s]["unique_sequences"]==EXPECTED and results[s]["missing_count"]==0 and results[s]["extra_count"]==0 and not results[s]["duplicates_conflicting"] for s in results) and not disagreements
 summary={"exam":"March 2026 LEPT Elementary","authority":"PRC","provenance":"third_party_fallback","expected_passers":EXPECTED,"official_attempt":official,"source_summaries":{s:{k:v for k,v in r.items() if k not in ("records","audit")} for s,r in results.items()},"cross_source_disagreement_count":len(disagreements),"cross_source_disagreement_examples":disagreements[:100],"greenlight":bool(passed),"publication_allowed":False,"published":False,"reason":"Evidence-only extraction run. Publication remains disabled pending full Greenlight review and the repository's normal GitOps acceptance path."}
 (OUT/"elementary-extraction-report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
 if not passed: raise SystemExit("Elementary extraction did not meet exact 18,376-record two-source Greenlight.")
if __name__=="__main__": main()

# Trigger a clean extraction run after workflow registration on the default branch.
