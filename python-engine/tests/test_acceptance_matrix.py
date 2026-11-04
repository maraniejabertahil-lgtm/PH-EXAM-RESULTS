"""Synthetic acceptance matrix for CPA CSV, Nursing JSON, Criminology HTML and fail-closed cases."""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent))
import prc_orchestrator as O
NAMES=["DELA CRUZ, JUAN P.","NUÑEZ, MARIA ÁNGELES","PEÑA, JOSÉ R.","SANTOS, ANA-LIZA"]
CSV=("No.,Name\n"+"\n".join(f'{i+1},"{n}"' for i,n in enumerate(NAMES))).encode()
JSN=json.dumps({"records":[{"n":i+1,"full":n} for i,n in enumerate(NAMES)]},ensure_ascii=False).encode()
HTML=("<table><tr><th>Seq</th><th>Name</th></tr>"+"".join(f"<tr><td>{i+1}</td><td>{n}</td></tr>" for i,n in enumerate(NAMES))+"</table>").encode()
CFG={"CPALE:*:csv":{"seq_col":"No.","name_col":"Name"},"NLE:*:json":{"seq_key":"n","name_key":"full"},"CLE:*:html":{"seq_idx":0,"name_idx":1}}
def ev(code,fmt,count=4,**kw):
 e={"schema_version":"1","source_id":"prc","article_url":"https://www.prc.gov.ph/a","exam_code":code,"exam_title":f"{code} results 2026","exam_year":2026,"list_type":"successful_examinees","announced_count":count,"content_urls":[{"url":"https://www.prc.gov.ph/x","format":fmt}],"detected_at":"2026-11-04T00:00:00Z"}; e.update(kw); return e
class Matrix(unittest.TestCase):
 def go(self,e,raw):
  d=Path(tempfile.mkdtemp()); cfg=d/"m.json"; cfg.write_text(json.dumps(CFG)); code=O.run(e,d/"out",fetcher=lambda u:raw,cfg_path=cfg); return code,json.loads((d/"out"/"report.json").read_text())
 def test_cpa_csv(self): self.assertEqual(self.go(ev("CPALE","csv"),CSV)[0],0)
 def test_nursing_json(self): self.assertEqual(self.go(ev("NLE","json"),JSN)[0],0)
 def test_crim_html(self): self.assertEqual(self.go(ev("CLE","html"),HTML)[0],0)
 def test_unicode_exact(self):
  d=Path(tempfile.mkdtemp()); cfg=d/"m.json"; cfg.write_text(json.dumps(CFG)); O.run(ev("CPALE","csv"),d/"o",fetcher=lambda u:CSV,cfg_path=cfg); ds=json.loads((d/"o"/"CPALE_all_2026.json").read_text("utf-8")); self.assertEqual([r["name"] for r in ds["records"]],NAMES)
 def test_count_mismatch_stops(self): self.assertEqual(self.go(ev("CPALE","csv",5),CSV)[0],3)
 def test_missing_row_stops(self): self.assertEqual(self.go(ev("CPALE","csv"),CSV.replace(b"2,",b"9,"))[0],3)
 def test_unknown_layout_stops(self): self.assertEqual(self.go(ev("CPALE","html"),HTML)[0],3)
 def test_legacy_generic_payload_rejected(self): self.assertEqual(self.go(ev("LICENSURE-EXAM-RESULTS","csv"),CSV)[0],2)
 def test_lept_needs_level(self): self.assertEqual(self.go(ev("LEPT","pdf"),b"")[0],2)
 def test_untrusted_host_rejected(self):
  e=ev("CPALE","csv"); e["content_urls"][0]["url"]="https://evil.example/x.csv"; self.assertEqual(self.go(e,CSV)[0],2)
 def test_never_published(self): self.assertFalse(self.go(ev("CPALE","csv"),CSV)[1]["published"])
if __name__=="__main__": unittest.main()
