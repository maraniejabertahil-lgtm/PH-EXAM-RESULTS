"""Format adapters. Preserve names exactly; stop when layout is unclear."""
import csv, io, json
from html.parser import HTMLParser
class NeedsReview(Exception): pass
REGISTRY = {}
def adapter(fmt):
    def deco(fn): REGISTRY[fmt] = fn; return fn
    return deco
def _pair(seq, name):
    seq, name = str(seq).strip().replace(",", ""), str(name)
    if not seq.isdigit() or not name.strip(): raise NeedsReview(f"unparseable row: seq={seq!r} name={name!r}")
    return int(seq), name
@adapter("csv")
def csv_adapter(raw, mapping):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    sc, nc = mapping.get("seq_col"), mapping.get("name_col")
    if not rows or sc not in rows[0] or nc not in rows[0]: raise NeedsReview("csv columns do not match reviewed mapping")
    return [_pair(r[sc], r[nc]) for r in rows]
@adapter("json")
def json_adapter(raw, mapping):
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict): data = data.get(mapping.get("list_key", "records"))
    if not isinstance(data, list): raise NeedsReview("json layout does not match reviewed mapping")
    sk, nk = mapping.get("seq_key"), mapping.get("name_key")
    try: return [_pair(r[sk], r[nk]) for r in data]
    except KeyError as e: raise NeedsReview(f"json key missing: {e}")
class _Tbl(HTMLParser):
    def __init__(self): super().__init__(); self.rows, self._r, self._c, self._in = [], None, None, False
    def handle_starttag(self,t,a):
        if t == "tr": self._r=[]
        elif t in ("td","th") and self._r is not None: self._c,self._in=[],True
    def handle_data(self,d):
        if self._in: self._c.append(d)
    def handle_endtag(self,t):
        if t in ("td","th") and self._in: self._r.append("".join(self._c).strip()); self._in=False
        elif t == "tr" and self._r is not None: self.rows.append(self._r); self._r=None
@adapter("html")
def html_adapter(raw,mapping):
    p=_Tbl(); p.feed(raw.decode("utf-8")); si,ni=mapping.get("seq_idx"),mapping.get("name_idx")
    if si is None or ni is None: raise NeedsReview("no reviewed column mapping for html layout")
    out=[]
    for i,r in enumerate(p.rows):
        if len(r)<=max(si,ni): raise NeedsReview(f"short row {i}")
        if i==0 and not r[si].replace(",","").isdigit(): continue
        out.append(_pair(r[si],r[ni]))
    return out
@adapter("pdf")
def pdf_adapter(raw,mapping):
    try: import pdfplumber
    except ImportError: raise NeedsReview("pdfplumber not installed")
    si,ni=mapping.get("seq_idx"),mapping.get("name_idx")
    if si is None or ni is None: raise NeedsReview("no reviewed column mapping for pdf layout")
    out=[]
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    if r and len(r)>max(si,ni) and (r[si] or "").replace(",","").strip().isdigit(): out.append(_pair(r[si],r[ni] or ""))
    if not out: raise NeedsReview("no table rows found in pdf")
    return out
def greenlight(records,announced):
    f,seqs=[],[s for s,_ in records]
    if not records: f.append("no records")
    if len(set(seqs))!=len(seqs): f.append("duplicate sequence numbers")
    if seqs and sorted(seqs)!=list(range(1,len(seqs)+1)): f.append("sequence not contiguous from 1")
    if announced and len(records)!=announced: f.append(f"count {len(records)} != announced {announced}")
    if any("\ufffd" in n for _,n in records): f.append("replacement characters in names")
    return (100 if not f else 0),f
