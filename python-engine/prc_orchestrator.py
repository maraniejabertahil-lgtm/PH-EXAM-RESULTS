"""FIX 2: single shared orchestrator. validate -> acquire -> adapter -> greenlight -> dataset+report.
Exit codes: 0 extracted (review pending), 2 invalid event, 3 stopped for human review (never guesses)."""
import argparse, hashlib, json, sys, urllib.request
from pathlib import Path
from urllib.parse import urlparse
from prc_adapters import REGISTRY, NeedsReview, greenlight
ALLOWED_HOSTS = {"www.prc.gov.ph", "prc.gov.ph", "drive.google.com", "docs.google.com"}
REQ = ["schema_version","source_id","article_url","exam_code","exam_title","exam_year","list_type","content_urls","detected_at"]
HERE = Path(__file__).parent
def validate_event(e):
    err = [f"missing {k}" for k in REQ if k not in e]
    if err: return err
    if e["schema_version"] != "1": err.append("unsupported schema_version")
    if not isinstance(e["exam_year"], int): err.append("exam_year must be int")
    if e["exam_code"] == "LICENSURE-EXAM-RESULTS": err.append("generic exam code (legacy payload)")
    if e["exam_code"] == "LEPT" and e.get("result_level") not in ("elementary", "secondary"):
        err.append("LEPT requires result_level elementary|secondary")
    for c in e["content_urls"]:
        if urlparse(c["url"]).hostname not in ALLOWED_HOSTS: err.append(f"host not allowed: {c['url']}")
        if c["format"] not in REGISTRY: err.append(f"unsupported format {c['format']}")
    return err
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PH-EXAM-RESULTS-ingest"})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read()
def load_mapping(e, fmt, cfg_path=None):
    cfg = json.loads((cfg_path or HERE / "config" / "adapter_mappings.json").read_text("utf-8"))
    return cfg.get(f"{e['exam_code']}:{e.get('result_level') or '*'}:{fmt}")
def run(e, out, fetcher=fetch, cfg_path=None):
    out.mkdir(parents=True, exist_ok=True)
    rep = {"event": e, "published": False, "status": "started"}
    def finish(status, code, **kw):
        rep.update(status=status, **kw)
        (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), "utf-8")
        return code
    errs = validate_event(e)
    if errs: return finish("invalid_event", 2, errors=errs)
    c = e["content_urls"][0] if len(e["content_urls"]) == 1 else None
    if c is None: return finish("needs_review", 3, reason="multiple content urls: human must pick the right list")
    mapping = load_mapping(e, c["format"], cfg_path)
    if mapping is None: return finish("needs_review", 3, reason=f"no reviewed mapping for {e['exam_code']}/{e.get('result_level')}/{c['format']}")
    try: records = REGISTRY[c["format"]](fetcher(c["url"]), mapping)
    except NeedsReview as ex: return finish("needs_review", 3, reason=str(ex), source=c["url"])
    score, fails = greenlight(records, e.get("announced_count"))
    if score < 100: return finish("needs_review", 3, reason="greenlight failed", failures=fails)
    ds = {"exam_code": e["exam_code"], "exam_year": e["exam_year"], "level": e.get("result_level"),
          "source": c["url"], "records": [{"seq": s, "name": n} for s, n in records]}
    body = json.dumps(ds, ensure_ascii=False, indent=1).encode("utf-8")
    name = f"{e['exam_code']}_{e.get('result_level') or 'all'}_{e['exam_year']}.json"
    (out / name).write_bytes(body)
    return finish("extracted_pending_review", 0, dataset=name, records=len(records), greenlight=100,
                  sha256=hashlib.sha256(body).hexdigest(), human_visual_review="PENDING")
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True); ap.add_argument("--out", default="out")
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args()
    ev = json.loads(Path(a.event).read_text("utf-8"))
    if a.validate_only:
        errs = validate_event(ev); print(json.dumps(errs)); sys.exit(2 if errs else 0)
    sys.exit(run(ev, Path(a.out)))
