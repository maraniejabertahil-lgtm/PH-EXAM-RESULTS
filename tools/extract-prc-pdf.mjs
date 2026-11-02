#!/usr/bin/env node
/**
 * Private PRC examination sample acquisition, PDF text extraction and OCR.
 * Staging-only: extracts approved official PRC examination PDFs; never commits or publishes names.
 */
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const fail = (m) => { throw new Error(m); };

const MAX_BYTES = 50 * 1024 * 1024;
const MAX_REDIRECTS = 5;
const DRIVE_HOSTS = new Set(["drive.google.com", "drive.usercontent.google.com"]);

export function validateDriveUrl(url, fileId) {
  if (url.protocol !== "https:" || !DRIVE_HOSTS.has(url.hostname.toLowerCase()) ||
      url.username || url.password || !["/uc", "/download"].includes(url.pathname) ||
      url.searchParams.get("id") !== fileId) {
    fail("Blocked Google Drive redirect: expected an approved HTTPS download URL with the exact file ID.");
  }
}

async function downloadApprovedPdf(fileId) {
  const start = new URL("https://drive.google.com/uc");
  start.searchParams.set("export", "download");
  start.searchParams.set("id", fileId);
  let current = start;

  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    validateDriveUrl(current, fileId);
    const response = await fetch(current, {
      method: "GET",
      redirect: "manual",
      headers: {
        "User-Agent": "PH-EXAM-RESULTS-PRC-Exam-Extractor/1.0",
        "Accept": "application/pdf,application/octet-stream,*/*"
      },
      signal: AbortSignal.timeout(30000)
    });

    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get("location");
      if (!location) fail("Drive redirect did not include a Location header.");
      current = new URL(location, current);
      validateDriveUrl(current, fileId);
      continue;
    }

    if (response.status !== 200 && response.status !== 206) {
      fail(`Google Drive returned HTTP ${response.status}; access was not bypassed.`);
    }
    const type = (response.headers.get("content-type") || "").split(";")[0].toLowerCase();
    if (type === "text/html") fail("Google Drive returned an HTML interstitial, not a PDF.");

    const declaredLength = Number(response.headers.get("content-length") || 0);
    if (declaredLength > MAX_BYTES) fail("PDF exceeds the 50 MB limit.");
    const reader = response.body?.getReader();
    if (!reader) fail("Google Drive returned no response body.");
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > MAX_BYTES) {
          await reader.cancel();
          fail("PDF exceeds the 50 MB limit.");
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    if (!total) fail("Google Drive returned an empty file.");
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    if (!Buffer.from(bytes.subarray(0, 1024)).includes(Buffer.from("%PDF-"))) {
      fail("Downloaded bytes do not contain the PDF signature.");
    }
    return bytes;
  }
  fail("Google Drive exceeded the redirect limit.");
}
const run = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", maxBuffer: 30 * 1024 * 1024 });
  if (r.error) throw r.error;
  if (r.status !== 0) fail(`${cmd} failed: ${(r.stderr || r.stdout || "").trim()}`);
  return r.stdout || "";
};

export function isApprovedPrcSource(source) {
  return Boolean(source && source.authority === "PRC" &&
    typeof source.exam === "string" && source.exam.trim() &&
    source.authorized === true && source.enabled === true &&
    source.source_type === "official" &&
    /^[A-Za-z0-9_-]{10,200}$/.test(source.drive_file_id || ""));
}

export function selectApprovedSource(registry, id) {
  if (!id || !registry || !Array.isArray(registry.sources)) {
    fail("SOURCE_ID and a valid sources registry are required.");
  }
  const matches = registry.sources.filter(s => s.id === id);
  if (matches.length !== 1) fail("SOURCE_ID must match exactly one PRC source registry entry.");
  const source = matches[0];
  if (!isApprovedPrcSource(source)) fail("Source is not an explicitly approved official PRC PDF.");
  return source;
}

async function main() {
  const id = process.env.SOURCE_ID || "";
  const registryPath = process.env.SOURCE_REGISTRY || "python-engine/config/prc-sources.json";
  const out = process.env.OUTPUT_DIR || "private-prc-extraction";
  const registry = JSON.parse(await readFile(registryPath, "utf8"));
  const source = selectApprovedSource(registry, id);

  await mkdir(out, { recursive: true });
  const bytes = Buffer.from(await downloadApprovedPdf(source.drive_file_id));

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
    source_id: id, authority: "PRC", exam: source.exam, level: source.level,
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
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(e => { console.error(`PRC staging extraction stopped safely: ${e.message || e}`); process.exitCode = 1; });
}
