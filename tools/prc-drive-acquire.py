import hashlib, json, os, pathlib, subprocess, urllib.request
from urllib.parse import urlparse, parse_qs

fid = "13u_FOsF3DxS7RvMOdMqsg4Q1HF2rKtvU"
sid = os.environ.get("SOURCE_ID", "PRC-NLE-2026-08-09")
out = pathlib.Path(os.environ.get("OUTPUT_DIR", "private-prc-extraction"))
out.mkdir(parents=True, exist_ok=True)
url = "https://drive.google.com/uc?export=download&confirm=t&id=" + fid
req = urllib.request.Request(url, headers={"User-Agent":"PH-EXAM-RESULTS-PRC-Exam-Extractor/1.0","Accept":"application/pdf,*/*"})
with urllib.request.urlopen(req, timeout=30) as response:
    final = urlparse(response.geturl())
    q = parse_qs(final.query)
    if final.scheme != "https" or final.hostname not in {"drive.google.com","drive.usercontent.google.com"}:
        raise RuntimeError("Unexpected final host")
    data = response.read(50*1024*1024+1)
if len(data) > 50*1024*1024:
    raise RuntimeError("PDF too large")
if b"%PDF-" not in data[:1024]:
    (out / "drive-response-diagnostic.html").write_bytes(data[:1024*1024])
    raise RuntimeError("Drive did not return PDF; diagnostic response saved privately")
pdf = out / (sid + ".pdf")
pdf.write_bytes(data)
info = subprocess.run(["pdfinfo",str(pdf)],check=True,capture_output=True,text=True).stdout
subprocess.run(["pdftotext","-layout",str(pdf),str(out/"poppler-layout.txt")],check=True)
subprocess.run(["pdftotext","-bbox-layout",str(pdf),str(out/"poppler-bbox.html")],check=True)
text = (out/"poppler-layout.txt").read_text(errors="replace")
report = {"source_id":sid,"authority":"PRC","exam":"NLE","drive_file_id":fid,"expected_passers":28652,"pdf_bytes":len(data),"pdf_sha256":hashlib.sha256(data).hexdigest(),"pdfinfo":info,"native_text_characters":len(text),"count_match_verified":False,"sequence_name_pairs_verified":False,"published":False}
(out/"extraction-report.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
