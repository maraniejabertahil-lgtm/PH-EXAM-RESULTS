#!/usr/bin/env node
/**
 * Private, owner-approved CSC PDF acquisition and text extraction.
 * Uses Node.js + PDF.js; does not bypass Google permissions or access controls.
 */
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const MAX_BYTES = 50 * 1024 * 1024;
const MAX_REDIRECTS = 5;
const DRIVE_HOSTS = new Set(["drive.google.com", "drive.usercontent.google.com"]);

function fail(message) {
  throw new Error(message);
}

function validateDriveUrl(url, fileId) {
  if (
    url.protocol !== "https:" ||
    !DRIVE_HOSTS.has(url.hostname.toLowerCase()) ||
    url.username || url.password ||
    !["/uc", "/download"].includes(url.pathname) ||
    url.searchParams.get("id") !== fileId
  ) {
    fail("Blocked Drive redirect: expected an approved HTTPS download URL with the exact file ID.");
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
        "User-Agent": "PH-EXAM-RESULTS-Node-Extractor/1.0",
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
    if (declaredLength > MAX_BYTES) fail(`PDF exceeds the ${MAX_BYTES}-byte limit.`);
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
          fail(`PDF exceeds the ${MAX_BYTES}-byte limit.`);
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

async function main() {
  const sourceId = process.env.SOURCE_ID || "";
  const fileId = process.env.DRIVE_FILE_ID || "";
  const registryPath = process.env.SOURCE_REGISTRY || "python-engine/config/sources.json";
  const outputDir = process.env.OUTPUT_DIR || "private-extraction";
  if (!sourceId || !/^[A-Za-z0-9_-]{10,200}$/.test(fileId)) {
    fail("SOURCE_ID and a valid DRIVE_FILE_ID are required.");
  }

  const registry = JSON.parse(await readFile(registryPath, "utf8"));
  const matches = (registry.sources || []).filter((item) => item?.id === sourceId);
  if (matches.length !== 1) fail("Source ID must match exactly one registry entry.");
  const source = matches[0];
  if (
    source.authority !== "CSC" ||
    source.source_type !== "official" ||
    source.authorized !== true ||
    source.enabled !== true ||
    source.file_format !== "pdf" ||
    !Array.isArray(source.drive_file_ids) ||
    !source.drive_file_ids.includes(fileId)
  ) {
    fail("Source or Drive file ID is not explicitly approved in the registry.");
  }

  await mkdir(outputDir, { recursive: true });
  const bytes = await downloadApprovedPdf(fileId);
  const pdfByteLength = bytes.byteLength;
  const pdfSha256 = createHash("sha256").update(bytes).digest("hex");
  const pdfPath = path.join(outputDir, `${sourceId}-${fileId}.pdf`);
  await writeFile(pdfPath, bytes);

  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const document = await pdfjs.getDocument({
    data: new Uint8Array(bytes),
    useSystemFonts: true,
    isEvalSupported: false
  }).promise;

  const pages = [];
  let totalCharacters = 0;
  for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
    const page = await document.getPage(pageNumber);
    const content = await page.getTextContent();
    const text = content.items
      .filter((item) => typeof item.str === "string")
      .map((item) => item.str)
      .join(" ")
      .replace(/[\t ]+/g, " ")
      .trim();
    pages.push({ page: pageNumber, text });
    totalCharacters += text.length;
  }

  const extractedText = pages.map((page) => `===== PAGE ${page.page} =====\n${page.text}`).join("\n\n");
  const textPath = path.join(outputDir, `${sourceId}-${fileId}.txt`);
  await writeFile(textPath, extractedText + "\n", "utf8");

  const report = {
    status: totalCharacters > 0 ? "text_extracted_private_review_required" : "no_embedded_text_ocr_required",
    source_id: sourceId,
    authority: source.authority,
    exam: source.exam,
    drive_file_id: fileId,
    pdf_bytes: pdfByteLength,
    pdf_sha256: pdfSha256,
    page_count: document.numPages,
    extracted_characters: totalCharacters,
    pdf_file: pdfPath,
    text_file: textPath,
    ocr_performed: false,
    published: false
  };
  await writeFile(
    path.join(outputDir, "extraction-report.json"),
    JSON.stringify(report, null, 2) + "\n",
    "utf8"
  );
  console.log(JSON.stringify({
    status: report.status,
    source_id: sourceId,
    drive_file_id: fileId,
    pdf_bytes: report.pdf_bytes,
    page_count: report.page_count,
    extracted_characters: totalCharacters,
    published: false
  }, null, 2));
  await document.destroy();
}

main().catch((error) => {
  console.error(`Extraction stopped safely: ${error.message || error}`);
  process.exitCode = 1;
});
