#!/usr/bin/env node
/**
 * Private PRC LEPT sample acquisition, PDF text extraction and OCR.
 * Staging-only: creates a private Actions artifact; never commits or publishes data.
 */
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const fail = (m) => { throw new Error(m); };
const run = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", maxBuffer: 30 * 1024 * 1024 });
  if (r.error) throw r.error;
  if (r.status !== 0) fail(`${cmd} failed: ${(r.stderr || r.stdout || "").trim()}`);
  return r.stdout || "";
};

async function main() {
  const id = process.env.SOURCE_ID || "";
  const registryPath = process.env.SOURCE_REGISTRY || "python-engine/config/prc-let-sources.json";
  const out = process.env.OUTPUT_DIR || "private-prc-let-extraction";
  const registry = JSON.parse(await readFile(registryPath, "utf8"));
  const matches = (registry.sources || []).filter(s => s.id === id);
  if (matches.length !== 1) fail("SOURCE_ID must match exactly one PRC LET registry entry.");
  const source = matches[0];
  if (source.authority !== "PRC" || source.exam !== "LEPT" || source.authorized !== true ||
      source.enabled !== true || source.source_type !== "official" ||
      !/^[A-Za-z0-9_-]{10,200}$/.test(source.drive_file_id || "")) {
    fail("Source is not an explicitly approved official PRC LEPT PDF.");
  }

  await mkdir(out, { recursive: true });
  const url = new URL("https://drive.google.com/uc");
  url.searchParams.set("export", "download");
  url.searchParams.set("id", source.drive_file_id);
  const response = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(60000) });
  if (!response.ok) fail(`Google Drive returned HTTP ${response.status}.`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!bytes.length || bytes.length > 50 * 1024 * 1024) fail("PDF is empty or exceeds 50 MB.");
  if (!bytes.subarray(0, 1024).includes(Buffer.from("%PDF-"))) fail("Drive did not return a PDF; refusing HTML/interstitial content.");

  const pdfPath = path.join(out, `${id}.pdf`);
  await writeFile(pdfPath, bytes);
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const doc = await pdfjs.getDocument({ data: new Uint8Array(bytes), useSystemFonts: true, isEvalSupported: false }).promise;
  const pages = [];
  let chars = 0;
  for (let n = 1; n <= doc.numPages; n++) {
    const p = await doc.getPage(n);
    const c = await p.getTextContent();
    const t = c.items.filter(x => typeof x.str === "string").map(x => x.str).join(" ").replace(/[\t ]+/g, " ").trim();
    pages.push(`===== PAGE ${n} =====\n${t}`);
    chars += t.length;
  }
  const textPath = path.join(out, `${id}-embedded.txt`);
  await writeFile(textPath, pages.join("\n\n") + "\n", "utf8");

  let ocrChars = 0;
  let ocrPages = 0;
  if (chars === 0) {
    const tmp = path.join(out, "rendered");
    await mkdir(tmp, { recursive: true });
    const prefix = path.join(tmp, "page");
    run("pdftoppm", ["-r", "200", "-jpeg", "-jpegopt", "quality=88", pdfPath, prefix]);
    const { readdir } = await import("node:fs/promises");
    const imgs = (await readdir(tmp)).filter(x => /^page-\d+\.jpg$/i.test(x))
      .sort((a,b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));
    if (imgs.length !== doc.numPages) fail("Rendered page count does not match PDF page count.");
    const ocr = [];
    for (let i=0; i<imgs.length; i++) {
      const t = run("tesseract", [path.join(tmp, imgs[i]), "stdout", "-l", "eng", "--psm", "6"]).trim();
      ocr.push(`===== PAGE ${i+1} =====\n${t}`);
      ocrChars += t.length;
    }
    ocrPages = imgs.length;
    await writeFile(path.join(out, `${id}-ocr.txt`), ocr.join("\n\n") + "\n", "utf8");
  }

  const report = {
    status: chars > 0 ? "embedded_text_extracted_review_required" : "ocr_completed_review_required",
    source_id: id, authority: "PRC", exam: "LEPT", level: source.level,
    exam_date: source.exam_date, expected_passers: source.expected_passers,
    announcement_url: source.announcement_url, drive_file_id: source.drive_file_id,
    pdf_bytes: bytes.length, pdf_sha256: createHash("sha256").update(bytes).digest("hex"),
    page_count: doc.numPages, embedded_text_characters: chars,
    ocr_performed: chars === 0, ocr_page_count: ocrPages, ocr_characters: ocrChars,
    expected_passers_are_reference_only: true,
    count_match_verified: false, names_verified: false, published: false
  };
  await writeFile(path.join(out, "extraction-report.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
  await doc.destroy();
}
main().catch(e => { console.error(`PRC LET staging extraction stopped safely: ${e.message || e}`); process.exitCode = 1; });
